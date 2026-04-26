import asyncio
import pygame
import sys
import hashlib
import queue
import time
import json
import os
from pygame.locals import *
from ui import Button, TextInput
from network import NetworkManager
from mascota_core import Pet
from mascota_render import Renderer

print("[WASM] main_mascota.py cargado y listo para iniciar main()")

INVENTORY_SAVE_FILE = "pets.json" 

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

WIDTH, HEIGHT = 800, 600
FPS = 60
MIN_WIDTH, MIN_HEIGHT = 760, 560

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
BLUE = (100, 150, 255)
DARK_BLUE = (50, 100, 200)

STATE_MENU = 0
STATE_CREATE_ROOM = 1
STATE_JOIN_ROOM = 2
STATE_ROOM_CREATED = 3
STATE_GAME = 4
STATE_LOBBY = 5

def generate_room_hash(room_name):
    return hashlib.sha256(room_name.encode('utf-8')).hexdigest()

def copy_to_clipboard(text):
    if sys.platform == 'emscripten':
        try:
            from platform import window
            window.navigator.clipboard.writeText(text)
            return True
        except:
            return False
    else:
        import subprocess
        try:
            subprocess.run(['wl-copy'], input=text.encode('utf-8'), check=True, stderr=subprocess.DEVNULL)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            try:
                subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode('utf-8'), check=True, stderr=subprocess.DEVNULL)
                return True
            except (FileNotFoundError, subprocess.CalledProcessError):
                return False

class MascotaGame:
    def __init__(self, screen, net_manager, room_hash=""):
        self.screen = screen
        self.net = net_manager
        self.room_hash = room_hash
        self.renderer = None
        self.pets = {}
        self.last_move_send = 0
        self.saved_pets = load_all_pets()
        self.font_normal = pygame.font.Font(None, 36)
        self.setup_game()

    def setup_game(self):
        self.pets.clear()
        if self.net:
            self.pets[self.net.peer_id] = Pet(self.net.peer_id)
            self.restore_pet(self.net.peer_id)
            for p in self.net.peers:
                self.pets[p] = Pet(p)
                self.restore_pet(p)
        else:
            self.pets['local'] = Pet('local')
        self.renderer = Renderer(self.screen.get_width(), self.screen.get_height(), self.font_normal)

    def save_my_pet(self):
        if not self.net or not self.room_hash: return
        room_key = self.room_hash
        if room_key not in self.saved_pets: self.saved_pets[room_key] = {}
        if self.net.peer_id in self.pets:
            my_pet = self.pets[self.net.peer_id]
            pet_data = my_pet.serialize_state()
            encrypted = self.net.encrypt_for_me(pet_data)
            if encrypted: self.saved_pets[room_key][self.net.peer_id] = {"encrypted": encrypted}
            else: self.saved_pets[room_key][self.net.peer_id] = pet_data
        for pid, p in self.pets.items():
            if pid != self.net.peer_id: self.saved_pets[room_key][pid] = p.serialize_state()
        save_all_pets(self.saved_pets)

    def restore_pet(self, peer_id):
        room_key = self.room_hash
        if room_key in self.saved_pets and peer_id in self.saved_pets[room_key]:
            stored = self.saved_pets[room_key][peer_id]
            if peer_id in self.pets:
                if isinstance(stored, dict) and "encrypted" in stored:
                    if self.net and peer_id == self.net.peer_id:
                        data = self.net.decrypt_for_me(stored["encrypted"])
                        if data: self.pets[peer_id].deserialize_state(data)
                else: self.pets[peer_id].deserialize_state(stored)

    def on_peer_connected(self, peer_id):
        if not self.net: return
        pet_data = self.saved_pets.get(self.room_hash, {})
        self.net.send_event("LATE_JOIN_SYNC", target_peer=peer_id, players=list(self.pets.keys()), pets_data=pet_data)
        if peer_id not in self.pets:
            self.pets[peer_id] = Pet(peer_id)
            self.restore_pet(peer_id)

    def on_peer_disconnected(self, peer_id):
        if peer_id in self.pets:
            self.save_my_pet()
            del self.pets[peer_id]

    def handle_event(self, event):
        if not self.renderer: return
        action = self.renderer.handle_event(event)
        if action and self.net and self.net.peer_id in self.pets:
            my_pet = self.pets[self.net.peer_id]
            if action == "feed": my_pet.feed()
            elif action == "play": my_pet.play()
            elif action == "sleep": my_pet.sleep()
            elif action == "clean": my_pet.clean()
            self.net.send_event("PET_ACTION", target_peer=self.net.peer_id, action_type=action)

    def update(self, dt):
        if not self.net: return
        for pid, pet in self.pets.items(): pet.update(dt)
        my_pet = self.pets.get(self.net.peer_id)
        if my_pet:
            now = time.time()
            if now - self.last_move_send > 0.1: 
                self.net.send_event("PET_UPDATE", pet_data=my_pet.serialize_state())
                self.last_move_send = now
            if int(now) % 5 == 0 and int(now) != getattr(self, '_last_pet_save', 0):
                self._last_pet_save = int(now)
                self.save_my_pet()

    def draw(self):
        if self.renderer and self.net:
            self.renderer.render(self.screen, self.pets, self.net.peer_id)

    def on_message(self, msg):
        action = msg.get("action")
        sender = msg.get("peerId")
        if action == "LATE_JOIN_SYNC":
            if msg.get("target_peer") == self.net.peer_id:
                self.pets.clear()
                self.pets[self.net.peer_id] = Pet(self.net.peer_id)
                for p in msg.get("players", []):
                    if p != self.net.peer_id: self.pets[p] = Pet(p)
                pets_data = msg.get("pets_data", {})
                if pets_data:
                    room_key = self.room_hash
                    if room_key not in self.saved_pets: self.saved_pets[room_key] = {}
                    self.saved_pets[room_key].update(pets_data)
                    save_all_pets(self.saved_pets)
                self.restore_pet(self.net.peer_id)
                for p in self.pets:
                    if p != self.net.peer_id: self.restore_pet(p)
                self.renderer = Renderer(self.screen.get_width(), self.screen.get_height(), self.font_normal)
        elif action == "PET_UPDATE":
            if sender and sender not in self.pets:
                self.pets[sender] = Pet(sender)
                self.restore_pet(sender)
            if sender in self.pets:
                pet_data = msg.get("pet_data", {})
                self.pets[sender].deserialize_state(pet_data)
        elif action == "PET_ACTION":
            target = msg.get("target_peer")
            act_type = msg.get("action_type")
            if target in self.pets:
                if act_type == "feed": self.pets[target].feed()
                elif act_type == "play": self.pets[target].play()
                elif act_type == "sleep": self.pets[target].sleep()
                elif act_type == "clean": self.pets[target].clean()

