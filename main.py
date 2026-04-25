import pygame
import sys
import hashlib
import subprocess
import queue
import math
import random
import time
import json
import os
from pygame.locals import *
from ui import Button, TextInput
from network import NetworkManager
from minecraft_core import World, Player, B_AIR, B_DIRT, B_STONE, B_WOOD, B_WHEAT, B_GRASS, B_SAND
from minecraft_render import Renderer, BLOCK_SIZE_PX

INVENTORY_SAVE_FILE = "inventories.json"

def load_all_inventories():
    if os.path.exists(INVENTORY_SAVE_FILE):
        try:
            with open(INVENTORY_SAVE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_all_inventories(data):
    try:
        with open(INVENTORY_SAVE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error guardando inventarios: {e}")

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
    pygame.display.set_caption("Minecraft P2P 2D")
    clock = pygame.time.Clock()

    font_title = pygame.font.SysFont(None, 64)
    font_normal = pygame.font.SysFont(None, 36)
    font_small = pygame.font.SysFont(None, 24)

    current_state = STATE_MENU

    net_manager = None
    is_host = False
    msg_queue = queue.Queue()
    
    # Variables de Partida Minecraft
    world = None
    renderer = None
    players = {} # peer_id -> Player object
    world_seed = 0
    last_move_send = 0
    input_dx = 0
    input_jump = False
    input_tab_held = False
    input_inventory_open = False
    saved_inventories = load_all_inventories()  # {room_hash: {peer_name: {inventory data}}}
    
    def set_opengl_mode():
        global WIDTH, HEIGHT
        return pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE | pygame.DOUBLEBUF | pygame.OPENGL)

    def on_message_received(msg):
        msg_queue.put(msg)

    def save_my_inventory():
        """Guarda el inventario del jugador local a disco, cifrado con su clave pública RSA."""
        if not net_manager or not room_hash_display:
            return
        room_key = room_hash_display
        if room_key not in saved_inventories:
            saved_inventories[room_key] = {}
        
        # Guardar MI inventario cifrado
        if net_manager.peer_id in players:
            my_p = players[net_manager.peer_id]
            inv_data = my_p.serialize_inventory()
            encrypted = net_manager.encrypt_for_me(inv_data)
            if encrypted:
                saved_inventories[room_key][net_manager.peer_id] = {"encrypted": encrypted}
            else:
                saved_inventories[room_key][net_manager.peer_id] = inv_data
        
        # Guardar inventarios de OTROS jugadores en texto plano (para que al reconectar lo vean)
        for pid, p in players.items():
            if pid != net_manager.peer_id and p.inventory:
                saved_inventories[room_key][pid] = p.serialize_inventory()
        
        save_all_inventories(saved_inventories)

    def restore_inventory(peer_id):
        """Restaura inventario guardado si existe, descifrando con clave privada."""
        room_key = room_hash_display
        if room_key in saved_inventories and peer_id in saved_inventories[room_key]:
            stored = saved_inventories[room_key][peer_id]
            if peer_id in players:
                if isinstance(stored, dict) and "encrypted" in stored:
                    # Descifrar con mi clave privada (solo funciona para MI inventario)
                    if net_manager and peer_id == net_manager.peer_id:
                        data = net_manager.decrypt_for_me(stored["encrypted"])
                        if data:
                            players[peer_id].deserialize_inventory(data)
                            print(f"[INVENTARIO] Restaurado inventario cifrado de {peer_id}")
                            return
                    # Si no somos nosotros, no podemos descifrar (así se protege)
                    print(f"[INVENTARIO] Inventario de {peer_id} está cifrado (solo él puede leerlo)")
                else:
                    # Datos en texto plano (legacy)
                    players[peer_id].deserialize_inventory(stored)
                    print(f"[INVENTARIO] Restaurado inventario de {peer_id}")

    def get_all_saved_inventories_for_room():
        room_key = room_hash_display
        return saved_inventories.get(room_key, {})

    def on_peer_connected(peer_id):
        if current_state == STATE_GAME and world:
            # Cualquier jugador ya en partida envía el sync (no solo el host)
            modified = world.get_modified_blocks_list()
            inv_data = get_all_saved_inventories_for_room()
            net_manager.send_event("LATE_JOIN_SYNC", 
                                   target_peer=peer_id, 
                                   seed=world_seed, 
                                   players=list(players.keys()), 
                                   modified_blocks=modified,
                                   inventories=inv_data)
            if peer_id not in players:
                players[peer_id] = Player()
                restore_inventory(peer_id)

    def on_peer_disconnected(peer_id):
        """Callback cuando un peer se desconecta: guardar su inventario y quitarlo de pantalla."""
        if peer_id in players:
            # Guardar su inventario antes de quitarlo
            save_my_inventory()
            del players[peer_id]
            print(f"[GAME] Jugador {peer_id} ha salido del juego")

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

    def update_ui_layout():
        if current_state == STATE_GAME:
            return
            
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

    update_ui_layout()

    running = True
    while running:
        if current_state != STATE_GAME:
            screen.fill(GRAY)
            update_ui_layout()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                new_w, new_h = clamp_window_size(*event.size)
                if (new_w, new_h) != (WIDTH, HEIGHT):
                    WIDTH, HEIGHT = new_w, new_h
                    if current_state == STATE_GAME:
                        screen = set_opengl_mode()
                        if renderer:
                            renderer.setup_opengl(WIDTH, HEIGHT)
                    else:
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
                        net_manager.on_peer_connected = on_peer_connected
                        net_manager.on_peer_disconnected = on_peer_disconnected
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
                        room_hash_display = room_hash  # Fijar el room_hash para el joiner
                        is_host = False
                        net_manager = NetworkManager(room_hash, peer_id=player_name)
                        net_manager.on_message_received = on_message_received
                        net_manager.on_peer_connected = on_peer_connected
                        net_manager.on_peer_disconnected = on_peer_disconnected
                        net_manager.start()
                        current_state = STATE_LOBBY
                if btn_join_back.handle_event(event):
                    current_state = STATE_MENU

            elif current_state == STATE_LOBBY:
                if is_host and btn_start_lobby.handle_event(event):
                    # El host decide empezar
                    players_list = list(net_manager.peers.keys())
                    world_seed = random.random() * 1000
                    net_manager.send_event("START_GAME", players=players_list, seed=world_seed)
                    
                    world = World(seed=world_seed)
                    players.clear()
                    players[net_manager.peer_id] = Player()
                    for p in players_list:
                        players[p] = Player()
                        
                    screen = set_opengl_mode()
                    renderer = Renderer(WIDTH, HEIGHT)
                    current_state = STATE_GAME
            
            elif current_state == STATE_GAME:
                if event.type == KEYDOWN:
                    if event.key == K_a: input_dx = -1
                    elif event.key == K_d: input_dx = 1
                    elif event.key == K_SPACE: input_jump = True
                    elif event.key == K_TAB: input_tab_held = True
                    elif event.key == K_e: input_inventory_open = not input_inventory_open
                    # Seleccion de items (1-4)
                    elif event.key == K_1: players[net_manager.peer_id].selected_item = B_DIRT
                    elif event.key == K_2: players[net_manager.peer_id].selected_item = B_STONE
                    elif event.key == K_3: players[net_manager.peer_id].selected_item = B_WOOD
                    elif event.key == K_4: players[net_manager.peer_id].selected_item = B_WHEAT
                elif event.type == KEYUP:
                    if event.key == K_a and input_dx == -1: input_dx = 0
                    elif event.key == K_d and input_dx == 1: input_dx = 0
                    elif event.key == K_SPACE: input_jump = False
                    elif event.key == K_TAB: input_tab_held = False
                elif event.type == MOUSEBUTTONDOWN:
                    my_player = players.get(net_manager.peer_id)
                    if my_player and renderer:
                        mx, my_y = event.pos

                        # --- Hotbar slot click (left button) ---
                        if event.button == 1:
                            clicked_item = renderer.hotbar_slot_hit(mx, my_y, my_player.inventory)
                            if clicked_item is not None:
                                my_player.selected_item = clicked_item
                                continue  # don't process as a world click

                        # --- World block interaction ---
                        blocks_x = WIDTH / BLOCK_SIZE_PX
                        blocks_y = HEIGHT / BLOCK_SIZE_PX
                        cam_x = max(0, min(my_player.x - blocks_x / 2.0, 400 - blocks_x))
                        cam_y = max(0, min(my_player.y - blocks_y / 2.0, 400 - blocks_y))

                        world_x = int(mx / BLOCK_SIZE_PX + cam_x)
                        world_y = int(my_y / BLOCK_SIZE_PX + cam_y)

                        action = "break" if event.button == 1 else ("place" if event.button == 3 else None)
                        if action:

                            if my_player.interact_block(world, world_x, world_y, action):
                                new_b = world.get_block(world_x, world_y)
                                net_manager.send_event("BLOCK_UPDATE", x=world_x, y=world_y, type=new_b)

        # Procesar mensajes de red entrantes
        while not msg_queue.empty():
            msg = msg_queue.get()
            action = msg.get("action")
            sender = msg.get("peerId")
            
            if action == "START_GAME":
                world_seed = msg.get("seed", 0)
                print(f"El Host ha iniciado la partida. Jugadores: {msg.get('players')}")
                world = World(seed=world_seed)
                players.clear()
                players[net_manager.peer_id] = Player()
                for p in msg.get("players", []):
                    players[p] = Player()
                screen = set_opengl_mode()
                renderer = Renderer(WIDTH, HEIGHT)
                current_state = STATE_GAME
                
            elif action == "LATE_JOIN_SYNC":
                if msg.get("target_peer") == net_manager.peer_id and current_state != STATE_GAME:
                    world_seed = msg.get("seed", 0)
                    print(f"Sincronizando partida iniciada. Seed: {world_seed}")
                    world = World(seed=world_seed)
                    players.clear()
                    players[net_manager.peer_id] = Player()
                    for p in msg.get("players", []):
                        if p != net_manager.peer_id:
                            players[p] = Player()
                    world.apply_modified_blocks(msg.get("modified_blocks", []))
                    # Restaurar inventarios recibidos
                    inv_data = msg.get("inventories", {})
                    if inv_data:
                        room_key = room_hash_display
                        if room_key not in saved_inventories:
                            saved_inventories[room_key] = {}
                        saved_inventories[room_key].update(inv_data)
                        save_all_inventories(saved_inventories)
                    # Restaurar mi propio inventario
                    restore_inventory(net_manager.peer_id)
                    screen = set_opengl_mode()
                    renderer = Renderer(WIDTH, HEIGHT)
                    current_state = STATE_GAME

            elif action == "BLOCK_UPDATE" and current_state == STATE_GAME:
                x = msg.get("x")
                y = msg.get("y")
                b_type = msg.get("type")
                if world and x is not None and y is not None:
                    world.set_block(x, y, b_type)
                    
            elif action == "PLAYER_MOVE" and current_state == STATE_GAME:
                # Crear jugador si no lo conocíamos (reconexión o late join)
                if sender and sender not in players:
                    players[sender] = Player()
                    restore_inventory(sender)
                if sender in players:
                    players[sender].x = msg.get("x", players[sender].x)
                    players[sender].y = msg.get("y", players[sender].y)
                    players[sender].vx = msg.get("vx", players[sender].vx)
                    players[sender].vy = msg.get("vy", players[sender].vy)

        # Lógica de dibujado
        if current_state == STATE_MENU:
            title = font_title.render("Minecraft P2P", True, BLACK)
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
            dt = clock.get_time() / 1000.0
            my_player = players.get(net_manager.peer_id)
            if world:
                for pid, p in players.items():
                    if pid == net_manager.peer_id:
                        p.update(dt, world, input_dx, input_jump)
                    else:
                        # Interpolación / Client-side prediction para movimiento fluido
                        p.x += p.vx * dt
                        p.y += p.vy * dt
                        
            if my_player and world:
                # Send position to other players
                now = time.time()
                if now - last_move_send > 0.05: # Send 20 times a second
                    net_manager.send_event("PLAYER_MOVE", x=my_player.x, y=my_player.y, vx=my_player.vx, vy=my_player.vy)
                    last_move_send = now
                
                # Auto-save inventory every 10 seconds
                if int(now) % 10 == 0 and int(now) != getattr(main, '_last_inv_save', 0):
                    main._last_inv_save = int(now)
                    save_my_inventory()

            if renderer and world:
                renderer.render(world, players, net_manager.peer_id, input_tab_held, input_inventory_open, font_normal)
            
        pygame.display.flip()
        clock.tick(FPS)

    # Guardar inventario antes de salir
    save_my_inventory()
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
