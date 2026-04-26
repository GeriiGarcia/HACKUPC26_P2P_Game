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
from ui import Button, TextInput, CraftingMenu
from network import NetworkManager
from minecraft_core import World, Player, B_AIR, B_DIRT, B_STONE, B_WOOD, B_WHEAT, B_GRASS, B_SAND, B_CHEST, I_CHEST, CRAFTING_RECIPES, ITEM_NAMES, Chest
from minecraft_render import Renderer, BLOCK_SIZE_PX

INVENTORY_SAVE_FILE = "inventories.json"
CHESTS_SAVE_FILE = "chests.json"

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

def load_all_chests():
    """Carga todos los cofres guardados encriptados."""
    if os.path.exists(CHESTS_SAVE_FILE):
        try:
            with open(CHESTS_SAVE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_all_chests(data):
    """Guarda todos los cofres encriptados."""
    try:
        with open(CHESTS_SAVE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error guardando cofres: {e}")

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


class MinecraftGame:
    def __init__(self, screen, net_manager, clock, seed=None, room_hash=""):
        self.screen = screen
        self.net = net_manager
        self.clock = clock
        self.room_hash = room_hash
        
        # Game State
        self.world = None
        self.renderer = None
        self.players = {} # peer_id -> Player object
        self.world_seed = seed if seed is not None else random.random() * 1000
        self.last_move_send = 0
        self.input_dx = 0
        self.input_jump = False
        self.input_tab_held = False
        self.input_inventory_open = False
        
        # Advanced Features
        self.saved_inventories = load_all_inventories()
        self.saved_chests = load_all_chests()
        self.crafting_menu = CraftingMenu(CRAFTING_RECIPES, ITEM_NAMES)
        self.chests = {} # chest_id -> Chest
        self.open_chest_id = None
        
        self.font_normal = pygame.font.SysFont(None, 36)
        
        self.setup_game()

    def setup_game(self):
        self.world = World(seed=self.world_seed)
        self.players.clear()
        if self.net:
            self.players[self.net.peer_id] = Player()
            # Initialize other known peers
            for p in self.net.peers:
                self.players[p] = Player()
                self.restore_inventory(p)
            self.restore_inventory(self.net.peer_id)
        else:
            self.players['local'] = Player()
            
        self.restore_chests()
        surf = pygame.display.get_surface()
        self.renderer = Renderer(surf.get_width(), surf.get_height())

    def save_my_inventory(self):
        if not self.net or not self.room_hash:
            return
        room_key = self.room_hash
        if room_key not in self.saved_inventories:
            self.saved_inventories[room_key] = {}
        
        if self.net.peer_id in self.players:
            my_p = self.players[self.net.peer_id]
            inv_data = my_p.serialize_inventory()
            encrypted = self.net.encrypt_for_me(inv_data)
            if encrypted:
                self.saved_inventories[room_key][self.net.peer_id] = {"encrypted": encrypted}
            else:
                self.saved_inventories[room_key][self.net.peer_id] = inv_data
        
        save_all_inventories(self.saved_inventories)

    def restore_inventory(self, peer_id):
        room_key = self.room_hash
        if room_key in self.saved_inventories and peer_id in self.saved_inventories[room_key]:
            stored = self.saved_inventories[room_key][peer_id]
            if peer_id in self.players:
                if isinstance(stored, dict) and "encrypted" in stored:
                    if self.net and peer_id == self.net.peer_id:
                        data = self.net.decrypt_for_me(stored["encrypted"])
                        if data:
                            self.players[peer_id].deserialize_inventory(data)
                            print(f"[INVENTARIO] Restaurado inventario cifrado de {peer_id}")
                            return
                    print(f"[INVENTARIO] Inventario de {peer_id} está cifrado")
                else:
                    self.players[peer_id].deserialize_inventory(stored)
                    print(f"[INVENTARIO] Restaurado inventario de {peer_id}")

    def save_my_chests(self):
        if not self.net or not self.room_hash:
            return
        room_key = self.room_hash
        if room_key not in self.saved_chests:
            self.saved_chests[room_key] = {}

        prev_room_data = self.saved_chests.get(room_key, {})
        room_data = {}

        for cid, chest in self.chests.items():
            entry = {
                "owner_peer_id": chest.owner_peer_id,
                "position": [int(chest.position[0]), int(chest.position[1])],
            }
            if chest.owner_peer_id == self.net.peer_id:
                encrypted = self.net.encrypt_chest(chest.serialize())
                if encrypted:
                    entry["encrypted"] = encrypted
            else:
                prev_entry = prev_room_data.get(cid, {})
                if isinstance(prev_entry, dict) and "encrypted" in prev_entry:
                    entry["encrypted"] = prev_entry["encrypted"]
            room_data[cid] = entry

        self.saved_chests[room_key] = room_data
        save_all_chests(self.saved_chests)

    def restore_chests(self):
        room_key = self.room_hash
        self.chests = {}
        if room_key in self.saved_chests:
            for cid, cdata in self.saved_chests[room_key].items():
                try:
                    if isinstance(cdata, dict) and "owner_peer_id" in cdata and "position" in cdata:
                        owner = cdata.get("owner_peer_id")
                        pos = cdata.get("position", [0, 0])
                        px, py = int(pos[0]), int(pos[1])
                        chest = Chest(cid, owner, position=(px, py))
                        encrypted = cdata.get("encrypted")
                        if encrypted and self.net and owner == self.net.peer_id:
                            data = self.net.decrypt_chest(encrypted)
                            if data:
                                chest = Chest.deserialize(data)
                                chest.chest_id = cid
                                chest.owner_peer_id = owner
                                chest.position = (px, py)
                        self.chests[cid] = chest
                    else:
                        self.chests[cid] = Chest.deserialize(cdata)
                except Exception as e:
                    print(f"[CHEST] Error restaurando cofre {cid}: {e}")

    def broadcast_chest_update(self, chest):
        if not self.net or chest.owner_peer_id != self.net.peer_id:
            return
        encrypted = self.net.encrypt_chest(chest.serialize())
        if not encrypted:
            return
        self.net.send_event(
            "CHEST_UPDATE",
            chest_id=chest.chest_id,
            owner_peer_id=chest.owner_peer_id,
            position=[int(chest.position[0]), int(chest.position[1])],
            encrypted=encrypted,
        )

    def find_chest_at(self, x, y):
        for cid, chest in self.chests.items():
            if getattr(chest, "position", None) == (x, y):
                return cid
        return None

    def handle_event(self, event):
        if event.type == KEYDOWN:
            if event.key == K_a: self.input_dx = -1
            elif event.key == K_d: self.input_dx = 1
            elif event.key == K_SPACE: self.input_jump = True
            elif event.key == K_TAB: self.input_tab_held = True
            elif event.key == K_e: self.input_inventory_open = not self.input_inventory_open
            elif event.key == K_c:
                self.crafting_menu.toggle()
            elif event.key == K_1: self.players[self.net.peer_id].selected_item = B_DIRT
            elif event.key == K_2: self.players[self.net.peer_id].selected_item = B_STONE
            elif event.key == K_3: self.players[self.net.peer_id].selected_item = B_WOOD
            elif event.key == K_4: self.players[self.net.peer_id].selected_item = B_WHEAT
        elif event.type == KEYUP:
            if event.key == K_a and self.input_dx == -1: self.input_dx = 0
            elif event.key == K_d and self.input_dx == 1: self.input_dx = 0
            elif event.key == K_SPACE: self.input_jump = False
            elif event.key == K_TAB: self.input_tab_held = False
        elif event.type == MOUSEBUTTONDOWN:
            my_player = self.players.get(self.net.peer_id)
            if not my_player: return

            # Chest UI clicks
            if self.open_chest_id and self.open_chest_id in self.chests and event.button == 1:
                open_chest = self.chests[self.open_chest_id]
                if open_chest.owner_peer_id == self.net.peer_id:
                    hit = self.renderer.chest_ui_hit(event.pos[0], event.pos[1], my_player.inventory, open_chest.inventory)
                    if hit:
                        side, item_id = hit
                        if side == "player" and my_player.remove_item(item_id, 1):
                            open_chest.add_item(item_id, 1)
                            self.save_my_inventory(); self.save_my_chests(); self.broadcast_chest_update(open_chest)
                        elif side == "chest" and open_chest.remove_item(item_id, 1):
                            my_player.add_item(item_id, 1)
                            self.save_my_inventory(); self.save_my_chests(); self.broadcast_chest_update(open_chest)
                        return

            # Crafting menu clicks
            if self.crafting_menu.is_open and event.button == 1:
                clicked_item = self.renderer.crafting_menu_hit(event.pos[0], event.pos[1], True)
                if clicked_item is not None:
                    if my_player.craft(clicked_item):
                        print(f"[CRAFTING] Fabricado {ITEM_NAMES.get(clicked_item)}")
                        self.save_my_inventory()
                        self.crafting_menu.toggle()
                    return

            # Hotbar click
            if event.button == 1:
                clicked_item = self.renderer.hotbar_slot_hit(event.pos[0], event.pos[1], my_player.inventory)
                if clicked_item is not None:
                    my_player.selected_item = clicked_item
                    return

            # World interaction
            surf = pygame.display.get_surface()
            w, h = surf.get_width(), surf.get_height()
            blocks_x = w / BLOCK_SIZE_PX
            blocks_y = h / BLOCK_SIZE_PX
            cam_x = max(0, min(my_player.x - blocks_x / 2.0, 400 - blocks_x))
            cam_y = max(0, min(my_player.y - blocks_y / 2.0, 400 - blocks_y))
            world_x = int(event.pos[0] / BLOCK_SIZE_PX + cam_x)
            world_y = int(event.pos[1] / BLOCK_SIZE_PX + cam_y)

            if event.button == 3:
                if self.world.get_block(world_x, world_y) == B_CHEST:
                    cid = self.find_chest_at(world_x, world_y)
                    if cid and self.chests[cid].owner_peer_id == self.net.peer_id:
                        self.open_chest_id = cid if self.open_chest_id != cid else None
                    return

            action = "break" if event.button == 1 else ("place" if event.button == 3 else None)
            if action and my_player.interact_block(self.world, world_x, world_y, action):
                new_b = self.world.get_block(world_x, world_y)
                self.net.send_event("BLOCK_UPDATE", x=world_x, y=world_y, type=new_b)
                if new_b == B_CHEST:
                    cid = f"chest_{world_x}_{world_y}_{self.net.peer_id}"
                    if cid not in self.chests:
                        self.chests[cid] = Chest(cid, self.net.peer_id, position=(world_x, world_y))
                        self.save_my_chests(); self.broadcast_chest_update(self.chests[cid])

    def update(self, dt):
        my_player = self.players.get(self.net.peer_id)
        if not my_player: return
        
        my_player.update(dt, self.world, self.input_dx, self.input_jump)
        
        # Sync movement
        now = time.time()
        if now - self.last_move_send > 0.05:
            self.net.send_event("PLAYER_MOVE", x=my_player.x, y=my_player.y, vx=my_player.vx, vy=my_player.vy)
            self.last_move_send = now
            
        # Other players interpolation
        for pid, p in self.players.items():
            if pid != self.net.peer_id:
                p.x += p.vx * dt
                p.y += p.vy * dt
        
        # Distance check for open chest
        if self.open_chest_id and self.open_chest_id in self.chests:
            chest = self.chests[self.open_chest_id]
            dist = math.sqrt((my_player.x - chest.position[0])**2 + (my_player.y - chest.position[1])**2)
            if dist > 5:
                self.open_chest_id = None

        # Auto-save
        if int(now) % 10 == 0 and int(now) != getattr(self, '_last_inv_save', 0):
            self._last_inv_save = int(now)
            self.save_my_inventory()

    def draw(self):
        if self.renderer and self.world:
            self.renderer.render(
                self.world, self.players, self.net.peer_id,
                self.input_tab_held, self.input_inventory_open, 
                self.crafting_menu.is_open, self.font_normal
            )
            if self.open_chest_id and self.open_chest_id in self.chests:
                self.renderer.draw_chest_popup(self.players[self.net.peer_id].inventory, self.chests[self.open_chest_id], self.font_normal)

    def on_peer_connected(self, peer_id):
        """Maneja la conexión de un nuevo jugador (Late Join Sync)."""
        if not self.net_manager:
            return
            
        print(f"[MINECRAFT] Jugador {peer_id} conectado. Enviando sincronización...")
        
        # Enviar estado actual del mundo e inventarios al nuevo jugador
        modified = self.world.get_modified_blocks_list()
        inv_data = self.get_all_saved_inventories()
        
        self.net_manager.send_event("LATE_JOIN_SYNC", 
                               target_peer=peer_id, 
                               seed=self.world_seed, 
                               players=list(self.players.keys()), 
                               modified_blocks=modified,
                               inventories=inv_data)
        
        if peer_id not in self.players:
            self.players[peer_id] = Player()
            self.restore_inventory(peer_id)

    def on_peer_disconnected(self, peer_id):
        """Maneja la desconexión de un jugador."""
        if peer_id in self.players:
            self.save_my_inventory()
            del self.players[peer_id]
            print(f"[MINECRAFT] Jugador {peer_id} ha salido")

    def on_message(self, msg):
        action = msg.get("action")
        sender = msg.get("peerId")
        
        if action == "BLOCK_UPDATE":
            x, y, b_type = msg.get("x"), msg.get("y"), msg.get("type")
            if self.world and x is not None:
                self.world.set_block(x, y, b_type)
                if b_type == B_CHEST:
                    cid = f"chest_{x}_{y}_{sender}"
                    if cid not in self.chests:
                        self.chests[cid] = Chest(cid, sender, position=(x, y))
                        self.save_my_chests()
                elif b_type == B_AIR:
                    cid = self.find_chest_at(x, y)
                    if cid in self.chests:
                        del self.chests[cid]
                        self.save_my_chests()
                        
        elif action == "CHEST_UPDATE":
            cid, owner, pos, encrypted = msg.get("chest_id"), msg.get("owner_peer_id"), msg.get("position"), msg.get("encrypted")
            if not cid: return
            px, py = int(pos[0]), int(pos[1])
            if self.world: self.world.set_block(px, py, B_CHEST)
            if cid not in self.chests: self.chests[cid] = Chest(cid, owner, position=(px, py))
            if encrypted and owner == self.net.peer_id:
                data = self.net.decrypt_chest(encrypted)
                if data:
                    restored = Chest.deserialize(data)
                    restored.chest_id, restored.owner_peer_id, restored.position = cid, owner, (px, py)
                    self.chests[cid] = restored
            room_key = self.room_hash
            if room_key not in self.saved_chests: self.saved_chests[room_key] = {}
            self.saved_chests[room_key][cid] = {"owner_peer_id": owner, "position": [px, py], "encrypted": encrypted}
            save_all_chests(self.saved_chests)

        elif action == "PLAYER_MOVE":
            if sender not in self.players:
                self.players[sender] = Player()
                self.restore_inventory(sender)
            p = self.players[sender]
            p.x, p.y, p.vx, p.vy = msg.get("x", p.x), msg.get("y", p.y), msg.get("vx", p.vx), msg.get("vy", p.vy)

        elif action == "LATE_JOIN_SYNC":
            if msg.get("target_peer") == self.net.peer_id:
                self.world_seed = msg.get("seed", 0)
                self.world = World(seed=self.world_seed)
                self.players.clear()
                self.players[self.net.peer_id] = Player()
                for p in msg.get("players", []):
                    if p != self.net.peer_id: self.players[p] = Player()
                self.world.apply_modified_blocks(msg.get("modified_blocks", []))
                inv_data = msg.get("inventories", {})
                if inv_data:
                    if self.room_hash not in self.saved_inventories: self.saved_inventories[self.room_hash] = {}
                    for pid, pdata in inv_data.items():
                        if pid != self.net.peer_id: self.saved_inventories[self.room_hash][pid] = pdata
                    save_all_inventories(self.saved_inventories)
                self.restore_inventory(self.net.peer_id)
                self.restore_chests()
                surf = pygame.display.get_surface()
                self.renderer.setup_opengl(surf.get_width(), surf.get_height())

def main():
    global WIDTH, HEIGHT
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Minecraft P2P 2D")
    clock = pygame.time.Clock()
    font_title, font_normal, font_small = pygame.font.SysFont(None, 64), pygame.font.SysFont(None, 36), pygame.font.SysFont(None, 24)
    current_state, net_manager, is_host = STATE_MENU, None, False
    msg_queue = queue.Queue()
    room_hash_display = ""
    game_instance = None

    def set_opengl_mode():
        return pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE | pygame.DOUBLEBUF | pygame.OPENGL)

    def on_message_received(msg):
        if game_instance: game_instance.on_message(msg)
        else: msg_queue.put(msg)

    # UI Buttons (kept as in original for standalone)
    btn_create = Button(WIDTH//2 - 150, HEIGHT//2 - 50, 300, 50, "Crear una nueva sala", font_normal)
    btn_join = Button(WIDTH//2 - 150, HEIGHT//2 + 20, 300, 50, "Unirse a una sala", font_normal)
    input_create_name = TextInput(WIDTH//2 - 150, HEIGHT//2 - 120, 300, 40, font_normal)
    input_create_room = TextInput(WIDTH//2 - 150, HEIGHT//2 - 30, 300, 40, font_normal)
    btn_create_confirm = Button(WIDTH//2 + 10, HEIGHT//2 + 40, 140, 40, "Crear sala", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)
    btn_create_back = Button(WIDTH//2 - 150, HEIGHT//2 + 40, 140, 40, "Volver", font_normal)
    btn_copy_hash = Button(WIDTH//2 - 150, HEIGHT//2 + 20, 300, 40, "Copiar Hash al Portapapeles", font_normal)
    btn_goto_lobby = Button(WIDTH//2 - 150, HEIGHT//2 + 80, 300, 40, "Ir a la Sala de Espera", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)
    btn_start_lobby = Button(WIDTH//2 - 150, HEIGHT - 100, 300, 40, "Empezar Partida", font_normal, bg_color=(50, 200, 50), hover_color=(50, 150, 50))
    input_join_name = TextInput(WIDTH//2 - 200, HEIGHT//2 - 120, 400, 40, font_normal)
    input_join_room = TextInput(WIDTH//2 - 200, HEIGHT//2 - 30, 400, 40, font_normal)
    btn_join_confirm = Button(WIDTH//2 + 10, HEIGHT//2 + 40, 140, 40, "Unirse", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)
    btn_join_back = Button(WIDTH//2 - 150, HEIGHT//2 + 40, 140, 40, "Volver", font_normal)

    running = True
    while running:
        if current_state != STATE_GAME: screen.fill(GRAY)
        for event in pygame.event.get():
            if event.type == QUIT:
                if game_instance: game_instance.save_my_inventory(); game_instance.save_my_chests()
                running = False
            elif event.type == VIDEORESIZE:
                WIDTH, HEIGHT = max(MIN_WIDTH, event.w), max(MIN_HEIGHT, event.h)
                if current_state == STATE_GAME:
                    screen = set_opengl_mode()
                    if game_instance and game_instance.renderer: game_instance.renderer.setup_opengl(WIDTH, HEIGHT)
                else: screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
            
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
                    net_manager.start(); current_state = STATE_ROOM_CREATED
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
                    net_manager.start(); current_state = STATE_LOBBY
                if btn_join_back.handle_event(event): current_state = STATE_MENU
            elif current_state == STATE_LOBBY:
                if is_host and btn_start_lobby.handle_event(event):
                    seed = random.random() * 1000
                    net_manager.send_event("START_GAME", players=list(net_manager.peers.keys()), seed=seed)
                    game_instance = MinecraftGame(set_opengl_mode(), net_manager, clock, seed=seed, room_hash=room_hash_display)
                    current_state = STATE_GAME

        while not msg_queue.empty():
            msg = msg_queue.get()
            if msg.get("action") == "START_GAME":
                game_instance = MinecraftGame(set_opengl_mode(), net_manager, clock, seed=msg.get("seed"), room_hash=room_hash_display)
                current_state = STATE_GAME

        if current_state == STATE_GAME:
            game_instance.update(clock.tick(FPS)/1000.0)
            game_instance.draw()
            pygame.display.flip()
        else:
            if current_state == STATE_MENU:
                screen.blit(font_title.render("Minecraft P2P", True, BLACK), (WIDTH//2 - 150, HEIGHT//4))
                btn_create.draw(screen); btn_join.draw(screen)
            elif current_state == STATE_ROOM_CREATED:
                screen.blit(font_title.render("Sala Creada", True, BLACK), (WIDTH//2 - 100, HEIGHT//5))
                btn_copy_hash.draw(screen); btn_goto_lobby.draw(screen)
            elif current_state == STATE_LOBBY:
                screen.blit(font_title.render("Sala de Espera", True, BLACK), (WIDTH//2 - 100, 50))
                if is_host: btn_start_lobby.draw(screen)
            pygame.display.flip(); clock.tick(FPS)

    pygame.quit(); sys.exit()

if __name__ == "__main__":
    main()
