import asyncio
import pygame
import sys
import hashlib
import os
import math
import random
import time
import json
import queue

if sys.platform != 'emscripten':
    import subprocess
else:
    subprocess = None
from pygame.locals import *

# local UI and network helpers
from ui import Button, TextInput, EscapeMenu
from network import NetworkManager

# minecraft components are optional for the launcher and other games.
try:
    from minecraft_core import World, Player, B_AIR, B_DIRT, B_STONE, B_WOOD, B_WHEAT, B_GRASS, B_SAND
except Exception:
    World = None
    BLOCK_SIZE_PX = 16
    class Player:
        def __init__(self):
            self.inventory = {}
            self.x = 0
            self.y = 0
        def serialize_inventory(self):
            return self.inventory or {}

try:
    from minecraft_render import Renderer, BLOCK_SIZE_PX as _BP
    # prefer real BLOCK_SIZE_PX if available
    try:
        BLOCK_SIZE_PX = _BP
    except Exception:
        pass
except Exception:
    class Renderer:
        def __init__(self, w, h):
            self.w = w
            self.h = h
        def render(self, *a, **k):
            pass


try:
    from main_minecraft import MinecraftGame
except Exception:
    MinecraftGame = None

try:
    from BatleShip import BattleshipGame
except Exception:
    BattleshipGame = None

try:
    from kart import KartGame
except Exception:
    KartGame = None

try:
    from piano import PianoGame
except Exception:
    PianoGame = None
    
try:
    from penaltis import PenaltiesGame
except Exception:
    PenaltiesGame = None

try:
    from head_soccer import HeadSoccerGame
except Exception:
    HeadSoccerGame = None

try:
    from main_mascota import MascotaGame
except Exception:
    MascotaGame = None


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

# Global variables for network and games
net_manager = None
msg_queue = queue.Queue()
battleship_game = None
piano_game = None
minecraft_game = None
mascota_game = None
is_host = False
room_hash_display = ""