async def main():
    try:
        global WIDTH, HEIGHT
        pygame.init()
        print("[WASM] Pygame inicializado")
        screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Tamagotchi P2P - WASM")
        clock = pygame.time.Clock()
        
        font_title = pygame.font.Font(None, 64)
        font_normal = pygame.font.Font(None, 36)
        
        current_state = STATE_MENU
        net_manager = None
        is_host = False
        msg_queue = queue.Queue()
        room_hash_display = ""
        game_instance = None

        def on_message_received(msg):
            if game_instance: game_instance.on_message(msg)
            else: msg_queue.put(msg)

        btn_create = Button(WIDTH//2 - 150, HEIGHT//2 - 50, 300, 50, "Crear Sala", font_normal)
        btn_join = Button(WIDTH//2 - 150, HEIGHT//2 + 20, 300, 50, "Unirse a Sala", font_normal)
        input_create_name = TextInput(WIDTH//2 - 150, HEIGHT//2 - 120, 300, 40, font_normal)
        input_create_room = TextInput(WIDTH//2 - 150, HEIGHT//2 - 30, 300, 40, font_normal)
        btn_create_confirm = Button(WIDTH//2 + 10, HEIGHT//2 + 40, 140, 40, "Crear", font_normal, bg_color=BLUE)
        btn_create_back = Button(WIDTH//2 - 150, HEIGHT//2 + 40, 140, 40, "Volver", font_normal)
        btn_copy_hash = Button(WIDTH//2 - 150, HEIGHT//2 + 20, 300, 40, "Copiar Hash", font_normal)
        btn_goto_lobby = Button(WIDTH//2 - 150, HEIGHT//2 + 80, 300, 40, "Ir a Lobby", font_normal, bg_color=BLUE)
        btn_start_lobby = Button(WIDTH//2 - 150, HEIGHT - 100, 300, 40, "Empezar", font_normal, bg_color=(50, 200, 50))
        input_join_name = TextInput(WIDTH//2 - 200, HEIGHT//2 - 120, 400, 40, font_normal)
        input_join_room = TextInput(WIDTH//2 - 200, HEIGHT//2 - 30, 400, 40, font_normal)
        btn_join_confirm = Button(WIDTH//2 + 10, HEIGHT//2 + 40, 140, 40, "Unirse", font_normal, bg_color=BLUE)
        btn_join_back = Button(WIDTH//2 - 150, HEIGHT//2 + 40, 140, 40, "Volver", font_normal)

        print(f"[WASM] Juego iniciado. Estado: {current_state}")

        running = True
        _last_log = 0
        while running:
            dt = clock.tick(FPS) / 1000.0
            if current_state != STATE_GAME: screen.fill(GRAY)
            
            now = time.time()
            if int(now) % 5 == 0 and int(now) != _last_log:
                _last_log = int(now)
                print(f"[WASM] Loop activo - Estado actual: {current_state}")

            for event in pygame.event.get():
                if event.type == pygame.QUIT: running = False
                
                if current_state == STATE_GAME: game_instance.handle_event(event)
                elif current_state == STATE_MENU:
                    if btn_create.handle_event(event): current_state = STATE_CREATE_ROOM
                    if btn_join.handle_event(event): current_state = STATE_JOIN_ROOM
                elif current_state == STATE_CREATE_ROOM:
                    input_create_name.handle_event(event); input_create_room.handle_event(event)
                    if btn_create_confirm.handle_event(event):
                        room_hash_display = generate_room_hash(input_create_room.text.strip())
                        is_host = True
                        net_manager = NetworkManager(room_hash_display, peer_id=input_create_name.text.strip())
                        net_manager.on_message_received = on_message_received
                        net_manager.start()
                        current_state = STATE_ROOM_CREATED
                    if btn_create_back.handle_event(event): current_state = STATE_MENU
                elif current_state == STATE_ROOM_CREATED:
                    if btn_copy_hash.handle_event(event): copy_to_clipboard(room_hash_display)
                    if btn_goto_lobby.handle_event(event): current_state = STATE_LOBBY
                elif current_state == STATE_JOIN_ROOM:
                    input_join_name.handle_event(event); input_join_room.handle_event(event)
                    if btn_join_confirm.handle_event(event):
                        room_hash_display = input_join_room.text.strip()
                        net_manager = NetworkManager(room_hash_display, peer_id=input_join_name.text.strip())
                        net_manager.on_message_received = on_message_received
                        net_manager.start()
                        current_state = STATE_LOBBY
                    if btn_join_back.handle_event(event): current_state = STATE_MENU
                elif current_state == STATE_LOBBY:
                    if is_host and btn_start_lobby.handle_event(event):
                        net_manager.send_event("START_GAME")
                        game_instance = MascotaGame(screen, net_manager, room_hash=room_hash_display)
                        current_state = STATE_GAME
                
            while not msg_queue.empty():
                msg = msg_queue.get()
                if msg.get("action") == "START_GAME":
                    game_instance = MascotaGame(screen, net_manager, room_hash=room_hash_display)
                    current_state = STATE_GAME

            if current_state == STATE_GAME:
                game_instance.update(dt)
                game_instance.draw()
            else:
                if current_state == STATE_MENU:
                    title = font_title.render("Tamagotchi P2P", True, BLACK)
                    screen.blit(title, (WIDTH//2 - title.get_width()//2, HEIGHT//4))
                    btn_create.draw(screen); btn_join.draw(screen)
                elif current_state == STATE_CREATE_ROOM:
                    input_create_name.draw(screen); input_create_room.draw(screen)
                    btn_create_confirm.draw(screen); btn_create_back.draw(screen)
                elif current_state == STATE_ROOM_CREATED:
                    btn_copy_hash.draw(screen); btn_goto_lobby.draw(screen)
                elif current_state == STATE_JOIN_ROOM:
                    input_join_name.draw(screen); input_join_room.draw(screen)
                    btn_join_confirm.draw(screen); btn_join_back.draw(screen)
                elif current_state == STATE_LOBBY:
                    text_lobby = font_normal.render("Esperando en Lobby...", True, BLACK)
                    screen.blit(text_lobby, (WIDTH//2 - text_lobby.get_width()//2, HEIGHT//2))
                    if is_host: btn_start_lobby.draw(screen)

            pygame.display.flip()
            await asyncio.sleep(0)

        if game_instance: game_instance.save_my_pet()
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pygame.quit()

if __name__ == "__main__":
    asyncio.run(main())
