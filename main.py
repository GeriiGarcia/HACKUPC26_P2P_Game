import pygame
import sys
import hashlib
import subprocess
import queue
import math

# local UI and network helpers
from ui import Button, TextInput
from network import NetworkManager

try:
    from BatleShip import BattleshipGame
except Exception:
    BattleshipGame = None

try:
    from kart import KartGame
except Exception:
    KartGame = None


def main():
    # All previous top-level code should be inside this main function.
    # We'll import and initialize commonly used globals here with safe defaults.
    pygame.init()

    # Basic window and UI defaults (will be adjusted later by the existing code)
    global WIDTH, HEIGHT, MIN_WIDTH, MIN_HEIGHT, FPS
    WIDTH, HEIGHT = 1280, 720
    MIN_WIDTH, MIN_HEIGHT = 640, 360
    FPS = 60

    # Colors
    global GRAY, BLUE, DARK_BLUE, WHITE, BLACK
    GRAY = (30, 30, 40)
    BLUE = (40, 120, 255)
    DARK_BLUE = (20, 80, 200)
    WHITE = (255, 255, 255)
    BLACK = (10, 10, 10)

    # Game states
    STATE_MENU = 0
    STATE_CREATE_ROOM = 1
    STATE_JOIN_ROOM = 2
    STATE_ROOM_CREATED = 3
    STATE_LOBBY = 4
    STATE_GAME = 5

    current_state = STATE_MENU

    # Battleship / game runtime placeholders (used by legacy inline logic)
    player_commits = {}
    my_board = None
    battle_phase = False
    game_over = False
    all_players_sorted = []
    current_turn_index = 0
    attack_boards = []
    eliminated_players = set()
    final_ranking = None
    winner_peer_id = None

    def generate_room_hash(room_name: str) -> str:
        return hashlib.sha256(room_name.encode('utf-8')).hexdigest()

    def on_message_received(msg):
        # Simple router for incoming network messages into the local queue
        try:
            msg_queue.put(msg)
        except Exception:
            pass

    def copy_to_clipboard(text: str) -> bool:
        # Try wl-copy, then xclip, then tkinter
        try:
            res = subprocess.run(['wl-copy'], input=text.encode('utf-8'), check=True)
            return True
        except Exception:
            pass
        try:
            res = subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode('utf-8'), check=True)
            return True
        except Exception:
            pass
        try:
            import tkinter as tk
            r = tk.Tk()
            r.withdraw()
            r.clipboard_clear()
            r.clipboard_append(text)
            r.update()
            r.destroy()
            return True
        except Exception:
            return False

    # Minimal placeholders for objects that other code expects to exist.
    global net_manager, msg_queue, battleship_game
    net_manager = None
    msg_queue = queue.Queue()
    battleship_game = None

    # Create a window and fonts used across the UI
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    font_small = pygame.font.SysFont(None, 18)
    font_normal = pygame.font.SysFont(None, 24)
    font_title = pygame.font.SysFont(None, 40)

    # The rest of the original file assumes many variables exist and will set them.
    # We'll continue executing the file from here (the remainder of the file)
    # Minimal UI elements expected by the rest of the code
    btn_create = Button(0, 0, 200, 44, "Crear Sala", font_normal, bg_color=BLUE)
    btn_join = Button(0, 0, 200, 44, "Unirse", font_normal)
    input_create_name = TextInput(0, 0, 360, 40, font_normal)
    input_create_room = TextInput(0, 0, 360, 40, font_normal)
    btn_create_back = Button(0, 0, 140, 40, "Volver", font_normal)
    btn_create_confirm = Button(0, 0, 140, 40, "Crear", font_normal, bg_color=BLUE)

    btn_copy_hash = Button(0, 0, 200, 40, "Copiar Hash", font_small)
    btn_player_count = Button(0, 0, 160, 40, "Players: 0", font_small)
    btn_game_battleships = Button(0, 0, 200, 160, "Battleships", font_normal, bg_color=(80,150,255))
    btn_game_karting = Button(0, 0, 200, 160, "Karting", font_normal, bg_color=(200,80,80))
    btn_start_game = Button(0, 0, 300, 56, "Start", font_normal, bg_color=BLUE)

    btn_start_lobby = Button(0, 0, 300, 44, "Iniciar partida", font_normal, bg_color=BLUE)
    btn_fire = Button(0, 0, 168, 44, "Fuego!", font_normal, bg_color=(200,40,40))

    # Join inputs (ensure exist)
    input_join_name = TextInput(WIDTH//2 - 200, HEIGHT//2 - 120, 400, 40, font_normal)
    input_join_room = TextInput(WIDTH//2 - 200, HEIGHT//2 - 30, 400, 40, font_normal)
    btn_join_confirm = Button(WIDTH//2 + 10, HEIGHT//2 + 40, 140, 40, "Unirse", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)
    btn_join_back = Button(WIDTH//2 - 150, HEIGHT//2 + 40, 140, 40, "Volver", font_normal)

    # State variables
    selected_game = None
    show_players_list = False
    room_hash_display = ""
    
    # Elemento UI - Fin de partida
    btn_end_to_menu = Button(WIDTH//2 - 140, HEIGHT - 80, 280, 44, "Volver al menú principal", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)

    # Elementos UI - Unirse a Sala
    input_join_name = TextInput(WIDTH//2 - 200, HEIGHT//2 - 120, 400, 40, font_normal)
    input_join_room = TextInput(WIDTH//2 - 200, HEIGHT//2 - 30, 400, 40, font_normal)
    btn_join_confirm = Button(WIDTH//2 + 10, HEIGHT//2 + 40, 140, 40, "Unirse", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)
    btn_join_back = Button(WIDTH//2 - 150, HEIGHT//2 + 40, 140, 40, "Volver", font_normal)

    def clamp_window_size(w, h):
        return max(MIN_WIDTH, w), max(MIN_HEIGHT, h)

    def reset_match_state():
        global battleship_game
        # discard any active Battleship manager and reset
        if battleship_game:
            try:
                # allow BattleshipGame to perform its cleanup if it has a method
                pass
            except Exception:
                pass
        battleship_game = None

    def return_to_main_menu():
        global current_state, net_manager, is_host
        if net_manager:
            net_manager.stop()
        net_manager = None
        is_host = False
        # clear any active battleship manager
        global battleship_game
        battleship_game = None

        while not msg_queue.empty():
            try:
                msg_queue.get_nowait()
            except Exception:
                break

        reset_match_state()
        current_state = STATE_MENU

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

        # Sala creada / responsive layout for top, middle, bottom areas
        big_btn_w = min(420, max(320, WIDTH - 90))
        # Top-left copy button
        btn_copy_hash.rect = pygame.Rect(16, 12, min(260, WIDTH//4), 40)
        # Top-right player count
        btn_player_count.rect = pygame.Rect(WIDTH - 16 - min(260, WIDTH//4), 12, min(260, WIDTH//4), 40)

        # Middle big buttons (side by side)
        mid_btn_w = min(320, max(240, (WIDTH - 140) // 2))
        mid_btn_h = min(200, max(120, HEIGHT//3))
        btn_game_battleships.rect = pygame.Rect(WIDTH//2 - mid_btn_w - 20, HEIGHT//2 - mid_btn_h//2, mid_btn_w, mid_btn_h)
        btn_game_karting.rect = pygame.Rect(WIDTH//2 + 20, HEIGHT//2 - mid_btn_h//2, mid_btn_w, mid_btn_h)

        # Bottom start button
        btn_start_game.rect = pygame.Rect(WIDTH//2 - 150, HEIGHT - 80, 300, 56)

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
        btn_end_to_menu.rect = pygame.Rect(WIDTH // 2 - 170, HEIGHT - 74, 340, 46)

        # Fase colocación: reescalar tablero para que quepa con márgenes e instrucciones
        if battleship_game and battleship_game.my_board and not battleship_game.battle_phase:
            top_space = max(120, font_title.get_height() + 50)
            bottom_space = 90
            available_w = WIDTH - 70
            available_h = HEIGHT - top_space - bottom_space
            cell = fit_board_cell_size(12, available_w, available_h, max_cell=32, min_cell=16)
            battleship_game.my_board.cell_size = cell
            board_px = 12 * cell
            battleship_game.my_board.x_offset = (WIDTH - board_px) // 2
            battleship_game.my_board.y_offset = top_space + max(0, (available_h - board_px) // 2)

        # Fase batalla: layout reactivo sin solapes
        if battleship_game and battleship_game.my_board and battleship_game.battle_phase:
            layout = compute_battle_layout(WIDTH, HEIGHT, len(battleship_game.attack_boards))
            btn_fire.rect.centerx = WIDTH // 2
            btn_fire.rect.y = layout["fire_y"]

            battleship_game.my_board.cell_size = layout["defense_cell"]
            battleship_game.my_board.x_offset = layout["defense_x"]
            battleship_game.my_board.y_offset = layout["defense_y"]

            for i, ab in enumerate(battleship_game.attack_boards):
                ab.cell_size = layout["attack_cell"]
                ab.x_offset = layout["attack_start_x"] + i * (12 * layout["attack_cell"] + layout["attack_gap"])
                ab.y_offset = layout["attack_y"]

            if battleship_game.game_over:
                panel_w = min(560, max(360, WIDTH - 120))
                panel_h = min(420, max(260, HEIGHT - 120))
                panel_x = (WIDTH - panel_w) // 2
                panel_y = (HEIGHT - panel_h) // 2
                btn_end_to_menu.rect = pygame.Rect(panel_x + panel_w // 2 - 170, panel_y + panel_h - 52, 340, 40)

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
                # Top buttons
                if btn_copy_hash.handle_event(event):
                    if copy_to_clipboard(room_hash_display):
                        print(f"Hash copiado con éxito: {room_hash_display}")
                    else:
                        print("Error copiando: No se encontró wl-copy ni xclip en el sistema. Asegúrate de tener 'wl-clipboard' instalado.")

                if btn_player_count.handle_event(event):
                    show_players_list = not show_players_list

                # Middle: select game
                if btn_game_battleships.handle_event(event):
                    selected_game = 'battleship'
                if btn_game_karting.handle_event(event):
                    selected_game = 'karting'

                # Bottom: start selected game
                if btn_start_game.handle_event(event):
                    if selected_game is None:
                        print("Select a game first (Battleship or Karting)")
                    elif selected_game == 'battleship':
                        # host starts battleship
                        if net_manager:
                            try:
                                players_list = list(net_manager.peers.keys())
                                net_manager.send_event("START_GAME", players=players_list)
                            except Exception:
                                pass
                        # initialize Battleship manager and start placement
                        battleship_game = BattleshipGame(net_manager)
                        battleship_game.start_placement(WIDTH, HEIGHT, cell_size=30)
                        current_state = STATE_GAME
                    elif selected_game == 'karting':
                        if KartGame is None:
                            print("KartGame not available (failed to import kart module).")
                        elif net_manager:
                            try:
                                game = KartGame(net_manager=net_manager)
                                try:
                                    game.run()
                                finally:
                                    try:
                                        net_manager.stop()
                                    except Exception:
                                        pass
                                    net_manager = None
                                    is_host = False
                                    current_state = STATE_MENU
                            except Exception as e:
                                print("Failed to start KartGame:", e)
                    
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
                    # initialize Battleship manager and start placement
                    battleship_game = BattleshipGame(net_manager)
                    battleship_game.start_placement(WIDTH, HEIGHT, cell_size=30)
                    current_state = STATE_GAME
            
            elif current_state == STATE_GAME:
                # Delegate event handling to BattleshipGame if present
                if battleship_game:
                    battleship_game.handle_event(event)
                    # if battle_phase and it's our turn and we pressed fire button, send FIRE_MULTI
                    if battleship_game.battle_phase:
                        turn_owner = battleship_game.all_players_sorted[battleship_game.current_turn_index] if battleship_game.all_players_sorted else None
                        is_my_turn = (not battleship_game.game_over and turn_owner == getattr(net_manager, 'peer_id', None) and getattr(net_manager, 'peer_id', None) not in battleship_game.eliminated_players)
                        if is_my_turn and btn_fire.handle_event(event):
                            targets = []
                            for ab in battleship_game.attack_boards:
                                if not ab.is_eliminated and ab.selected_coord:
                                    targets.append({"target_peer": ab.target_peer_id, "coord": ab.get_selected_coord_str()})
                            active_attack_boards = [ab for ab in battleship_game.attack_boards if not ab.is_eliminated]
                            if len(targets) == len(active_attack_boards) and len(active_attack_boards) > 0 and net_manager:
                                net_manager.send_event("FIRE_MULTI", targets=targets)
                                battleship_game.advance_turn_to_next_alive()
                                print("[JUEGO] Disparos enviados.")
                else:
                    # fallback to previous inline logic (if BattleshipGame not created)
                    pass

        # Procesar mensajes de red entrantes
        while not msg_queue.empty():
            msg = msg_queue.get()
            # If battleship_game is active, let it handle relevant actions
            if battleship_game:
                try:
                    battleship_game.on_network_message(msg)
                except Exception:
                    pass
                # allow other message handlers to run below if needed
                continue
            # fallback inline handling (kept for compatibility if battleship_game not created)
            if msg.get("action") == "START_GAME":
                print(f"El Host ha iniciado la partida. Jugadores: {msg.get('players')}")
                # create Battleship manager if not already
                if not battleship_game:
                    battleship_game = BattleshipGame(net_manager)
                    battleship_game.start_placement(WIDTH, HEIGHT, cell_size=30)
                current_state = STATE_GAME
            elif msg.get("action") == "COMMIT_BOARD":
                peer_id = msg.get("peerId")
                b_hash = msg.get("board_hash")
                player_commits[peer_id] = b_hash
                print(f"[JUEGO] El jugador {peer_id} ha fijado su flota.")
                
            elif msg.get("action") == "FIRE_MULTI":
                targets = msg.get("targets") or []
                sender = msg.get("peerId")
                
                if battle_phase and not game_over and sender and sender not in eliminated_players:
                    if sender in all_players_sorted:
                        current_turn_index = all_players_sorted.index(sender)
                    advance_turn_to_next_alive()
                
                for t in targets:
                    if t["target_peer"] == net_manager.peer_id:
                        coord = t["coord"]
                        try:
                            x, y = coord_to_idx(coord)
                        except Exception:
                            continue

                        shot_result = my_board.receive_shot(x, y)
                        hit = shot_result.get("hit", False)
                        sunk = shot_result.get("sunk", False)
                        sunk_cells = shot_result.get("sunk_cells", [])
                        eliminated_now = shot_result.get("eliminated", False)
                        sunk_cells_coord = coord_list_from_cells(sunk_cells)

                        info = "HUNDIDO" if sunk else ("Tocado" if hit else "Agua")
                        print(f"[JUEGO] Nos han disparado en {coord}. Resultado: {info}")

                        net_manager.send_event(
                            "RESULT",
                            target_peer=sender,
                            coord=coord,
                            hit=hit,
                            sunk=sunk,
                            sunk_cells=sunk_cells_coord,
                            eliminated=eliminated_now,
                            eliminated_peer=net_manager.peer_id if eliminated_now else None,
                        )

                        if eliminated_now:
                            print(f"[JUEGO] {net_manager.peer_id} ha sido eliminado.")
                            announce_elimination(net_manager.peer_id, source="local")

            elif msg.get("action") == "RESULT":
                target_peer = msg.get("target_peer")
                coord = msg.get("coord")
                hit = msg.get("hit")
                sender = msg.get("peerId")
                sunk = msg.get("sunk", False)
                sunk_cells = msg.get("sunk_cells") or []
                eliminated_flag = msg.get("eliminated", False)
                eliminated_peer = msg.get("eliminated_peer") or sender

                # Estado compartido: todos los jugadores ven impactos/hundimientos.
                for ab in attack_boards:
                    if ab.target_peer_id == sender:
                        if coord:
                            ab.apply_result(coord, hit, sunk=sunk)
                        if sunk and sunk_cells:
                            ab.apply_sunk_cells(sunk_cells)

                if target_peer == net_manager.peer_id:
                    status_txt = "HUNDIDO" if sunk else ("Tocado" if hit else "Agua")
                    print(f"[JUEGO] Resultado de ataque a {sender} en {coord}: {status_txt}")

                if eliminated_flag and eliminated_peer:
                    announce_elimination(eliminated_peer, source="remote")

            elif msg.get("action") == "PLAYER_ELIMINATED":
                eliminated_peer = msg.get("eliminated_peer") or msg.get("peerId")
                if eliminated_peer:
                    announce_elimination(eliminated_peer, source="remote")

            elif msg.get("action") == "GAME_OVER":
                winner_peer = msg.get("winner_peer")
                ranking = msg.get("ranking") or []
                if ranking:
                    game_over = True
                    final_ranking = ranking
                    winner_peer_id = winner_peer or ranking[0]
                elif winner_peer:
                    game_over = True
                    winner_peer_id = winner_peer
                    final_ranking = build_final_ranking()

        # Lógica de dibujado
        # If using BattleshipGame manager, check if we should transition to battle
        if battleship_game and not battleship_game.battle_phase:
            try:
                # Debug: print commit status
                try:
                    pc = getattr(battleship_game, 'player_commits', {})
                    hc = getattr(battleship_game, 'has_committed_board', False)
                    peers_count = (len(net_manager.peers) + 1) if net_manager else 1
                    print(f"[DEBUG] commits={len(pc)} has_committed={hc} peers_total={peers_count}")
                except Exception:
                    pass

                started = battleship_game.start_battle_if_ready()
                if started:
                    print("[JUEGO] Todos listos — iniciando fase de batalla.")
                    current_state = STATE_GAME
                    update_ui_layout()
            except Exception:
                pass

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
            # Top: copy hash (left), Lobby title + hash (center), player count (right)
            # Left: copy button
            btn_copy_hash.draw(screen)

            # Center title and hash
            title = font_title.render("Lobby", True, BLACK)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, 12))
            # hash below title (split into two lines)
            hash_surf1 = font_small.render(room_hash_display[:32], True, DARK_BLUE)
            hash_surf2 = font_small.render(room_hash_display[32:], True, DARK_BLUE)
            screen.blit(hash_surf1, (WIDTH//2 - hash_surf1.get_width()//2, 12 + title.get_height() + 6))
            screen.blit(hash_surf2, (WIDTH//2 - hash_surf2.get_width()//2, 12 + title.get_height() + 6 + hash_surf1.get_height()))

            # Right: player count button
            # Update count label
            if net_manager:
                count = 1 + len(net_manager.peers)
            else:
                count = 0
            btn_player_count.text = f"Players: {count}"
            btn_player_count.draw(screen)

            # Middle: large game selection
            btn_game_battleships.draw(screen)
            btn_game_karting.draw(screen)
            # Highlight selection
            if selected_game == 'battleship':
                pygame.draw.rect(screen, (255,255,255), btn_game_battleships.rect, 4)
            elif selected_game == 'karting':
                pygame.draw.rect(screen, (255,255,255), btn_game_karting.rect, 4)

            # Player list popup
            if show_players_list:
                # draw simple panel on the right under the player button
                panel_w = 300
                panel_h = 24 + (len(net_manager.peers) + 1) * 28 if net_manager else 80
                panel_x = WIDTH - panel_w - 16
                panel_y = 16 + btn_player_count.rect.height + 8
                pygame.draw.rect(screen, (240,240,240), (panel_x, panel_y, panel_w, panel_h))
                pygame.draw.rect(screen, (100,100,100), (panel_x, panel_y, panel_w, panel_h), 2)
                # list entries
                y = panel_y + 8
                if net_manager:
                    me_lbl = font_small.render(f"You: {net_manager.peer_id}", True, (30,30,30))
                    screen.blit(me_lbl, (panel_x + 8, y))
                    y += 28
                    for p in net_manager.peers:
                        lbl = font_small.render(p, True, (30,30,30))
                        screen.blit(lbl, (panel_x + 8, y))
                        y += 28

            # Bottom: start button
            btn_start_game.draw(screen)
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
            # If we have a BattleshipGame manager, delegate drawing to it
            if battleship_game:
                try:
                    battleship_game.draw(screen, font_small, font_normal, font_title, WIDTH, HEIGHT)
                except Exception:
                    pass

                # draw fire button if it's our turn
                if getattr(battleship_game, 'battle_phase', False) and not getattr(battleship_game, 'game_over', False) and net_manager:
                    turn_owner = battleship_game.all_players_sorted[battleship_game.current_turn_index] if battleship_game.all_players_sorted else None
                    is_my_turn = (turn_owner == getattr(net_manager, 'peer_id', None) and getattr(net_manager, 'peer_id', None) not in battleship_game.eliminated_players)
                    if is_my_turn:
                        btn_fire.draw(screen)

                # draw end-to-menu button when game over
                if getattr(battleship_game, 'game_over', False):
                    btn_end_to_menu.draw(screen)

            else:
                # Legacy inline battleship drawing (kept for compatibility)
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
                    ensure_current_turn_is_alive()

                    # 1. Estado de turno (arriba)
                    turn_player = all_players_sorted[current_turn_index] if all_players_sorted else None
                    i_am_eliminated = (net_manager.peer_id in eliminated_players)
                    is_my_turn = (not game_over and not i_am_eliminated and turn_player == net_manager.peer_id)

                    if game_over:
                        turn_text = f"🏆 Ganador: {winner_peer_id}" if winner_peer_id else "Partida terminada"
                        color = (255, 215, 80)
                    elif i_am_eliminated:
                        turn_text = "Has sido eliminado"
                        color = (255, 120, 120)
                    else:
                        turn_text = "¡Es tu turno!" if is_my_turn else f"Turno de {turn_player}..."
                        color = (50, 255, 50) if is_my_turn else (200, 200, 200)

                    turn_lbl = font_title.render(turn_text, True, color)
                    screen.blit(turn_lbl, (WIDTH//2 - turn_lbl.get_width()//2, layout["turn_y"]))

                    # 2. Tableros de ataque (arriba-centro, sin solape)
                    for ab in attack_boards:
                        ab.draw(screen, font_small, is_their_turn=(ab.target_peer_id == turn_player))

                    # 3. Tablero propio de defensa (abajo, sin solape)
                    my_lbl_color = (255, 120, 120) if i_am_eliminated else ((255, 255, 0) if is_my_turn else WHITE)
                    defense_label_y = my_board.y_offset - font_small.get_height() - 6
                    defense_label_txt = "Tu tablero de defensa" + (" (ELIMINADO)" if i_am_eliminated else ":")
                    lbl_defense = font_small.render(defense_label_txt, True, my_lbl_color)
                    screen.blit(lbl_defense, (my_board.x_offset, defense_label_y))
                    my_board.draw(screen, font_small, show_status_text=False)
                    
                    if is_my_turn:
                        btn_fire.draw(screen)

                    if game_over:
                        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                        overlay.fill((10, 10, 20, 170))
                        screen.blit(overlay, (0, 0))

                        panel_w = min(560, max(360, WIDTH - 120))
                        panel_h = min(420, max(260, HEIGHT - 120))
                        panel_x = (WIDTH - panel_w) // 2
                        panel_y = (HEIGHT - panel_h) // 2
                        panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
                        pygame.draw.rect(screen, (30, 35, 55), panel_rect, border_radius=10)
                        pygame.draw.rect(screen, (230, 230, 230), panel_rect, 2, border_radius=10)

                        title = font_title.render("Fin de la partida", True, (255, 255, 255))
                        screen.blit(title, (panel_x + panel_w // 2 - title.get_width() // 2, panel_y + 18))

                        winner_text = f"Ganador: {winner_peer_id}" if winner_peer_id else "Ganador: (desconocido)"
                        winner_lbl = font_normal.render(winner_text, True, (255, 215, 80))
                        screen.blit(winner_lbl, (panel_x + panel_w // 2 - winner_lbl.get_width() // 2, panel_y + 86))

                        ranking_title = font_normal.render("Clasificación final", True, (220, 220, 220))
                        screen.blit(ranking_title, (panel_x + 30, panel_y + 136))

                        ranking_lines = final_ranking if final_ranking else build_final_ranking()
                        line_h = font_small.get_height() + 8
                        start_y = panel_y + 176
                        for i, player in enumerate(ranking_lines, start=1):
                            is_me = (net_manager and player == net_manager.peer_id)
                            c = (255, 255, 150) if is_me else (240, 240, 240)
                            line = font_small.render(f"{pos_label(i)}  {player}" + ("  (tú)" if is_me else ""), True, c)
                            screen.blit(line, (panel_x + 36, start_y + (i - 1) * line_h))

                        if net_manager and net_manager.peer_id in ranking_lines:
                            my_pos = ranking_lines.index(net_manager.peer_id) + 1
                            pos_lbl = font_normal.render(f"Tu posición: {pos_label(my_pos)}", True, (180, 255, 180))
                            screen.blit(pos_lbl, (panel_x + panel_w // 2 - pos_lbl.get_width() // 2, panel_y + panel_h - 98))

                        btn_end_to_menu.draw(screen)
            
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
