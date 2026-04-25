import pygame
import sys
import hashlib
import subprocess
import queue
import math
from ui import Button, TextInput
from network import NetworkManager
from game import Board, AttackBoard

# Configuración básica
WIDTH, HEIGHT = 800, 600
FPS = 60
MIN_WIDTH, MIN_HEIGHT = 760, 560

# Colores
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
BLUE = (100, 150, 255)
DARK_BLUE = (50, 100, 200)

# Estados del juego
STATE_MENU = 0
STATE_CREATE_ROOM = 1
STATE_JOIN_ROOM = 2
STATE_ROOM_CREATED = 3
STATE_GAME = 4
STATE_LOBBY = 5

def generate_room_hash(room_name):
    """Genera un hash SHA-256 a partir del nombre de la sala (Semilla)."""
    return hashlib.sha256(room_name.encode('utf-8')).hexdigest()

def copy_to_clipboard(text):
    """Intenta copiar texto al portapapeles de forma robusta en Linux (Wayland/X11)."""
    try:
        subprocess.run(['wl-copy'], input=text.encode('utf-8'), check=True, stderr=subprocess.DEVNULL)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        try:
            subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode('utf-8'), check=True, stderr=subprocess.DEVNULL)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

def main():
    global WIDTH, HEIGHT
    pygame.init()
        
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Hundir la Flota P2P")
    clock = pygame.time.Clock()

    font_title = pygame.font.SysFont(None, 64)
    font_normal = pygame.font.SysFont(None, 36)
    font_small = pygame.font.SysFont(None, 24)

    current_state = STATE_MENU

    net_manager = None
    is_host = False
    msg_queue = queue.Queue()
    
    # Variables de Partida
    my_board = None
    has_committed_board = False
    player_commits = {} # Aquí guardaremos los board_hash de los rivales
    
    # Variables de Batalla
    battle_phase = False
    attack_boards = []
    btn_fire = Button(WIDTH//2 - 70, HEIGHT - 60, 140, 40, "¡Fuego!", font_normal, bg_color=(200, 50, 50), hover_color=(255, 100, 100))
    all_players_sorted = []
    current_turn_index = 0

    def on_message_received(msg):
        msg_queue.put(msg)

    # Elementos UI - Menú Principal
    btn_create = Button(WIDTH//2 - 150, HEIGHT//2 - 50, 300, 50, "Crear una nueva sala", font_normal)
    btn_join = Button(WIDTH//2 - 150, HEIGHT//2 + 20, 300, 50, "Unirse a una sala", font_normal)

    # Elementos UI - Crear Sala
    input_create_name = TextInput(WIDTH//2 - 150, HEIGHT//2 - 120, 300, 40, font_normal)
    input_create_room = TextInput(WIDTH//2 - 150, HEIGHT//2 - 30, 300, 40, font_normal)
    btn_create_confirm = Button(WIDTH//2 + 10, HEIGHT//2 + 40, 140, 40, "Crear sala", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)
    btn_create_back = Button(WIDTH//2 - 150, HEIGHT//2 + 40, 140, 40, "Volver", font_normal)
    
    # Elementos UI - Sala Creada
    room_hash_display = ""
    btn_copy_hash = Button(WIDTH//2 - 150, HEIGHT//2 + 20, 300, 40, "Copiar Hash al Portapapeles", font_normal)
    btn_goto_lobby = Button(WIDTH//2 - 150, HEIGHT//2 + 80, 300, 40, "Ir a la Sala de Espera", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)

    # Elementos UI - Lobby
    btn_start_lobby = Button(WIDTH//2 - 150, HEIGHT - 100, 300, 40, "Empezar Partida", font_normal, bg_color=(50, 200, 50), hover_color=(50, 150, 50))

    # Elementos UI - Unirse a Sala
    input_join_name = TextInput(WIDTH//2 - 200, HEIGHT//2 - 120, 400, 40, font_normal)
    input_join_room = TextInput(WIDTH//2 - 200, HEIGHT//2 - 30, 400, 40, font_normal)
    btn_join_confirm = Button(WIDTH//2 + 10, HEIGHT//2 + 40, 140, 40, "Unirse", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)
    btn_join_back = Button(WIDTH//2 - 150, HEIGHT//2 + 40, 140, 40, "Volver", font_normal)

    def clamp_window_size(w, h):
        return max(MIN_WIDTH, w), max(MIN_HEIGHT, h)

    def fit_board_cell_size(board_size_cells, max_w, max_h, max_cell, min_cell=8):
        if max_w <= 0 or max_h <= 0:
            return min_cell
        by_w = max_w // board_size_cells
        by_h = max_h // board_size_cells
        return max(min_cell, min(max_cell, by_w, by_h))

    def compute_battle_layout(window_w, window_h, rivals_count):
        top_margin = 12
        turn_block_h = font_title.get_height() + 12
        attack_label_h = font_small.get_height() + 6
        defense_label_h = font_small.get_height() + 6
        bottom_pad = 16
        fire_h = btn_fire.rect.height

        # Espacio vertical total disponible para tableros (ataque + defensa)
        fixed_vertical = top_margin + turn_block_h + attack_label_h + defense_label_h + bottom_pad
        if rivals_count > 0:
            fixed_vertical += fire_h + 10

        vertical_budget = max(120, window_h - fixed_vertical)

        # Reservar algo más para ataque cuando hay muchos rivales
        attack_share = 0.62 if rivals_count >= 2 else 0.55
        attack_budget = int(vertical_budget * attack_share)
        defense_budget = vertical_budget - attack_budget

        # Defensa siempre visible
        defense_cell = fit_board_cell_size(12, window_w - 40, defense_budget, max_cell=22, min_cell=10)

        if rivals_count <= 0:
            return {
                "attack_cell": 20,
                "attack_gap": 24,
                "attack_start_x": window_w // 2,
                "attack_y": top_margin + turn_block_h + attack_label_h,
                "defense_cell": defense_cell,
                "defense_x": (window_w - 12 * defense_cell) // 2,
                "defense_y": window_h - bottom_pad - 12 * defense_cell,
                "turn_y": top_margin,
                "fire_y": window_h - bottom_pad - fire_h,
            }

        # Cálculo horizontal para tableros de ataque
        side_pad = 20
        horizontal_budget = max(160, window_w - side_pad * 2)
        max_gap = 50
        min_gap = 4
        gap = max_gap
        if rivals_count > 1:
            max_total_gap = horizontal_budget - rivals_count * 8
            gap = min(max_gap, max(min_gap, max_total_gap // (rivals_count - 1)))

        attack_cell_w = max(6, (horizontal_budget - gap * max(0, rivals_count - 1)) // (12 * rivals_count))
        attack_cell_h = fit_board_cell_size(12, horizontal_budget, attack_budget, max_cell=25, min_cell=8)
        attack_cell = max(6, min(25, attack_cell_w, attack_cell_h))

        # Recalcular gap con el tamaño definitivo de celda
        if rivals_count > 1:
            used_by_boards = rivals_count * 12 * attack_cell
            leftover = horizontal_budget - used_by_boards
            gap = max(min_gap, min(max_gap, leftover // (rivals_count - 1)))
        else:
            gap = 0

        # Asegurar que todos los tableros de ataque caben horizontalmente
        max_attack_w = horizontal_budget
        total_attack_w = rivals_count * 12 * attack_cell + max(0, rivals_count - 1) * gap
        while total_attack_w > max_attack_w and attack_cell > 4:
            attack_cell -= 1
            if rivals_count > 1:
                used_by_boards = rivals_count * 12 * attack_cell
                leftover = horizontal_budget - used_by_boards
                gap = max(2, min(max_gap, leftover // (rivals_count - 1)))
            total_attack_w = rivals_count * 12 * attack_cell + max(0, rivals_count - 1) * gap

        if total_attack_w > max_attack_w and rivals_count > 1:
            used_by_boards = rivals_count * 12 * attack_cell
            max_possible_gap = (max_attack_w - used_by_boards) // (rivals_count - 1)
            gap = max(1, min(gap, max_possible_gap))

        total_attack_w = rivals_count * 12 * attack_cell + max(0, rivals_count - 1) * gap
        attack_start_x = max(side_pad, (window_w - total_attack_w) // 2)
        turn_y = top_margin
        attack_y = turn_y + turn_block_h + attack_label_h

        defense_w = 12 * defense_cell
        defense_x = (window_w - defense_w) // 2
        fire_y = window_h - bottom_pad - fire_h

        # Defensa encima del botón fuego
        defense_bottom_limit = fire_y - 10 if rivals_count > 0 else window_h - bottom_pad
        defense_y = defense_bottom_limit - 12 * defense_cell

        # Ajuste final por seguridad (si aún hay solape vertical)
        attack_bottom = attack_y + 12 * attack_cell
        min_defense_top = attack_bottom + 16 + defense_label_h
        if defense_y < min_defense_top:
            # Reducir primero defensa, luego ataque
            overlap = min_defense_top - defense_y
            reduce_def_cells = math.ceil(overlap / 12)
            new_defense_cell = max(8, defense_cell - reduce_def_cells)
            if new_defense_cell != defense_cell:
                defense_cell = new_defense_cell
                defense_w = 12 * defense_cell
                defense_x = (window_w - defense_w) // 2
                defense_y = defense_bottom_limit - 12 * defense_cell

            if defense_y < min_defense_top:
                # Reducir ataque si sigue justo
                overlap2 = min_defense_top - defense_y
                reduce_att_cells = math.ceil(overlap2 / 12)
                new_attack_cell = max(8, attack_cell - reduce_att_cells)
                if new_attack_cell != attack_cell:
                    attack_cell = new_attack_cell
                    if rivals_count > 1:
                        used_by_boards = rivals_count * 12 * attack_cell
                        leftover = horizontal_budget - used_by_boards
                        gap = max(min_gap, min(max_gap, leftover // (rivals_count - 1)))
                    total_attack_w = rivals_count * 12 * attack_cell + max(0, rivals_count - 1) * gap
                    attack_start_x = max(side_pad, (window_w - total_attack_w) // 2)
                    attack_bottom = attack_y + 12 * attack_cell
                    min_defense_top = attack_bottom + 16 + defense_label_h
                    defense_y = max(min_defense_top, defense_bottom_limit - 12 * defense_cell)

        return {
            "attack_cell": attack_cell,
            "attack_gap": gap,
            "attack_start_x": attack_start_x,
            "attack_y": attack_y,
            "defense_cell": defense_cell,
            "defense_x": defense_x,
            "defense_y": defense_y,
            "turn_y": turn_y,
            "fire_y": fire_y,
        }

    def update_ui_layout():
        # Menú principal
        menu_w, menu_h = 340, 52
        menu_gap = 18
        menu_total_h = menu_h * 2 + menu_gap
        menu_top = HEIGHT // 2 - menu_total_h // 2
        btn_create.rect = pygame.Rect(WIDTH // 2 - menu_w // 2, menu_top, menu_w, menu_h)
        btn_join.rect = pygame.Rect(WIDTH // 2 - menu_w // 2, menu_top + menu_h + menu_gap, menu_w, menu_h)

        # Crear sala
        form_w = min(440, max(320, WIDTH - 80))
        input_h = 44
        btn_small_w, btn_h = 170, 44
        vertical_base = HEIGHT // 2 - 90
        input_create_name.rect = pygame.Rect(WIDTH // 2 - form_w // 2, vertical_base - 36, form_w, input_h)
        input_create_room.rect = pygame.Rect(WIDTH // 2 - form_w // 2, vertical_base + 48, form_w, input_h)
        btn_create_back.rect = pygame.Rect(WIDTH // 2 - btn_small_w - 8, vertical_base + 110, btn_small_w, btn_h)
        btn_create_confirm.rect = pygame.Rect(WIDTH // 2 + 8, vertical_base + 110, btn_small_w, btn_h)

        # Sala creada
        big_btn_w = min(420, max(320, WIDTH - 90))
        btn_copy_hash.rect = pygame.Rect(WIDTH // 2 - big_btn_w // 2, HEIGHT // 2 + 30, big_btn_w, 44)
        btn_goto_lobby.rect = pygame.Rect(WIDTH // 2 - big_btn_w // 2, HEIGHT // 2 + 86, big_btn_w, 44)

        # Unirse a sala
        join_w = min(520, max(360, WIDTH - 90))
        join_base = HEIGHT // 2 - 90
        input_join_name.rect = pygame.Rect(WIDTH // 2 - join_w // 2, join_base - 36, join_w, input_h)
        input_join_room.rect = pygame.Rect(WIDTH // 2 - join_w // 2, join_base + 48, join_w, input_h)
        btn_join_back.rect = pygame.Rect(WIDTH // 2 - btn_small_w - 8, join_base + 110, btn_small_w, btn_h)
        btn_join_confirm.rect = pygame.Rect(WIDTH // 2 + 8, join_base + 110, btn_small_w, btn_h)

        # Lobby / batalla
        btn_start_lobby.rect = pygame.Rect(WIDTH // 2 - big_btn_w // 2, HEIGHT - 68, big_btn_w, 44)
        btn_fire.rect = pygame.Rect(WIDTH // 2 - 84, HEIGHT - 62, 168, 44)

        # Fase colocación: reescalar tablero para que quepa con márgenes e instrucciones
        if my_board and not battle_phase:
            top_space = max(120, font_title.get_height() + 50)
            bottom_space = 90
            available_w = WIDTH - 70
            available_h = HEIGHT - top_space - bottom_space
            cell = fit_board_cell_size(12, available_w, available_h, max_cell=32, min_cell=16)
            my_board.cell_size = cell
            board_px = 12 * cell
            my_board.x_offset = (WIDTH - board_px) // 2
            my_board.y_offset = top_space + max(0, (available_h - board_px) // 2)

        # Fase batalla: layout reactivo sin solapes
        if my_board and battle_phase:
            layout = compute_battle_layout(WIDTH, HEIGHT, len(attack_boards))
            btn_fire.rect.centerx = WIDTH // 2
            btn_fire.rect.y = layout["fire_y"]

            my_board.cell_size = layout["defense_cell"]
            my_board.x_offset = layout["defense_x"]
            my_board.y_offset = layout["defense_y"]

            for i, ab in enumerate(attack_boards):
                ab.cell_size = layout["attack_cell"]
                ab.x_offset = layout["attack_start_x"] + i * (12 * layout["attack_cell"] + layout["attack_gap"])
                ab.y_offset = layout["attack_y"]

    update_ui_layout()

    running = True
    while running:
        screen.fill(GRAY)
        update_ui_layout()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                new_w, new_h = clamp_window_size(*event.size)
                if (new_w, new_h) != (WIDTH, HEIGHT):
                    WIDTH, HEIGHT = new_w, new_h
                    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                    update_ui_layout()
            
            if current_state == STATE_MENU:
                if btn_create.handle_event(event):
                    current_state = STATE_CREATE_ROOM
                    input_create_room.text = ""
                if btn_join.handle_event(event):
                    current_state = STATE_JOIN_ROOM
                    input_join_room.text = ""
            
            elif current_state == STATE_CREATE_ROOM:
                input_create_name.handle_event(event)
                input_create_room.handle_event(event)
                if btn_create_confirm.handle_event(event):
                    room_name = input_create_room.text.strip()
                    player_name = input_create_name.text.strip()
                    if room_name and player_name:
                        room_hash_display = generate_room_hash(room_name)
                        is_host = True
                        net_manager = NetworkManager(room_hash_display, peer_id=player_name)
                        net_manager.on_message_received = on_message_received
                        net_manager.start()
                        current_state = STATE_ROOM_CREATED
                if btn_create_back.handle_event(event):
                    current_state = STATE_MENU
            
            elif current_state == STATE_ROOM_CREATED:
                if btn_copy_hash.handle_event(event):
                    if copy_to_clipboard(room_hash_display):
                        print(f"Hash copiado con éxito: {room_hash_display}")
                    else:
                        print("Error copiando: No se encontró wl-copy ni xclip en el sistema. Asegúrate de tener 'wl-clipboard' instalado.")
                if btn_goto_lobby.handle_event(event):
                    current_state = STATE_LOBBY
                    
            elif current_state == STATE_JOIN_ROOM:
                input_join_name.handle_event(event)
                input_join_room.handle_event(event)
                if btn_join_confirm.handle_event(event):
                    room_hash = input_join_room.text.strip()
                    player_name = input_join_name.text.strip()
                    if room_hash and player_name:
                        print(f"Conectando a sala con Hash/Topic: {room_hash}")
                        is_host = False
                        net_manager = NetworkManager(room_hash, peer_id=player_name)
                        net_manager.on_message_received = on_message_received
                        net_manager.start()
                        current_state = STATE_LOBBY
                if btn_join_back.handle_event(event):
                    current_state = STATE_MENU

            elif current_state == STATE_LOBBY:
                if is_host and btn_start_lobby.handle_event(event):
                    # El host decide empezar
                    players_list = list(net_manager.peers.keys())
                    net_manager.send_event("START_GAME", players=players_list)
                    
                    my_board = Board(WIDTH//2 - (12 * 30)//2, HEIGHT//2 - (12 * 30)//2)
                    has_committed_board = False
                    current_state = STATE_GAME
            
            elif current_state == STATE_GAME:
                if my_board and not battle_phase:
                    my_board.handle_event(event)
                    
                    if my_board.is_ready and not has_committed_board:
                        board_hash = my_board.get_board_hash()
                        print(f"Enviando COMMIT_BOARD: {board_hash}")
                        net_manager.send_event("COMMIT_BOARD", board_hash=board_hash)
                        has_committed_board = True
                        
                elif battle_phase:
                    is_my_turn = (all_players_sorted[current_turn_index] == net_manager.peer_id)
                    for ab in attack_boards:
                        ab.handle_event(event, is_my_turn)
                        
                    if is_my_turn and btn_fire.handle_event(event):
                        targets = []
                        for ab in attack_boards:
                            if ab.selected_coord:
                                targets.append({"target_peer": ab.target_peer_id, "coord": ab.get_selected_coord_str()})
                                
                        # Solo permitimos disparar si ha seleccionado en todos los rivales
                        if len(targets) == len(attack_boards):
                            net_manager.send_event("FIRE_MULTI", targets=targets)
                            current_turn_index = (current_turn_index + 1) % len(all_players_sorted)
                            print("[JUEGO] Disparos enviados.")

        # Procesar mensajes de red entrantes
        while not msg_queue.empty():
            msg = msg_queue.get()
            if msg.get("action") == "START_GAME":
                print(f"El Host ha iniciado la partida. Jugadores: {msg.get('players')}")
                my_board = Board(WIDTH//2 - (12 * 30)//2, HEIGHT//2 - (12 * 30)//2)
                has_committed_board = False
                current_state = STATE_GAME
            elif msg.get("action") == "COMMIT_BOARD":
                peer_id = msg.get("peerId")
                b_hash = msg.get("board_hash")
                player_commits[peer_id] = b_hash
                print(f"[JUEGO] El jugador {peer_id} ha fijado su flota.")
                
            elif msg.get("action") == "FIRE_MULTI":
                targets = msg.get("targets")
                sender = msg.get("peerId")
                
                if battle_phase:
                    current_turn_index = (current_turn_index + 1) % len(all_players_sorted)
                
                for t in targets:
                    if t["target_peer"] == net_manager.peer_id:
                        coord = t["coord"]
                        letters = "ABCDEFGHIJKL"
                        x = letters.index(coord[0])
                        y = int(coord[1:]) - 1
                        
                        hit = (my_board.grid[y][x] == 1 or my_board.grid[y][x] >= 3)
                        # Marcar en nuestro tablero sumando impactos
                        if my_board.grid[y][x] == 1:
                            my_board.grid[y][x] = 3
                        elif my_board.grid[y][x] >= 3:
                            my_board.grid[y][x] += 1
                        elif my_board.grid[y][x] == 0:
                            my_board.grid[y][x] = 2
                            
                        print(f"[JUEGO] Nos han disparado en {coord}. Tocado: {hit}")
                        net_manager.send_event("RESULT", target_peer=sender, coord=coord, hit=hit)
                        
            elif msg.get("action") == "RESULT":
                target_peer = msg.get("target_peer")
                coord = msg.get("coord")
                hit = msg.get("hit")
                sender = msg.get("peerId")
                
                if target_peer == net_manager.peer_id:
                    for ab in attack_boards:
                        if ab.target_peer_id == sender:
                            ab.apply_result(coord, hit)
                            print(f"[JUEGO] Resultado de ataque a {sender} en {coord}: {'Tocado' if hit else 'Agua'}")

        # Lógica de dibujado
        if current_state == STATE_MENU:
            title = font_title.render("Hundir la Flota P2P", True, BLACK)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, HEIGHT//4))
            btn_create.draw(screen)
            btn_join.draw(screen)
            
        elif current_state == STATE_CREATE_ROOM:
            title = font_title.render("Crear Nueva Sala", True, BLACK)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, max(26, input_create_name.rect.y - 110)))
            
            lbl_name = font_normal.render("Tu nombre:", True, BLACK)
            screen.blit(lbl_name, (input_create_name.rect.x, input_create_name.rect.y - 28))
            input_create_name.draw(screen)
            
            lbl_room = font_normal.render("Nombre / Semilla de sala:", True, BLACK)
            screen.blit(lbl_room, (input_create_room.rect.x, input_create_room.rect.y - 28))
            input_create_room.draw(screen)
            
            btn_create_confirm.draw(screen)
            btn_create_back.draw(screen)
            
        elif current_state == STATE_ROOM_CREATED:
            title = font_title.render("Sala Creada", True, BLACK)
            title_y = max(28, HEIGHT // 5 - 60)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, title_y))
            
            label = font_normal.render("Comparte este Hash con tus amigos para que se unan:", True, BLACK)
            label_y = title_y + 95
            screen.blit(label, (WIDTH//2 - label.get_width()//2, label_y))
            
            # Mostrar el hash (cortado si es muy largo, pero como es SHA256 son 64 chars)
            # Lo dividimos en dos líneas o usamos font_small
            hash_surf1 = font_small.render(room_hash_display[:32], True, DARK_BLUE)
            hash_surf2 = font_small.render(room_hash_display[32:], True, DARK_BLUE)
            screen.blit(hash_surf1, (WIDTH//2 - hash_surf1.get_width()//2, label_y + 46))
            screen.blit(hash_surf2, (WIDTH//2 - hash_surf2.get_width()//2, label_y + 73))
            
            btn_copy_hash.draw(screen)
            btn_goto_lobby.draw(screen)
            
        elif current_state == STATE_JOIN_ROOM:
            title = font_title.render("Unirse a la Sala", True, BLACK)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, max(26, input_join_name.rect.y - 110)))
            
            lbl_name = font_normal.render("Tu nombre:", True, BLACK)
            screen.blit(lbl_name, (input_join_name.rect.x, input_join_name.rect.y - 28))
            input_join_name.draw(screen)
            
            lbl_room = font_normal.render("Introduce el Hash / Semilla de la sala:", True, BLACK)
            screen.blit(lbl_room, (input_join_room.rect.x, input_join_room.rect.y - 28))
            input_join_room.draw(screen)
            
            btn_join_confirm.draw(screen)
            btn_join_back.draw(screen)
            
        elif current_state == STATE_LOBBY:
            title = font_title.render("Sala de Espera", True, BLACK)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, 50))
            
            # Listar jugadores
            list_top = 150
            line_h = font_normal.get_height() + 8
            controls_top = btn_start_lobby.rect.y if is_host else HEIGHT - 100
            max_lines = max(1, (controls_top - list_top - 12) // line_h)
            y_offset = list_top
            
            if net_manager:
                lines = [f"Tú: {net_manager.peer_id} " + ("(Host)" if is_host else "")]
                lines.extend([f"Jugador conectado: {peer_id}" for peer_id in net_manager.peers])

                visible = lines[:max_lines]
                hidden_count = max(0, len(lines) - len(visible))

                for i, txt in enumerate(visible):
                    color = DARK_BLUE if i == 0 else BLACK
                    peer_lbl = font_normal.render(txt, True, color)
                    screen.blit(peer_lbl, (WIDTH//2 - peer_lbl.get_width()//2, y_offset))
                    y_offset += line_h

                if hidden_count > 0:
                    extra_lbl = font_small.render(f"... y {hidden_count} jugador(es) más", True, (80, 80, 80))
                    screen.blit(extra_lbl, (WIDTH//2 - extra_lbl.get_width()//2, y_offset))
                    
            if is_host:
                btn_start_lobby.draw(screen)
            else:
                wait_lbl = font_normal.render("Esperando a que el host inicie la partida...", True, (100, 100, 100))
                screen.blit(wait_lbl, (WIDTH//2 - wait_lbl.get_width()//2, HEIGHT - 100))

        elif current_state == STATE_GAME:
            screen.fill((20, 20, 40))
            if not battle_phase:
                if my_board:
                    # El layout se calcula de forma reactiva en update_ui_layout
                    my_board.draw(screen, font_small)
                    
                    if my_board.is_ready:
                        ready_count = len(player_commits) + 1 # +1 por nosotros
                        total_players = len(net_manager.peers) + 1
                        
                        status_text = f"Jugadores listos: {ready_count} / {total_players}"
                        status_lbl = font_normal.render(status_text, True, (200, 200, 200))
                        screen.blit(status_lbl, (WIDTH//2 - status_lbl.get_width()//2, HEIGHT - 50))
                        
                        if ready_count == total_players:
                            battle_phase = True
                            all_players_sorted = sorted(list(net_manager.peers.keys()) + [net_manager.peer_id])
                            current_turn_index = 0

                            # Crear tableros de ataque
                            for p in net_manager.peers.keys():
                                attack_boards.append(AttackBoard(p, 0, 100)) # El offset x se calculará dinámicamente

                            update_ui_layout()

            else:
                # Dibujar fase de batalla con layout reactivo
                layout = compute_battle_layout(WIDTH, HEIGHT, len(attack_boards))

                # 1. Estado de turno (arriba)
                is_my_turn = (all_players_sorted[current_turn_index] == net_manager.peer_id)
                turn_player = all_players_sorted[current_turn_index]
                
                turn_text = "¡Es tu turno!" if is_my_turn else f"Turno de {turn_player}..."
                color = (50, 255, 50) if is_my_turn else (200, 200, 200)
                turn_lbl = font_title.render(turn_text, True, color)
                screen.blit(turn_lbl, (WIDTH//2 - turn_lbl.get_width()//2, layout["turn_y"]))

                # 2. Tableros de ataque (arriba-centro, sin solape)
                for ab in attack_boards:
                    ab.draw(screen, font_small, is_their_turn=(ab.target_peer_id == turn_player))

                # 3. Tablero propio de defensa (abajo, sin solape)
                my_lbl_color = (255, 255, 0) if is_my_turn else WHITE
                defense_label_y = my_board.y_offset - font_small.get_height() - 6
                lbl_defense = font_small.render("Tu tablero de defensa:", True, my_lbl_color)
                screen.blit(lbl_defense, (my_board.x_offset, defense_label_y))
                my_board.draw(screen, font_small, show_status_text=False)
                
                if is_my_turn:
                    btn_fire.draw(screen)
            
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
