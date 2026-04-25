import pygame
import sys
import hashlib
import subprocess
import queue
import time
import json
import os
from pygame.locals import *
from ui import Button, TextInput
from network import NetworkManager
from mascota_core import Pet
from mascota_render import Renderer

INVENTORY_SAVE_FILE = "pets.json" # Cambiado a pets.json

def load_all_pets():
    if os.path.exists(INVENTORY_SAVE_FILE):
        try:
            with open(INVENTORY_SAVE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_all_pets(data):
    try:
        with open(INVENTORY_SAVE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error guardando mascotas: {e}")

# Configuración básica
WIDTH, HEIGHT = 800, 600
FPS = 60
MIN_WIDTH, MIN_HEIGHT = 760, 560

# Colores UI
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
    return hashlib.sha256(room_name.encode('utf-8')).hexdigest()

def copy_to_clipboard(text):
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
    pygame.display.set_caption("Tamagotchi en Red P2P")
    clock = pygame.time.Clock()

    font_title = pygame.font.SysFont(None, 64)
    font_normal = pygame.font.SysFont(None, 36)
    font_small = pygame.font.SysFont(None, 24)

    current_state = STATE_MENU

    net_manager = None
    is_host = False
    msg_queue = queue.Queue()
    
    # Variables de la Mascota
    renderer = None
    pets = {} # peer_id -> Pet object
    last_move_send = 0
    saved_pets = load_all_pets()  # {room_hash: {peer_name: {pet data}}}
    
    def on_message_received(msg):
        msg_queue.put(msg)

    def save_my_pet():
        if not net_manager or not room_hash_display:
            return
        room_key = room_hash_display
        if room_key not in saved_pets:
            saved_pets[room_key] = {}
        
        # Guardar MI mascota cifrada
        if net_manager.peer_id in pets:
            my_pet = pets[net_manager.peer_id]
            pet_data = my_pet.serialize_state()
            encrypted = net_manager.encrypt_for_me(pet_data)
            if encrypted:
                saved_pets[room_key][net_manager.peer_id] = {"encrypted": encrypted}
            else:
                saved_pets[room_key][net_manager.peer_id] = pet_data
        
        # Guardar mascotas de OTROS jugadores en texto plano
        for pid, p in pets.items():
            if pid != net_manager.peer_id:
                saved_pets[room_key][pid] = p.serialize_state()
        
        save_all_pets(saved_pets)

    def restore_pet(peer_id):
        room_key = room_hash_display
        if room_key in saved_pets and peer_id in saved_pets[room_key]:
            stored = saved_pets[room_key][peer_id]
            if peer_id in pets:
                if isinstance(stored, dict) and "encrypted" in stored:
                    if net_manager and peer_id == net_manager.peer_id:
                        data = net_manager.decrypt_for_me(stored["encrypted"])
                        if data:
                            pets[peer_id].deserialize_state(data)
                            print(f"[MASCOTA] Restaurada mascota cifrada de {peer_id}")
                            return
                    print(f"[MASCOTA] Mascota de {peer_id} está cifrada")
                else:
                    pets[peer_id].deserialize_state(stored)
                    print(f"[MASCOTA] Restaurada mascota de {peer_id}")

    def on_peer_connected(peer_id):
        if current_state == STATE_GAME:
            pet_data = saved_pets.get(room_hash_display, {})
            net_manager.send_event("LATE_JOIN_SYNC", 
                                   target_peer=peer_id, 
                                   players=list(pets.keys()), 
                                   pets_data=pet_data)
            if peer_id not in pets:
                pets[peer_id] = Pet(peer_id)
                restore_pet(peer_id)

    def on_peer_disconnected(peer_id):
        if peer_id in pets:
            save_my_pet()
            del pets[peer_id]
            print(f"[GAME] Mascota de {peer_id} ha salido")

    # UI Elementos
    btn_create = Button(WIDTH//2 - 150, HEIGHT//2 - 50, 300, 50, "Crear Sala", font_normal)
    btn_join = Button(WIDTH//2 - 150, HEIGHT//2 + 20, 300, 50, "Unirse a Sala", font_normal)

    input_create_name = TextInput(WIDTH//2 - 150, HEIGHT//2 - 120, 300, 40, font_normal)
    input_create_room = TextInput(WIDTH//2 - 150, HEIGHT//2 - 30, 300, 40, font_normal)
    btn_create_confirm = Button(WIDTH//2 + 10, HEIGHT//2 + 40, 140, 40, "Crear", font_normal, bg_color=BLUE)
    btn_create_back = Button(WIDTH//2 - 150, HEIGHT//2 + 40, 140, 40, "Volver", font_normal)
    
    room_hash_display = ""
    btn_copy_hash = Button(WIDTH//2 - 150, HEIGHT//2 + 20, 300, 40, "Copiar Hash", font_normal)
    btn_goto_lobby = Button(WIDTH//2 - 150, HEIGHT//2 + 80, 300, 40, "Ir a Lobby", font_normal, bg_color=BLUE)

    btn_start_lobby = Button(WIDTH//2 - 150, HEIGHT - 100, 300, 40, "Empezar", font_normal, bg_color=(50, 200, 50))

    input_join_name = TextInput(WIDTH//2 - 200, HEIGHT//2 - 120, 400, 40, font_normal)
    input_join_room = TextInput(WIDTH//2 - 200, HEIGHT//2 - 30, 400, 40, font_normal)
    btn_join_confirm = Button(WIDTH//2 + 10, HEIGHT//2 + 40, 140, 40, "Unirse", font_normal, bg_color=BLUE)
    btn_join_back = Button(WIDTH//2 - 150, HEIGHT//2 + 40, 140, 40, "Volver", font_normal)

    def clamp_window_size(w, h):
        return max(MIN_WIDTH, w), max(MIN_HEIGHT, h)

    def update_ui_layout():
        if current_state == STATE_GAME:
            if renderer: renderer.resize(WIDTH, HEIGHT)
            return
            
        menu_w, menu_h = 340, 52
        menu_top = HEIGHT // 2 - (menu_h * 2 + 18) // 2
        btn_create.rect = pygame.Rect(WIDTH // 2 - menu_w // 2, menu_top, menu_w, menu_h)
        btn_join.rect = pygame.Rect(WIDTH // 2 - menu_w // 2, menu_top + menu_h + 18, menu_w, menu_h)

        form_w = min(440, max(320, WIDTH - 80))
        btn_small_w, btn_h = 170, 44
        vertical_base = HEIGHT // 2 - 90
        input_create_name.rect = pygame.Rect(WIDTH // 2 - form_w // 2, vertical_base - 36, form_w, 44)
        input_create_room.rect = pygame.Rect(WIDTH // 2 - form_w // 2, vertical_base + 48, form_w, 44)
        btn_create_back.rect = pygame.Rect(WIDTH // 2 - btn_small_w - 8, vertical_base + 110, btn_small_w, btn_h)
        btn_create_confirm.rect = pygame.Rect(WIDTH // 2 + 8, vertical_base + 110, btn_small_w, btn_h)

        big_btn_w = min(420, max(320, WIDTH - 90))
        btn_copy_hash.rect = pygame.Rect(WIDTH // 2 - big_btn_w // 2, HEIGHT // 2 + 30, big_btn_w, 44)
        btn_goto_lobby.rect = pygame.Rect(WIDTH // 2 - big_btn_w // 2, HEIGHT // 2 + 86, big_btn_w, 44)

        join_w = min(520, max(360, WIDTH - 90))
        join_base = HEIGHT // 2 - 90
        input_join_name.rect = pygame.Rect(WIDTH // 2 - join_w // 2, join_base - 36, join_w, 44)
        input_join_room.rect = pygame.Rect(WIDTH // 2 - join_w // 2, join_base + 48, join_w, 44)
        btn_join_back.rect = pygame.Rect(WIDTH // 2 - btn_small_w - 8, join_base + 110, btn_small_w, btn_h)
        btn_join_confirm.rect = pygame.Rect(WIDTH // 2 + 8, join_base + 110, btn_small_w, btn_h)

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
                    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                    update_ui_layout()
            
            if current_state == STATE_MENU:
                if btn_create.handle_event(event):
                    current_state = STATE_CREATE_ROOM
                if btn_join.handle_event(event):
                    current_state = STATE_JOIN_ROOM
            
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
                    copy_to_clipboard(room_hash_display)
                if btn_goto_lobby.handle_event(event):
                    current_state = STATE_LOBBY
                    
            elif current_state == STATE_JOIN_ROOM:
                input_join_name.handle_event(event)
                input_join_room.handle_event(event)
                if btn_join_confirm.handle_event(event):
                    room_hash = input_join_room.text.strip()
                    player_name = input_join_name.text.strip()
                    if room_hash and player_name:
                        room_hash_display = room_hash
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
                    players_list = list(net_manager.peers.keys())
                    net_manager.send_event("START_GAME", players=players_list)
                    
                    pets.clear()
                    pets[net_manager.peer_id] = Pet(net_manager.peer_id)
                    restore_pet(net_manager.peer_id)
                    for p in players_list:
                        pets[p] = Pet(p)
                        restore_pet(p)
                        
                    renderer = Renderer(WIDTH, HEIGHT, font_normal)
                    current_state = STATE_GAME
            
            elif current_state == STATE_GAME:
                # Interacciones con la mascota y UI
                action = renderer.handle_event(event)
                if action and net_manager.peer_id in pets:
                    my_pet = pets[net_manager.peer_id]
                    # Aplicar la accion localmente
                    if action == "feed": my_pet.feed()
                    elif action == "play": my_pet.play()
                    elif action == "sleep": my_pet.sleep()
                    elif action == "clean": my_pet.clean()
                    
                    # Notificar a los demas que hice una acción
                    net_manager.send_event("PET_ACTION", target_peer=net_manager.peer_id, action_type=action)

        # Procesar mensajes de red entrantes
        while not msg_queue.empty():
            msg = msg_queue.get()
            action = msg.get("action")
            sender = msg.get("peerId")
            
            if action == "START_GAME":
                pets.clear()
                pets[net_manager.peer_id] = Pet(net_manager.peer_id)
                restore_pet(net_manager.peer_id)
                for p in msg.get("players", []):
                    pets[p] = Pet(p)
                    restore_pet(p)
                renderer = Renderer(WIDTH, HEIGHT, font_normal)
                current_state = STATE_GAME
                
            elif action == "LATE_JOIN_SYNC":
                if msg.get("target_peer") == net_manager.peer_id and current_state != STATE_GAME:
                    pets.clear()
                    pets[net_manager.peer_id] = Pet(net_manager.peer_id)
                    for p in msg.get("players", []):
                        if p != net_manager.peer_id:
                            pets[p] = Pet(p)
                    
                    pets_data = msg.get("pets_data", {})
                    if pets_data:
                        room_key = room_hash_display
                        if room_key not in saved_pets:
                            saved_pets[room_key] = {}
                        saved_pets[room_key].update(pets_data)
                        save_all_pets(saved_pets)
                    
                    restore_pet(net_manager.peer_id)
                    for p in pets:
                        if p != net_manager.peer_id:
                            restore_pet(p)
                            
                    renderer = Renderer(WIDTH, HEIGHT, font_normal)
                    current_state = STATE_GAME

            elif action == "PET_UPDATE" and current_state == STATE_GAME:
                if sender and sender not in pets:
                    pets[sender] = Pet(sender)
                    restore_pet(sender)
                if sender in pets:
                    pet_data = msg.get("pet_data", {})
                    pets[sender].deserialize_state(pet_data)
                    
            elif action == "PET_ACTION" and current_state == STATE_GAME:
                target = msg.get("target_peer")
                act_type = msg.get("action_type")
                if target in pets:
                    # Aplicar la accion visualmente para mantener sincronía
                    if act_type == "feed": pets[target].feed()
                    elif act_type == "play": pets[target].play()
                    elif act_type == "sleep": pets[target].sleep()
                    elif act_type == "clean": pets[target].clean()

        # Lógica de dibujado
        if current_state == STATE_MENU:
            title = font_title.render("Tamagotchi P2P", True, BLACK)
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
            label = font_normal.render("Comparte este Hash con tus amigos:", True, BLACK)
            label_y = title_y + 95
            screen.blit(label, (WIDTH//2 - label.get_width()//2, label_y))
            hash_surf1 = font_small.render(room_hash_display[:32], True, DARK_BLUE)
            hash_surf2 = font_small.render(room_hash_display[32:], True, DARK_BLUE)
            screen.blit(hash_surf1, (WIDTH//2 - hash_surf1.get_width()//2, label_y + 46))
            screen.blit(hash_surf2, (WIDTH//2 - hash_surf2.get_width()//2, label_y + 73))
            btn_copy_hash.draw(screen)
            btn_goto_lobby.draw(screen)
            
        elif current_state == STATE_JOIN_ROOM:
            title = font_title.render("Unirse a Sala", True, BLACK)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, max(26, input_join_name.rect.y - 110)))
            lbl_name = font_normal.render("Tu nombre:", True, BLACK)
            screen.blit(lbl_name, (input_join_name.rect.x, input_join_name.rect.y - 28))
            input_join_name.draw(screen)
            lbl_room = font_normal.render("Introduce el Hash:", True, BLACK)
            screen.blit(lbl_room, (input_join_room.rect.x, input_join_room.rect.y - 28))
            input_join_room.draw(screen)
            btn_join_confirm.draw(screen)
            btn_join_back.draw(screen)
            
        elif current_state == STATE_LOBBY:
            title = font_title.render("Sala de Espera", True, BLACK)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, 50))
            if net_manager:
                y_offset = 150
                for i, peer_id in enumerate([net_manager.peer_id] + list(net_manager.peers.keys())):
                    color = DARK_BLUE if i == 0 else BLACK
                    lbl = font_normal.render(peer_id + (" (Tú)" if i==0 else ""), True, color)
                    screen.blit(lbl, (WIDTH//2 - lbl.get_width()//2, y_offset))
                    y_offset += 40
                    
            if is_host:
                btn_start_lobby.draw(screen)
            else:
                wait_lbl = font_normal.render("Esperando al host...", True, (100, 100, 100))
                screen.blit(wait_lbl, (WIDTH//2 - wait_lbl.get_width()//2, HEIGHT - 100))

        elif current_state == STATE_GAME:
            dt = clock.get_time() / 1000.0
            my_pet = pets.get(net_manager.peer_id)
            
            for pid, pet in pets.items():
                if pid == net_manager.peer_id:
                    pet.update(dt)
                else:
                    # En red actualizamos visualmente su timer e interpolación mínima
                    pet.update(dt)
                    
            if my_pet:
                now = time.time()
                if now - last_move_send > 0.1: # Sync 10 veces por sec
                    net_manager.send_event("PET_UPDATE", pet_data=my_pet.serialize_state())
                    last_move_send = now
                
                # Auto-save cada 5 segundos
                if int(now) % 5 == 0 and int(now) != getattr(main, '_last_pet_save', 0):
                    main._last_pet_save = int(now)
                    save_my_pet()

            if renderer:
                renderer.render(screen, pets, net_manager.peer_id)
            
        pygame.display.flip()
        clock.tick(FPS)

    save_my_pet()
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