async def main():
    # All previous top-level code should be inside this main function.
    pygame.init()
        
    screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
    pygame.display.set_caption("Minecraft P2P 2D")
    clock = pygame.time.Clock()

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

    def copy_to_clipboard(text: str) -> bool:
        """Intenta copiar texto al portapapeles de forma robusta."""
        if sys.platform == 'emscripten':
            try:
                from platform import window
                window.prompt("Copia este código:", text)
                return True
            except Exception:
                return False
        
        try:
            if subprocess:
                subprocess.run(['wl-copy'], input=text.encode('utf-8'), check=True, stderr=subprocess.DEVNULL)
                return True
        except Exception: pass
        # ... rest of native fallbacks ...
        return False

    # Minimal placeholders for objects that other code expects to exist.
    global net_manager, msg_queue, battleship_game, piano_game, minecraft_game, mascota_game, is_host, room_hash_display
    # (Global variables initialized at module level, but we need 'global' here to allow main() to assign to them)
    show_players_list = False
    
    def set_opengl_mode():
        global WIDTH, HEIGHT
        return pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE | pygame.DOUBLEBUF | pygame.OPENGL)

    def on_message_received(msg):
        # Simple router for incoming network messages into the local queue
        try:
            msg_queue.put(msg)
        except Exception:
            pass

    def on_peer_connected(peer_id):
        try:
            if selected_game and net_manager:
                net_manager.send_event("GAME_SELECT", game=selected_game)
        except Exception:
            pass

        if minecraft_game:
            minecraft_game.on_peer_connected(peer_id)
        if mascota_game:
            mascota_game.on_peer_connected(peer_id)

    def on_peer_disconnected(peer_id):
        if minecraft_game:
            minecraft_game.on_peer_disconnected(peer_id)
        if mascota_game:
            mascota_game.on_peer_disconnected(peer_id)
        print(f"[GAME] Jugador {peer_id} ha salido")

    # Chat state for lobby
    chat_messages = []  # list of (peer_id, text)
    chat_input = None
    btn_send_chat = None

    # Fonts used across the UI
    font_small = pygame.font.SysFont(None, 18)
    font_normal = pygame.font.SysFont(None, 24)
    font_title = pygame.font.SysFont(None, 40)

    # Chat UI (create after fonts exist)
    chat_input = TextInput(WIDTH - 360, HEIGHT - 80, 340, 40, font_normal)
    btn_send_chat = Button(WIDTH - 120, HEIGHT - 80, 100, 40, "Enviar", font_small, bg_color=BLUE)

    # Minimal UI elements expected by the rest of the code
    btn_create = Button(0, 0, 200, 44, "Crear Sala", font_normal, bg_color=BLUE)
    btn_join = Button(0, 0, 200, 44, "Unirse", font_normal)
    input_create_name = TextInput(0, 0, 360, 40, font_normal)
    input_create_room = TextInput(0, 0, 360, 40, font_normal)
    btn_create_back = Button(0, 0, 140, 40, "Volver", font_normal)
    btn_create_confirm = Button(0, 0, 140, 40, "Crear", font_normal, bg_color=BLUE)

    btn_copy_hash = Button(0, 0, 200, 40, "Copiar Hash", font_small)
    btn_player_count = Button(0, 0, 160, 40, "Players: 0", font_small)
    
    # Define available games (8 total). Each entry: (display_text, game_key)
    game_definitions = [
        ("Battleships", "battleship"),
        ("Karting", "karting"),
        ("Piano", "piano"),
        ("HeadSoccer", "head_soccer"),
        ("Minecraft", "minecraft"),
        ("Mascota", "mascota"),
        ("Penaltis", "penaltis"),
        ("Game 8", "game8"),
    ]

    # Create Button objects for all games (will be positioned per-page in update_ui_layout)
    game_buttons = []
    for text, key in game_definitions:
        b = Button(0, 0, 200, 160, text, font_normal, bg_color=(120, 140, 200))
        b._game_key = key
        game_buttons.append(b)

    # Map game_key -> display text for consistent labeling
    game_label_map = {key: text for (text, key) in game_definitions}

    # Pagination controls for game list
    page_index = 0
    games_per_page = 4  # 2 columns x 2 rows
    total_pages = (len(game_buttons) + games_per_page - 1) // games_per_page
    btn_prev_page = Button(0, 0, 120, 40, "Prev", font_small)
    btn_next_page = Button(0, 0, 120, 40, "Next", font_small)
    btn_start_game = Button(0, 0, 300, 56, "Start", font_normal, bg_color=BLUE)

    btn_start_lobby = Button(0, 0, 300, 44, "Iniciar partida", font_normal, bg_color=BLUE)

    # Join inputs (ensure exist)
    input_join_name = TextInput(WIDTH//2 - 200, HEIGHT//2 - 120, 400, 40, font_normal)
    input_join_room = TextInput(WIDTH//2 - 200, HEIGHT//2 - 30, 400, 40, font_normal)
    btn_join_confirm = Button(WIDTH//2 + 10, HEIGHT//2 + 40, 140, 40, "Unirse", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)
    btn_join_back = Button(WIDTH//2 - 150, HEIGHT//2 + 40, 140, 40, "Volver", font_normal)
    btn_join_paste = Button(0, 0, 80, 40, "Pegar", font_small, bg_color=(100, 180, 100))

    # State variables
    selected_game = None
    
    # Elemento UI - Fin de partida
    btn_end_to_menu = Button(WIDTH//2 - 140, HEIGHT - 80, 280, 44, "Volver al menú principal", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)

    def clamp_window_size(w, h):
        return max(MIN_WIDTH, w), max(MIN_HEIGHT, h)

    # Focus/navigation helpers for TextInput fields
    def get_inputs_for_state(state):
        if state == STATE_CREATE_ROOM:
            return [input_create_name, input_create_room]
        if state == STATE_JOIN_ROOM:
            return [input_join_name, input_join_room]
        if state in (STATE_LOBBY, STATE_ROOM_CREATED):
            # chat is available in lobby/room
            return [chat_input]
        return []

    def focus_next_input(state):
        inputs = [i for i in get_inputs_for_state(state) if i is not None]
        if not inputs:
            return
        # find current active
        active_idx = None
        for idx, inp in enumerate(inputs):
            if getattr(inp, 'is_active', False):
                active_idx = idx
                break
        # move to next or unfocus if last
        if active_idx is None:
            # focus first
            for inp in inputs:
                inp.is_active = False
            inputs[0].is_active = True
        else:
            # unset current
            inputs[active_idx].is_active = False
            if active_idx + 1 < len(inputs):
                inputs[active_idx + 1].is_active = True
            else:
                # if last, unfocus all
                for inp in inputs:
                    inp.is_active = False

    def handle_enter_as_confirm(state):
        global net_manager, is_host, room_hash_display
        nonlocal current_state
        # If chat input is active, send chat
        if state in (STATE_LOBBY, STATE_ROOM_CREATED):
            if chat_input and getattr(chat_input, 'is_active', False):
                text = chat_input.text.strip()
                if text and net_manager:
                    try:
                        net_manager.send_event('CHAT', text=text)
                    except Exception:
                        pass
                    chat_messages.append((getattr(net_manager, 'peer_id', 'You'), text))
                    chat_input.text = ""
                return

        # Create room confirm (same behavior as clicking create)
        if state == STATE_CREATE_ROOM:
            room_name = input_create_room.text.strip()
            player_name = input_create_name.text.strip()
            if room_name and player_name:
                # ensure the shared room hash variable is updated for UI and copy
                room_hash_display = generate_room_hash(room_name)
                is_host = True
                try:
                    net_manager = NetworkManager(room_hash_display, peer_id=player_name)
                    net_manager.on_message_received = on_message_received
                    net_manager.on_peer_connected = on_peer_connected
                    net_manager.on_peer_disconnected = on_peer_disconnected
                    net_manager.start()
                    current_state = STATE_ROOM_CREATED
                except Exception:
                    net_manager = None

        # Join room confirm (same behavior as clicking join)
        if state == STATE_JOIN_ROOM:
            room_hash = input_join_room.text.strip()
            player_name = input_join_name.text.strip()
            if room_hash and player_name:
                is_host = False
                room_hash_display = room_hash
                try:
                    net_manager = NetworkManager(room_hash, peer_id=player_name)
                    net_manager.on_message_received = on_message_received
                    net_manager.on_peer_connected = on_peer_connected
                    net_manager.on_peer_disconnected = on_peer_disconnected
                    net_manager.start()
                    current_state = STATE_LOBBY
                except Exception:
                    net_manager = None

    def reset_match_state():
        global battleship_game, piano_game, minecraft_game, mascota_game
        if mascota_game:
            try:
                mascota_game.save_my_pet()
            except Exception:
                pass
        battleship_game = None
        piano_game = None
        minecraft_game = None
        mascota_game = None

    def return_to_main_menu():
        global current_state, net_manager, is_host
        if net_manager:
            try:
                net_manager.stop()
            except Exception:
                pass
        net_manager = None
        is_host = False
        reset_match_state()
        current_state = STATE_MENU

        while not msg_queue.empty():
            try:
                msg_queue.get_nowait()
            except Exception:
                pass

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
        fire_h = 44

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

        # Sala creada / responsive layout for top, middle, bottom areas
        big_btn_w = min(420, max(320, WIDTH - 90))
        # Top-left copy button
        btn_copy_hash.rect = pygame.Rect(16, 12, min(260, WIDTH//4), 40)
        # Top-right player count
        btn_player_count.rect = pygame.Rect(WIDTH - 16 - min(260, WIDTH//4), 12, min(260, WIDTH//4), 40)

        # Middle: paginated game buttons (2 columns x 2 rows), avoid chat area on right
        chat_w = 340
        chat_margin = 20
        chat_x = WIDTH - chat_w - chat_margin
        content_left = 20
        content_right = chat_x - 20
        content_width = max(200, content_right - content_left)
        # button size responsive to content width
        col_w = min(420, max(240, (content_width - 40) // 2))
        row_h = min(200, max(120, HEIGHT // 6))
        gap_x = 40
        gap_y = 20
        col_x1 = content_left
        col_x2 = col_x1 + col_w + gap_x
        total_rows_h = 2 * row_h + gap_y
        start_y = max(120, HEIGHT // 2 - total_rows_h // 2)
        row_y0 = start_y
        row_y1 = start_y + row_h + gap_y

        # Position visible buttons for current page
        try:
            start = page_index * games_per_page
            for i in range(games_per_page):
                idx = start + i
                if idx < len(game_buttons):
                    b = game_buttons[idx]
                    col = i % 2
                    row = i // 2
                    x = col_x1 if col == 0 else col_x2
                    y = row_y0 if row == 0 else row_y1
                    b.rect = pygame.Rect(x, y, col_w, row_h)
                else:
                    # hide off-page buttons
                    pass
        except Exception:
            pass

        # Bottom start button (centered between content and chat)
        center_x = (content_left + content_right) // 2
        btn_start_game.rect = pygame.Rect(center_x - 150, HEIGHT - 80, 300, 56)

        # Chat input and send button (right side)
        chat_w = 340
        chat_h = 200
        chat_margin = 20
        chat_x = WIDTH - chat_w - chat_margin
        chat_y = max(120, 120)
        # place input at bottom-right
        if 'chat_input' in locals() or True:
            try:
                chat_input.rect.x = chat_x
                chat_input.rect.w = chat_w
                chat_input.rect.y = HEIGHT - 80
                chat_input.rect.h = 40
            except Exception:
                pass
        try:
            btn_send_chat.rect.x = chat_x + chat_w - 100
            btn_send_chat.rect.y = HEIGHT - 80
            btn_send_chat.rect.w = 100
            btn_send_chat.rect.h = 40
        except Exception:
            pass

        # Pagination buttons (Prev/Next)
        try:
            btn_prev_page.rect = pygame.Rect(content_left, HEIGHT - 80, 120, 40)
            btn_next_page.rect = pygame.Rect(content_right - 120, HEIGHT - 80, 120, 40)
        except Exception:
            pass

        # Unirse a sala
        join_w = min(520, max(360, WIDTH - 90))
        join_base = HEIGHT // 2 - 90
        input_join_name.rect = pygame.Rect(WIDTH // 2 - join_w // 2, join_base - 36, join_w, input_h)
        input_join_room.rect = pygame.Rect(WIDTH // 2 - join_w // 2, join_base + 48, join_w, input_h)
        btn_join_back.rect = pygame.Rect(WIDTH // 2 - btn_small_w - 8, join_base + 110, btn_small_w, btn_h)
        btn_join_confirm.rect = pygame.Rect(WIDTH // 2 + 8, join_base + 110, btn_small_w, btn_h)
        btn_join_paste.rect = pygame.Rect(input_join_room.rect.right + 10, input_join_room.rect.y, 80, 40)

        # Lobby / batalla
        btn_start_lobby.rect = pygame.Rect(WIDTH // 2 - big_btn_w // 2, HEIGHT - 68, big_btn_w, 44)
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
        if not (current_state == STATE_GAME and minecraft_game is not None):
            screen.fill(WHITE)
            
        if current_state != STATE_GAME:
            update_ui_layout()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                new_w, new_h = clamp_window_size(*event.size)
                if (new_w, new_h) != (WIDTH, HEIGHT):
                    WIDTH, HEIGHT = new_w, new_h
                    if current_state == STATE_GAME and minecraft_game is not None:
                        screen = set_opengl_mode()
                        if minecraft_game and minecraft_game.renderer:
                            minecraft_game.renderer.setup_opengl(WIDTH, HEIGHT)
                    else:
                        screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                        update_ui_layout()

            # Global keyboard navigation: Tab to cycle inputs, Enter to confirm
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_TAB:
                    if not (current_state == STATE_GAME and minecraft_game is not None):
                        focus_next_input(current_state)
                        continue
                if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                    if not (current_state == STATE_GAME and minecraft_game is not None):
                        handle_enter_as_confirm(current_state)
                        continue
                if event.key == pygame.K_ESCAPE:
                    if current_state == STATE_GAME:
                        # If in OpenGL mode (Minecraft), switch to 2D for the menu
                        is_opengl = (minecraft_game is not None)
                        if is_opengl:
                            pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                        
                        menu = EscapeMenu(screen, clock, font_normal)
                        res = menu.show()
                        
                        if res == "RESUME":
                            if is_opengl:
                                screen = set_opengl_mode()
                            continue
                        elif res == "LOBBY":
                            current_state = STATE_ROOM_CREATED if is_host else STATE_LOBBY
                            reset_match_state()
                            # ensure 2D mode
                            screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                            update_ui_layout()
                            continue
                        elif res == "EXIT":
                            running = False
                            continue
            
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
                # Chat input events (allow typing in chat while in room)
                try:
                    chat_input.handle_event(event)
                except Exception:
                    pass
                if event.type == pygame.KEYDOWN:
                    if getattr(chat_input, 'is_active', False) and event.key == pygame.K_RETURN:
                        text = chat_input.text.strip()
                        if text and net_manager:
                            try:
                                net_manager.send_event('CHAT', text=text)
                            except Exception:
                                pass
                            chat_messages.append((getattr(net_manager, 'peer_id', 'You'), text))
                            chat_input.text = ""
                try:
                    if btn_send_chat.handle_event(event):
                        text = chat_input.text.strip()
                        if text and net_manager:
                            try:
                                net_manager.send_event('CHAT', text=text)
                            except Exception:
                                pass
                            chat_messages.append((getattr(net_manager, 'peer_id', 'You'), text))
                            chat_input.text = ""
                except Exception:
                    pass
                # Top buttons
                if btn_copy_hash.handle_event(event):
                    if copy_to_clipboard(room_hash_display):
                        print(f"Hash copiado con éxito: {room_hash_display}")
                    else:
                        print("Error copiando al portapapeles. Asegúrate de tener 'wl-clipboard' o 'xclip' instalado.")

                if btn_player_count.handle_event(event):
                    show_players_list = not show_players_list

                # Middle: select game (paginated)
                try:
                    start = page_index * games_per_page
                    for i in range(games_per_page):
                        idx = start + i
                        if idx < len(game_buttons):
                            b = game_buttons[idx]
                            if b.handle_event(event):
                                selected_game = getattr(b, '_game_key', None)
                                if net_manager and selected_game:
                                    try:
                                        net_manager.send_event("GAME_SELECT", game=selected_game)
                                    except Exception:
                                        pass
                except Exception:
                    pass

                # Pagination controls
                try:
                    if btn_prev_page.handle_event(event):
                        page_index = max(0, page_index - 1)
                    if btn_next_page.handle_event(event):
                        page_index = min(total_pages - 1, page_index + 1)
                except Exception:
                    pass

                # Bottom: start selected game
                if btn_start_game.handle_event(event):
                    if selected_game is None:
                        print("Select a game first")
                    elif selected_game == 'minecraft':
                        if MinecraftGame:
                            minecraft_game = MinecraftGame(set_opengl_mode(), net_manager, clock, seed=random.random()*1000, room_hash=room_hash_display)
                            # notify peers so everyone launches minecraft
                            if net_manager:
                                try:
                                    players_list = [net_manager.peer_id] + list(net_manager.peers.keys())
                                    net_manager.send_event("START_GAME", players=players_list, game=selected_game, seed=minecraft_game.world_seed)
                                except Exception:
                                    pass
                            current_state = STATE_GAME
                        else:
                            print("MinecraftGame not available.")

                    elif selected_game == 'battleship':
                        # host starts battleship
                        if net_manager:
                            try:
                                # include host first then peers so all clients have canonical order
                                players_list = [net_manager.peer_id] + list(net_manager.peers.keys())
                                net_manager.send_event("START_GAME", players=players_list, game=selected_game)
                            except Exception:
                                pass
                        # initialize Battleship manager and start placement
                        battleship_game = BattleshipGame(net_manager)
                        battleship_game.start_placement(WIDTH, HEIGHT, cell_size=30)
                        current_state = STATE_GAME
                    elif selected_game == 'mascota':
                        if MascotaGame:
                            mascota_game = MascotaGame(screen, net_manager, clock, room_hash=room_hash_display)
                            if net_manager:
                                try:
                                    players_list = [net_manager.peer_id] + list(net_manager.peers.keys())
                                    net_manager.send_event("START_GAME", players=players_list, game=selected_game)
                                except Exception:
                                    pass
                            current_state = STATE_GAME
                        else:
                            print("MascotaGame not available.")
                    elif selected_game == 'penaltis':
                        # host starts Penaltis
                        if net_manager:
                                try:
                                    players_list = [net_manager.peer_id] + list(net_manager.peers.keys())
                                    net_manager.send_event("START_GAME", players=players_list, game=selected_game)
                                except Exception:
                                    pass
                        # initialize Penalties manager and start
                        try:
                            penalties_game = PenaltiesGame(net_manager, is_host=is_host, players=players_list if 'players_list' in locals() else None)
                        except Exception:
                            penalties_game = None
                        battleship_game = penalties_game
                        try:
                            if battleship_game:
                                battleship_game.start_placement(WIDTH, HEIGHT, cell_size=30)
                        except Exception:
                            pass
                        current_state = STATE_GAME
                    elif selected_game == 'karting':
                        if KartGame is None:
                            print("KartGame not available (failed to import kart module).")
                        elif net_manager:
                            try:
                                # notify peers so everyone launches the kart game
                                try:
                                    players_list = [net_manager.peer_id] + list(net_manager.peers.keys())
                                    net_manager.send_event("START_GAME", players=players_list, game=selected_game)
                                except Exception:
                                    pass
                                game = KartGame(net_manager=net_manager)
                                try:
                                    game.run()
                                except Exception as e:
                                    print("Failed to run KartGame:", e)
                                
                                # Return to lobby instead of menu, keep net_manager alive
                                if net_manager:
                                    net_manager.on_message_received = on_message_received
                                    net_manager.on_peer_connected = on_peer_connected
                                    net_manager.on_peer_disconnected = on_peer_disconnected
                                    current_state = STATE_ROOM_CREATED if is_host else STATE_LOBBY
                                    # re-set screen to 2D mode in case game changed it
                                    if not pygame.get_init():
                                        pygame.init()
                                        update_ui_layout(reinit_fonts=True)
                                    else:
                                        screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                                        update_ui_layout()
                                else:
                                    current_state = STATE_MENU
                                    is_host = False
                            except Exception as e:
                                print("Failed to start KartGame:", e)
                    elif selected_game == 'head_soccer':
                        if HeadSoccerGame is None:
                            print("HeadSoccerGame not available (failed to import head_soccer module).")
                        elif net_manager:
                            try:
                                # notify peers so everyone launches the head soccer game
                                try:
                                    players_list = [net_manager.peer_id] + list(net_manager.peers.keys())
                                    net_manager.send_event("START_GAME", players=players_list, game=selected_game)
                                except Exception:
                                    pass
                                game = HeadSoccerGame(net_manager=net_manager)
                                try:
                                    game.run()
                                except Exception as e:
                                    print("Failed to run HeadSoccerGame:", e)
                                
                                # Return to lobby instead of menu, keep net_manager alive
                                if net_manager:
                                    current_state = STATE_ROOM_CREATED if is_host else STATE_LOBBY
                                    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                                    update_ui_layout()
                                else:
                                    current_state = STATE_MENU
                                    is_host = False
                            except Exception as e:
                                print("Failed to start HeadSoccerGame:", e)
                    elif selected_game == 'piano':
                        if PianoGame is None:
                            print("PianoGame not available (failed to import piano module).")
                        else:
                            if net_manager:
                                try:
                                    players_list = list(net_manager.peers.keys())
                                    net_manager.send_event("START_GAME", players=players_list, game="piano")
                                except Exception:
                                    pass
                            piano_game = PianoGame(net_manager)
                            piano_game.build_layout(WIDTH, HEIGHT)
                            current_state = STATE_GAME
                    
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
                if btn_join_paste.handle_event(event):
                    if sys.platform == 'emscripten':
                        from platform import window
                        pasted = window.prompt("Pega aquí el código/hash de la sala:")
                        if pasted:
                            input_join_room.text = pasted.strip()
                    else:
                        print("El botón Pegar solo es necesario en la versión Web.")

            elif current_state == STATE_LOBBY:
                # Chat input events in lobby
                try:
                    chat_input.handle_event(event)
                except Exception:
                    pass
                if event.type == pygame.KEYDOWN:
                    if getattr(chat_input, 'is_active', False) and event.key == pygame.K_RETURN:
                        text = chat_input.text.strip()
                        if text and net_manager:
                            try:
                                net_manager.send_event('CHAT', text=text)
                            except Exception:
                                pass
                            chat_messages.append((getattr(net_manager, 'peer_id', 'You'), text))
                            chat_input.text = ""
                try:
                    if btn_send_chat.handle_event(event):
                        text = chat_input.text.strip()
                        if text and net_manager:
                            try:
                                net_manager.send_event('CHAT', text=text)
                            except Exception:
                                pass
                            chat_messages.append((getattr(net_manager, 'peer_id', 'You'), text))
                            chat_input.text = ""
                except Exception:
                    pass

                if is_host and btn_start_lobby.handle_event(event):
                    # El host decide empezar
                    players_list = list(net_manager.peers.keys())
                    try:
                        net_manager.send_event("START_GAME", players=players_list, game=selected_game or 'battleship')
                    except Exception:
                        pass
                    
                    if selected_game == 'minecraft':
                        if MinecraftGame:
                            minecraft_game = MinecraftGame(set_opengl_mode(), net_manager, clock, seed=random.random()*1000, room_hash=room_hash_display)
                            if net_manager:
                                try:
                                    players_list = [net_manager.peer_id] + list(net_manager.peers.keys())
                                    net_manager.send_event("START_GAME", players=players_list, game=selected_game, seed=minecraft_game.world_seed)
                                except Exception:
                                    pass
                        else:
                            print("MinecraftGame not available.")
                    elif selected_game == 'piano':
                        piano_game = PianoGame(net_manager)
                        piano_game.build_layout(WIDTH, HEIGHT)
                    elif selected_game == 'battleship':
                        battleship_game = BattleshipGame(net_manager)
                        battleship_game.start_placement(WIDTH, HEIGHT, cell_size=30)
                    elif selected_game == 'mascota':
                        if MascotaGame:
                            mascota_game = MascotaGame(screen, net_manager, clock, room_hash=room_hash_display)
                        else:
                            print("MascotaGame not available.")
                    current_state = STATE_GAME
            
            elif current_state == STATE_GAME:
                # Piano game: handle events (ESC to return)
                if piano_game:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        piano_game.cleanup()
                        piano_game = None
                        current_state = STATE_ROOM_CREATED if is_host else STATE_LOBBY
                    else:
                        piano_game.handle_event(event)
                # Delegate event handling to BattleshipGame if present
                elif battleship_game:
                    battleship_game.handle_event(event)
                    # if battle_phase and it's our turn and we pressed fire button, send FIRE_MULTI
                    if battleship_game.battle_phase:
                        turn_owner = battleship_game.all_players_sorted[battleship_game.current_turn_index] if battleship_game.all_players_sorted else None
                        is_my_turn = (not battleship_game.game_over and turn_owner == getattr(net_manager, 'peer_id', None) and getattr(net_manager, 'peer_id', None) not in battleship_game.eliminated_players)
                        if is_my_turn and (event.type == pygame.KEYDOWN and (event.key == pygame.K_SPACE or event.key == pygame.K_RETURN)):
                            targets = []
                            for ab in battleship_game.attack_boards:
                                if not ab.is_eliminated and ab.selected_coord:
                                    targets.append({"target_peer": ab.target_peer_id, "coord": ab.get_selected_coord_str()})
                            active_attack_boards = [ab for ab in battleship_game.attack_boards if not ab.is_eliminated]
                            if len(targets) == len(active_attack_boards) and len(active_attack_boards) > 0 and net_manager:
                                net_manager.send_event("FIRE_MULTI", targets=targets)
                                battleship_game.advance_turn_to_next_alive()
                                print("[JUEGO] Disparos enviados.")
                        # allow the end-to-menu button to be clicked whenever the game is over
                        try:
                            if getattr(battleship_game, 'game_over', False):
                                if btn_end_to_menu.handle_event(event):
                                    return_to_main_menu()
                        except Exception:
                            pass
                elif minecraft_game:
                    minecraft_game.handle_event(event)
                elif mascota_game:
                    mascota_game.handle_event(event)

        # Procesar mensajes de red entrantes
        while not msg_queue.empty():
            msg = msg_queue.get()
            action = msg.get("action")
            sender = msg.get("peerId") or msg.get("peer_id") or 'unknown'

            # If battleship_game is active, let it handle relevant actions
            # First, always handle lobby chat messages globally
            if action == 'CHAT':
                text = msg.get('text') or msg.get('message') or ''
                chat_messages.append((sender, text))
                # keep chat length reasonable
                if len(chat_messages) > 200:
                    chat_messages.pop(0)

            # If a Battleship manager is active, delegate to it
            if battleship_game:
                try:
                    battleship_game.on_network_message(msg)
                except Exception:
                    pass

            # If a Piano game is active, delegate note events to it
            if piano_game and action in ('NOTE_ON', 'NOTE_OFF'):
                try:
                    piano_game.on_network_message(msg)
                except Exception:
                    pass

            if action == "START_GAME":
                g = msg.get('game') or selected_game or 'battleship'
                print(f"El Host ha iniciado la partida. Juego: {g} Jugadores: {msg.get('players')}")
                try:
                    reset_match_state()
                except Exception:
                    pass

                # create appropriate manager
                if g == 'minecraft':
                    if MinecraftGame:
                        minecraft_game = MinecraftGame(set_opengl_mode(), net_manager, clock, seed=msg.get("seed"), room_hash=room_hash_display)
                    else:
                        print("MinecraftGame not available.")
                elif g == 'piano':
                    if not piano_game:
                        piano_game = PianoGame(net_manager)
                        piano_game.build_layout(WIDTH, HEIGHT)
                elif g == 'battleship':
                    try:
                        battleship_game = BattleshipGame(net_manager)
                        battleship_game.start_placement(WIDTH, HEIGHT, cell_size=30)
                    except Exception:
                        battleship_game = None
                elif g == 'mascota':
                    if MascotaGame:
                        mascota_game = MascotaGame(screen, net_manager, clock, room_hash=room_hash_display)
                    else:
                        print("MascotaGame not available.")
                elif g == 'penaltis':
                    try:
                        players_list = msg.get('players') if isinstance(msg.get('players'), list) else None
                        penalties_game = PenaltiesGame(net_manager, is_host=False, players=players_list)
                        battleship_game = penalties_game
                        if battleship_game:
                            battleship_game.start_placement(WIDTH, HEIGHT, cell_size=30)
                    except Exception:
                        battleship_game = None
                elif g == 'karting':
                    try:
                        if KartGame is None:
                            print("KartGame not available on this client.")
                        else:
                            try:
                                game = KartGame(net_manager=net_manager)
                                try:
                                    game.run()
                                finally:
                                    # Return to lobby instead of menu, keep net_manager alive
                                    if net_manager:
                                        net_manager.on_message_received = on_message_received
                                        net_manager.on_peer_connected = on_peer_connected
                                        net_manager.on_peer_disconnected = on_peer_disconnected
                                        
                                        current_state = STATE_ROOM_CREATED if is_host else STATE_LOBBY
                                        if not pygame.get_init():
                                            pygame.init()
                                            update_ui_layout(reinit_fonts=True)
                                        else:
                                            screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                                            update_ui_layout()
                                    else:
                                        current_state = STATE_MENU
                                        is_host = False
                            except Exception as e:
                                print("Failed to start KartGame on client:", e)
                    except Exception:
                        pass
                elif g == 'head_soccer':
                    try:
                        if HeadSoccerGame is None:
                            print("HeadSoccerGame not available on this client.")
                        else:
                            try:
                                game = HeadSoccerGame(net_manager=net_manager)
                                try:
                                    game.run()
                                finally:
                                    # Return to lobby instead of menu, keep net_manager alive
                                    if net_manager:
                                        net_manager.on_message_received = on_message_received
                                        net_manager.on_peer_connected = on_peer_connected
                                        net_manager.on_peer_disconnected = on_peer_disconnected
                                        
                                        current_state = STATE_ROOM_CREATED if is_host else STATE_LOBBY
                                        if not pygame.get_init():
                                            pygame.init()
                                            update_ui_layout(reinit_fonts=True)
                                        else:
                                            screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                                            update_ui_layout()
                                    else:
                                        current_state = STATE_MENU
                                        is_host = False
                            except Exception as e:
                                print("Failed to start HeadSoccerGame on client:", e)
                    except Exception:
                        pass
                else:
                    # unknown game, fallback to battleship
                    try:
                        battleship_game = BattleshipGame(net_manager)
                        battleship_game.start_placement(WIDTH, HEIGHT, cell_size=30)
                    except Exception:
                        battleship_game = None
                current_state = STATE_GAME

            elif action in ("LATE_JOIN_SYNC", "BLOCK_UPDATE", "PLAYER_MOVE", "CHEST_UPDATE") and minecraft_game:
                minecraft_game.on_message(msg)
            elif action in ("LATE_JOIN_SYNC", "PET_UPDATE", "PET_ACTION") and mascota_game:
                mascota_game.on_message(msg)

            elif msg.get("action") == "COMMIT_BOARD":
                peer_id = msg.get("peerId")
                b_hash = msg.get("board_hash")
                player_commits[peer_id] = b_hash
                print(f"[JUEGO] El jugador {peer_id} ha fijado su flota.")
            
            elif msg.get("action") == "GAME_SELECT":
                # Host announced the selected game for this room
                g = msg.get('game')
                if g in ('battleship', 'karting', 'penaltis', 'piano', 'minecraft', 'head_soccer', 'mascota'):
                    selected_game = g
                    print(f"[LOBBY] Juego seleccionado: {selected_game}")
                
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

            # Middle: paginated game buttons
            try:
                start = page_index * games_per_page
                for i in range(games_per_page):
                    idx = start + i
                    if idx < len(game_buttons):
                        b = game_buttons[idx]
                        b.draw(screen)
                        # highlight selection
                        if getattr(b, '_game_key', None) == selected_game:
                            pygame.draw.rect(screen, (255,255,255), b.rect, 4)
            except Exception:
                pass

            # Pagination UI
            try:
                btn_prev_page.draw(screen)
                btn_next_page.draw(screen)
                chat_w = 340
                chat_margin = 20
                content_left = 20
                content_right = WIDTH - chat_w - chat_margin - 20
                page_lbl = font_small.render(f"Page {page_index+1}/{total_pages}", True, (40,40,40))
                screen.blit(page_lbl, ( (content_left + content_right)//2 - page_lbl.get_width()//2, HEIGHT - 74 ))
            except Exception:
                pass

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
            # Chat panel (right side)
            # Chat panel (right side)
            panel_w = 340
            panel_x = WIDTH - panel_w - 20
            panel_y = 120
            panel_h = HEIGHT - 160
            pygame.draw.rect(screen, (245,245,245), (panel_x, panel_y, panel_w, panel_h))
            pygame.draw.rect(screen, (160,160,160), (panel_x, panel_y, panel_w, panel_h), 2)
            # messages area
            msg_area_h = panel_h - 60
            max_lines = max(3, msg_area_h // (font_small.get_height() + 4))
            # draw from bottom up
            start_y = panel_y + msg_area_h - 8
            for sender, text in reversed(chat_messages[-max_lines:]):
                line = f"{sender}: {text}"
                surf = font_small.render(line, True, (20,20,20))
                start_y -= surf.get_height() + 4
                screen.blit(surf, (panel_x + 8, start_y))
            # draw input and send
            try:
                chat_input.draw(screen)
                btn_send_chat.draw(screen)
            except Exception:
                pass
                
                # Handle chat input events
                # (chat_input handles focus on mouse down; we check ENTER here)
                if event.type == pygame.KEYDOWN:
                    if getattr(chat_input, 'is_active', False) and event.key == pygame.K_RETURN:
                        text = chat_input.text.strip()
                        if text and net_manager:
                            try:
                                net_manager.send_event('CHAT', text=text)
                            except Exception:
                                pass
                            chat_messages.append((getattr(net_manager, 'peer_id', 'You'), text))
                            chat_input.text = ""
                if btn_send_chat.handle_event(event):
                    text = chat_input.text.strip()
                    if text and net_manager:
                        try:
                            net_manager.send_event('CHAT', text=text)
                        except Exception:
                            pass
                        chat_messages.append((getattr(net_manager, 'peer_id', 'You'), text))
                        chat_input.text = ""
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
            btn_join_paste.draw(screen)
            
        elif current_state == STATE_LOBBY:
            title = font_title.render("Sala de Espera", True, BLACK)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, 50))
            # Show currently selected game (if any)
            if selected_game:
                # Use the canonical display name if available
                display_name = game_label_map.get(selected_game, selected_game)
                label_text = "Juego seleccionado: " + display_name
                lbl_sel = font_normal.render(label_text, True, DARK_BLUE)
                screen.blit(lbl_sel, (WIDTH//2 - lbl_sel.get_width()//2, 100))
                sel_hint = font_small.render("El host ha elegido este juego.", True, (80,80,80))
                screen.blit(sel_hint, (WIDTH//2 - sel_hint.get_width()//2, 100 + lbl_sel.get_height() + 4))
            
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

            # Chat panel (right side) - same layout as room created
            panel_w = 340
            panel_x = WIDTH - panel_w - 20
            panel_y = 120
            panel_h = HEIGHT - 160
            pygame.draw.rect(screen, (245,245,245), (panel_x, panel_y, panel_w, panel_h))
            pygame.draw.rect(screen, (160,160,160), (panel_x, panel_y, panel_w, panel_h), 2)
            msg_area_h = panel_h - 60
            max_lines = max(3, msg_area_h // (font_small.get_height() + 4))
            start_y = panel_y + msg_area_h - 8
            for sender, text in reversed(chat_messages[-max_lines:]):
                line = f"{sender}: {text}"
                surf = font_small.render(line, True, (20,20,20))
                start_y -= surf.get_height() + 4
                screen.blit(surf, (panel_x + 8, start_y))
            try:
                chat_input.draw(screen)
                btn_send_chat.draw(screen)
            except Exception:
                pass
            # Chat input events
            if event.type == pygame.KEYDOWN:
                if getattr(chat_input, 'is_active', False) and event.key == pygame.K_RETURN:
                    text = chat_input.text.strip()
                    if text and net_manager:
                        try:
                            net_manager.send_event('CHAT', text=text)
                        except Exception:
                            pass
                        chat_messages.append((getattr(net_manager, 'peer_id', 'You'), text))
                        chat_input.text = ""
            if btn_send_chat.handle_event(event):
                text = chat_input.text.strip()
                if text and net_manager:
                    try:
                        net_manager.send_event('CHAT', text=text)
                    except Exception:
                        pass
                    chat_messages.append((getattr(net_manager, 'peer_id', 'You'), text))
                    chat_input.text = ""

        elif current_state == STATE_GAME:
            # If we have a PianoGame, delegate drawing to it
            if piano_game:
                piano_game.build_layout(WIDTH, HEIGHT)
                piano_game.draw(screen, font_small, font_normal, font_title, WIDTH, HEIGHT)
            # If we have a BattleshipGame manager, delegate drawing to it
            elif battleship_game:
                try:
                    battleship_game.draw(screen, font_small, font_normal, font_title, WIDTH, HEIGHT)
                except Exception:
                    pass

                # draw fire button if it's our turn
                if getattr(battleship_game, 'battle_phase', False) and not getattr(battleship_game, 'game_over', False) and net_manager:
                    turn_owner = battleship_game.all_players_sorted[battleship_game.current_turn_index] if battleship_game.all_players_sorted else None
                    is_my_turn = (turn_owner == getattr(net_manager, 'peer_id', None) and getattr(net_manager, 'peer_id', None) not in battleship_game.eliminated_players)
                    # fire button removed; instruct user to press Space/Enter to fire
                    if is_my_turn:
                        pass

                # draw end-to-menu button when game over
                if getattr(battleship_game, 'game_over', False):
                    btn_end_to_menu.draw(screen)
            elif minecraft_game:
                dt = clock.get_time() / 1000.0
                minecraft_game.update(dt)
                minecraft_game.draw()
            elif mascota_game:
                dt = clock.get_time() / 1000.0
                mascota_game.update(dt)
                mascota_game.draw()

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
                        # fire button removed; user can press Space/Enter to fire
                        pass

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
        await asyncio.sleep(0)

    # Guardar inventario antes de salir
    if minecraft_game:
        minecraft_game.save_my_inventory()
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    asyncio.run(main())