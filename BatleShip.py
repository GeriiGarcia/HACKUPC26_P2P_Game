import pygame
import random
import string
import hashlib

# (removed debug logging) click mapping will mirror placement board behavior

# Colores del juego
SEA_COLOR = (20, 100, 200)
GRID_COLOR = (50, 150, 255)
SHIP_COLOR = (100, 100, 100)
SHIP_HOVER_COLOR = (150, 150, 150)
INVALID_COLOR = (255, 50, 50)

CELL_SIZE = 30
BOARD_SIZE = 12

class Ship:
    def __init__(self, size):
        self.size = size
        self.placed = False
        self.x = -1
        self.y = -1
        self.vertical = False
        self.sunk = False

class Board:
    def __init__(self, x_offset, y_offset, cell_size=CELL_SIZE):
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.cell_size = cell_size
        self.grid = [[0 for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.ships = [
            Ship(4),
            Ship(3), Ship(3),
            Ship(2), Ship(2), Ship(2)
        ]
        self.current_ship_index = 0
        self.placing_vertical = False
        self.is_ready = False
        self.salt = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

    def draw(self, screen, font, show_status_text=True):
        # Dibujar cuadricula
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                rect = pygame.Rect(self.x_offset + x * self.cell_size, self.y_offset + y * self.cell_size, self.cell_size, self.cell_size)

                cell = self.grid[y][x]
                if cell == 2:
                    pygame.draw.rect(screen, (200, 200, 200), rect) # Agua
                elif cell == 3:
                    pygame.draw.rect(screen, (255, 165, 0), rect) # Tocado por 1 (Naranja)
                elif cell >= 4:
                    pygame.draw.rect(screen, (190, 40, 40), rect) # Barco hundido
                elif cell == 1:
                    pygame.draw.rect(screen, SHIP_COLOR, rect) # Barco intacto
                else:
                    pygame.draw.rect(screen, SEA_COLOR, rect)

                if cell >= 4:
                    self._draw_thin_x(screen, rect)
                    
                pygame.draw.rect(screen, GRID_COLOR, rect, 1)

        # Lógica de Hover (previsualización del barco) si no hemos terminado
        if not self.is_ready:
            mouse_x, mouse_y = pygame.mouse.get_pos()
            if self._is_mouse_in_board(mouse_x, mouse_y):
                grid_x = (mouse_x - self.x_offset) // self.cell_size
                grid_y = (mouse_y - self.y_offset) // self.cell_size

                ship = self.ships[self.current_ship_index]
                can_place = self._can_place_ship(ship.size, grid_x, grid_y, self.placing_vertical)

                color = SHIP_HOVER_COLOR if can_place else INVALID_COLOR
                width = self.cell_size if self.placing_vertical else self.cell_size * ship.size
                height = self.cell_size * ship.size if self.placing_vertical else self.cell_size

                rect = pygame.Rect(self.x_offset + grid_x * self.cell_size, self.y_offset + grid_y * self.cell_size, width, height)
                pygame.draw.rect(screen, color, rect)
                pygame.draw.rect(screen, (255, 255, 255), rect, 2)

        if show_status_text:
            text_y = self.y_offset - font.get_height() - 6
            if not self.is_ready:
                inst_text = font.render(f"Colocando barco de tamaño {self.ships[self.current_ship_index].size} (Click Dcho: Rotar)", True, (255,255,255))
            else:
                inst_text = font.render("¡Flota preparada! Esperando a los rivales...", True, (50,255,50))
            screen.blit(inst_text, (self.x_offset, text_y))

    def handle_event(self, event):
        if self.is_ready:
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 3: # Click derecho para rotar
                self.placing_vertical = not self.placing_vertical
            elif event.button == 1: # Click izquierdo para colocar
                mouse_x, mouse_y = event.pos
                if self._is_mouse_in_board(mouse_x, mouse_y):
                    grid_x = (mouse_x - self.x_offset) // self.cell_size
                    grid_y = (mouse_y - self.y_offset) // self.cell_size
                    
                    ship = self.ships[self.current_ship_index]
                    if self._can_place_ship(ship.size, grid_x, grid_y, self.placing_vertical):
                        self._place_ship(ship, grid_x, grid_y, self.placing_vertical)
                        self.current_ship_index += 1
                        
                        if self.current_ship_index >= len(self.ships):
                            self.is_ready = True
                            print(f"[GAME] ¡Flota posicionada! Generando hash...")

    def _draw_thin_x(self, screen, rect, color=(240, 240, 240)):
        margin = max(1, self.cell_size // 6)
        thickness = 1 if self.cell_size <= 18 else 2
        pygame.draw.line(screen, color,
                         (rect.left + margin, rect.top + margin),
                         (rect.right - margin, rect.bottom - margin),
                         thickness)
        pygame.draw.line(screen, color,
                         (rect.left + margin, rect.bottom - margin),
                         (rect.right - margin, rect.top + margin),
                         thickness)

    def _is_mouse_in_board(self, x, y):
        return (self.x_offset <= x < self.x_offset + BOARD_SIZE * self.cell_size and 
                self.y_offset <= y < self.y_offset + BOARD_SIZE * self.cell_size)

    def _can_place_ship(self, size, x, y, vertical):
        if vertical:
            if y + size > BOARD_SIZE: return False
            for i in range(size):
                if self.grid[y+i][x] != 0: return False
        else:
            if x + size > BOARD_SIZE: return False
            for i in range(size):
                if self.grid[y][x+i] != 0: return False
        return True

    def _place_ship(self, ship, x, y, vertical):
        ship.x = x
        ship.y = y
        ship.vertical = vertical
        ship.placed = True
        
        if vertical:
            for i in range(ship.size):
                self.grid[y+i][x] = 1
        else:
            for i in range(ship.size):
                self.grid[y][x+i] = 1

    def get_board_hash(self):
        """Genera el Hash criptográfico del tablero según la Fase 2"""
        # Aplanar la grid a string y sumar la salt
        grid_str = "".join(str(cell) for row in self.grid for cell in row)
        data_to_hash = grid_str + self.salt
        return hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()

    def _ship_cells(self, ship):
        cells = []
        if not ship.placed:
            return cells
        for i in range(ship.size):
            x = ship.x
            y = ship.y
            if ship.vertical:
                y += i
            else:
                x += i
            cells.append((x, y))
        return cells

    def _ship_at(self, x, y):
        for ship in self.ships:
            if not ship.placed:
                continue
            if (x, y) in self._ship_cells(ship):
                return ship
        return None

    def _is_ship_sunk(self, ship):
        if not ship:
            return False
        for cx, cy in self._ship_cells(ship):
            if self.grid[cy][cx] < 3:
                return False
        return True

    def _mark_ship_sunk(self, ship):
        sunk_cells = []
        if not ship:
            return sunk_cells
        for cx, cy in self._ship_cells(ship):
            if self.grid[cy][cx] >= 3:
                self.grid[cy][cx] = 4
                sunk_cells.append((cx, cy))
        ship.sunk = True
        return sunk_cells

    def are_all_ships_sunk(self):
        return all(getattr(ship, "sunk", False) for ship in self.ships)

    def receive_shot(self, x, y):
        """
        Procesa un disparo entrante sobre el tablero propio.
        Devuelve un dict con hit, sunk, sunk_cells y eliminated.
        """
        if not (0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE):
            return {"hit": False, "sunk": False, "sunk_cells": [], "eliminated": self.are_all_ships_sunk()}

        cell = self.grid[y][x]

        # Casilla de agua no descubierta
        if cell == 0:
            self.grid[y][x] = 2
            return {"hit": False, "sunk": False, "sunk_cells": [], "eliminated": self.are_all_ships_sunk()}

        # Ya disparada (agua)
        if cell == 2:
            return {"hit": False, "sunk": False, "sunk_cells": [], "eliminated": self.are_all_ships_sunk()}

        if cell in (3, 4):
            return {"hit": True, "sunk": False, "sunk_cells": [], "eliminated": self.are_all_ships_sunk()}

        # Impacto en barco intacto
        if cell == 1:
            self.grid[y][x] = 3
            ship = self._ship_at(x, y)
            sunk = False
            sunk_cells = []
            if ship and self._is_ship_sunk(ship):
                sunk_cells = self._mark_ship_sunk(ship)
                sunk = True
            return {"hit": True, "sunk": sunk, "sunk_cells": sunk_cells, "eliminated": self.are_all_ships_sunk()}

        return {"hit": False, "sunk": False, "sunk_cells": [], "eliminated": self.are_all_ships_sunk()}

# Estados para el tablero de ataque
UNEXPLORED = 0
SELECTED = 1
WATER = 2
HIT = 3
SUNK = 4

class AttackBoard:
    def __init__(self, target_peer_id, x_offset, y_offset, cell_size=25):
        self.target_peer_id = target_peer_id
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.cell_size = cell_size
        self.grid = [[UNEXPLORED for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.selected_coord = None # Tupla (x, y)
        self.is_eliminated = False

    def _draw_thin_x(self, screen, rect, color=(245, 245, 245)):
        margin = max(1, self.cell_size // 6)
        thickness = 1 if self.cell_size <= 16 else 2
        pygame.draw.line(screen, color,
                         (rect.left + margin, rect.top + margin),
                         (rect.right - margin, rect.bottom - margin),
                         thickness)
        pygame.draw.line(screen, color,
                         (rect.left + margin, rect.bottom - margin),
                         (rect.right - margin, rect.top + margin),
                         thickness)

    def clear_selection(self):
        if self.selected_coord:
            sx, sy = self.selected_coord
            if 0 <= sx < BOARD_SIZE and 0 <= sy < BOARD_SIZE and self.grid[sy][sx] == SELECTED:
                self.grid[sy][sx] = UNEXPLORED
            self.selected_coord = None

    def draw(self, screen, font, is_their_turn=False):
        label = f"Rival: {self.target_peer_id}"
        if self.is_eliminated:
            label += " (ELIMINADO)"
        color = (255, 120, 120) if self.is_eliminated else ((255, 255, 0) if is_their_turn else (255, 255, 255))
        lbl = font.render(label, True, color)
        lbl_y = self.y_offset - font.get_height() - 4
        screen.blit(lbl, (self.x_offset, lbl_y))
        
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                rect = pygame.Rect(self.x_offset + x * self.cell_size, self.y_offset + y * self.cell_size, self.cell_size, self.cell_size)
                
                if self.grid[y][x] == UNEXPLORED:
                    pygame.draw.rect(screen, (30, 40, 80), rect)
                elif self.grid[y][x] == SELECTED:
                    pygame.draw.rect(screen, (200, 200, 50), rect)
                elif self.grid[y][x] == WATER:
                    pygame.draw.rect(screen, (200, 200, 200), rect)
                elif self.grid[y][x] == HIT:
                    pygame.draw.rect(screen, (255, 50, 50), rect)
                elif self.grid[y][x] == SUNK:
                    pygame.draw.rect(screen, (180, 30, 30), rect)
                    self._draw_thin_x(screen, rect)
                    
                pygame.draw.rect(screen, GRID_COLOR, rect, 1)

        if self.is_eliminated:
            overlay = pygame.Surface((BOARD_SIZE * self.cell_size, BOARD_SIZE * self.cell_size), pygame.SRCALPHA)
            overlay.fill((20, 20, 20, 110))
            screen.blit(overlay, (self.x_offset, self.y_offset))

    def handle_event(self, event, is_my_turn):
        if not is_my_turn or self.is_eliminated:
            return False
            
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_x, mouse_y = event.pos
            if (self.x_offset <= mouse_x < self.x_offset + BOARD_SIZE * self.cell_size and 
                self.y_offset <= mouse_y < self.y_offset + BOARD_SIZE * self.cell_size):
                
                # Compute grid indices robustly and clamp to valid range
                rel_x = mouse_x - self.x_offset
                rel_y = mouse_y - self.y_offset
                # Use floor mapping like placement: top-left of cell selects that cell
                grid_x = int(rel_x // self.cell_size)
                grid_y = int(rel_y // self.cell_size)

                if grid_x < 0: grid_x = 0
                if grid_y < 0: grid_y = 0
                if grid_x >= BOARD_SIZE: grid_x = BOARD_SIZE - 1
                if grid_y >= BOARD_SIZE: grid_y = BOARD_SIZE - 1

                if self.grid[grid_y][grid_x] in (UNEXPLORED, SELECTED):
                    # Use same mapping as placement: floor division (top-left mapping)
                    self.clear_selection()
                    self.selected_coord = (grid_x, grid_y)
                    self.grid[grid_y][grid_x] = SELECTED
                    return True
        return False
        
    def get_selected_coord_str(self):
        if not self.selected_coord: return None
        letters = "ABCDEFGHIJKL"
        x, y = self.selected_coord
        return f"{letters[x]}{y+1}"
        
    def apply_result(self, coord_str, hit, sunk=False):
        letters = "ABCDEFGHIJKL"
        x = letters.index(coord_str[0])
        y = int(coord_str[1:]) - 1

        if not (0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE):
            return

        current = self.grid[y][x]
        if hit:
            if sunk or current == SUNK:
                self.grid[y][x] = SUNK
            else:
                self.grid[y][x] = HIT
        else:
            if current in (UNEXPLORED, SELECTED):
                self.grid[y][x] = WATER

        if self.selected_coord == (x, y):
            self.selected_coord = None

    def apply_sunk_cells(self, coord_list):
        if not coord_list:
            return
        letters = "ABCDEFGHIJKL"
        for coord_str in coord_list:
            if not coord_str:
                continue
            try:
                x = letters.index(coord_str[0])
                y = int(coord_str[1:]) - 1
            except (ValueError, IndexError):
                continue
            if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE:
                self.grid[y][x] = SUNK
                if self.selected_coord == (x, y):
                    self.selected_coord = None


class BattleshipGame:
    """High-level Battleship game flow manager.
    Manages placement, attack boards, turns and network message handling.
    """
    def __init__(self, net_manager=None):
        self.net = net_manager
        self.my_board = None
        self.player_commits = {}
        self.has_committed_board = False
        self.battle_phase = False
        self.attack_boards = []
        self.all_players_sorted = []
        self.current_turn_index = 0
        self.eliminated_players = set()
        self.elimination_order = []
        self.game_over = False
        self.final_ranking = []
        self.winner_peer_id = None

    def start_placement(self, width, height, cell_size=30):
        # create a centered board; main program may call update_ui_layout to reposition
        board_px = BOARD_SIZE * cell_size
        x = width//2 - board_px//2
        y = height//2 - board_px//2
        self.my_board = Board(x, y, cell_size)
        self.player_commits.clear()
        self.has_committed_board = False
        self.battle_phase = False
        self.attack_boards.clear()
        self.eliminated_players.clear()
        self.elimination_order.clear()
        self.all_players_sorted.clear()
        self.current_turn_index = 0
        self.game_over = False
        self.final_ranking.clear()
        self.winner_peer_id = None

    def _first_alive_index(self):
        for i, p in enumerate(self.all_players_sorted):
            if p not in self.eliminated_players:
                return i
        return None

    def ensure_current_turn_is_alive(self):
        if not self.all_players_sorted:
            return
        if not (0 <= self.current_turn_index < len(self.all_players_sorted)):
            idx = self._first_alive_index()
            if idx is not None:
                self.current_turn_index = idx
            return
        current_player = self.all_players_sorted[self.current_turn_index]
        if current_player not in self.eliminated_players:
            return
        n = len(self.all_players_sorted)
        i = self.current_turn_index
        for _ in range(n):
            i = (i + 1) % n
            if self.all_players_sorted[i] not in self.eliminated_players:
                self.current_turn_index = i
                return

    def advance_turn_to_next_alive(self):
        if not self.all_players_sorted:
            return
        if not (0 <= self.current_turn_index < len(self.all_players_sorted)):
            idx = self._first_alive_index()
            if idx is not None:
                self.current_turn_index = idx
            return
        n = len(self.all_players_sorted)
        i = self.current_turn_index
        for _ in range(n):
            i = (i + 1) % n
            if self.all_players_sorted[i] not in self.eliminated_players:
                self.current_turn_index = i
                return

    def refresh_attack_boards_elimination_state(self):
        for ab in self.attack_boards:
            ab.is_eliminated = (ab.target_peer_id in self.eliminated_players)
            if ab.is_eliminated:
                ab.clear_selection()

    def announce_elimination(self, peer_id, source="local"):
        if peer_id in self.eliminated_players:
            return
        self.eliminated_players.add(peer_id)
        if peer_id not in self.elimination_order:
            self.elimination_order.append(peer_id)
        self.refresh_attack_boards_elimination_state()
        if self.net and peer_id == getattr(self.net, 'peer_id', None):
            for ab in self.attack_boards:
                ab.clear_selection()
        # check winners
        alive = [p for p in (sorted(list(self.net.peers.keys()) + [self.net.peer_id]) if self.net else []) if p not in self.eliminated_players]
        if len(alive) <= 1:
            self.game_over = True
            # build final ranking
            ordered = [p for p in self.elimination_order if p not in alive]
            self.final_ranking = list(reversed(alive)) + list(reversed(ordered))
            self.winner_peer_id = self.final_ranking[0] if self.final_ranking else None
        else:
            self.ensure_current_turn_is_alive()

        if source == "local" and self.net:
            try:
                self.net.send_event("PLAYER_ELIMINATED", eliminated_peer=peer_id)
                if self.game_over:
                    self.net.send_event("GAME_OVER", winner_peer=self.winner_peer_id, ranking=self.final_ranking)
            except Exception:
                pass

    def handle_event(self, event):
        # placement
        if self.my_board and not self.battle_phase:
            self.my_board.handle_event(event)
            if self.my_board.is_ready and not self.has_committed_board and self.net:
                board_hash = self.my_board.get_board_hash()
                try:
                    self.net.send_event("COMMIT_BOARD", board_hash=board_hash)
                except Exception:
                    pass
                self.has_committed_board = True
        elif self.battle_phase:
            if self.game_over:
                return
            self.ensure_current_turn_is_alive()
            turn_owner = self.all_players_sorted[self.current_turn_index] if self.all_players_sorted else None
            is_my_turn = (not self.game_over and turn_owner == getattr(self.net, 'peer_id', None) and getattr(self.net, 'peer_id', None) not in self.eliminated_players)
            for ab in self.attack_boards:
                ab.handle_event(event, is_my_turn)
            # returning whether a FIRE_MULTI needs to be sent is handled by caller via checking attack_boards selection

    def on_network_message(self, msg):
        action = msg.get('action')
        if action == 'START_GAME':
            # Host started the match
            self.start_placement(msg.get('width', 800), msg.get('height', 600))
            return
        if action == 'COMMIT_BOARD':
            peer_id = msg.get('peerId')
            b_hash = msg.get('board_hash')
            self.player_commits[peer_id] = b_hash
            return
        if action == 'FIRE_MULTI':
            targets = msg.get('targets') or []
            sender = msg.get('peerId')
            if self.battle_phase and not self.game_over and sender and sender not in self.eliminated_players:
                if sender in self.all_players_sorted:
                    self.current_turn_index = self.all_players_sorted.index(sender)
                self.advance_turn_to_next_alive()
            for t in targets:
                if t.get('target_peer') == getattr(self.net, 'peer_id', None):
                    coord = t.get('coord')
                    try:
                        letters = "ABCDEFGHIJKL"
                        x = letters.index(coord[0])
                        y = int(coord[1:]) - 1
                    except Exception:
                        continue
                    shot_result = self.my_board.receive_shot(x, y)
                    hit = shot_result.get('hit', False)
                    sunk = shot_result.get('sunk', False)
                    sunk_cells = shot_result.get('sunk_cells', [])
                    eliminated_now = shot_result.get('eliminated', False)
                    # send result back
                    if self.net:
                        try:
                            letters = "ABCDEFGHIJKL"
                            sunk_cells_coord = [f"{letters[cx]}{cy+1}" for (cx, cy) in sunk_cells]
                            self.net.send_event('RESULT', target_peer=sender, coord=coord, hit=hit, sunk=sunk, sunk_cells=sunk_cells_coord, eliminated=eliminated_now, eliminated_peer=(self.net.peer_id if eliminated_now else None))
                        except Exception:
                            pass
                    if eliminated_now:
                        self.announce_elimination(getattr(self.net, 'peer_id', None), source='local')
            return
        if action == 'RESULT':
            target_peer = msg.get('target_peer')
            coord = msg.get('coord')
            hit = msg.get('hit')
            sender = msg.get('peerId')
            sunk = msg.get('sunk', False)
            sunk_cells = msg.get('sunk_cells') or []
            eliminated_flag = msg.get('eliminated', False)
            eliminated_peer = msg.get('eliminated_peer') or sender
            for ab in self.attack_boards:
                if ab.target_peer_id == sender:
                    if coord:
                        ab.apply_result(coord, hit, sunk=sunk)
                    if sunk and sunk_cells:
                        ab.apply_sunk_cells(sunk_cells)
            if target_peer == getattr(self.net, 'peer_id', None):
                pass
            if eliminated_flag and eliminated_peer:
                self.announce_elimination(eliminated_peer, source='remote')
            return
        if action == 'PLAYER_ELIMINATED':
            eliminated_peer = msg.get('eliminated_peer') or msg.get('peerId')
            if eliminated_peer:
                self.announce_elimination(eliminated_peer, source='remote')
            return
        if action == 'GAME_OVER':
            winner_peer = msg.get('winner_peer')
            ranking = msg.get('ranking') or []
            if ranking:
                self.game_over = True
                self.final_ranking = ranking
                self.winner_peer_id = winner_peer or ranking[0]
            elif winner_peer:
                self.game_over = True
                self.winner_peer_id = winner_peer
                # best effort
                self.final_ranking = []
            return

    def start_battle_if_ready(self):
        # called to check if all players committed and transition to battle
        if not self.my_board or not self.my_board.is_ready:
            return False
        if not self.net:
            return False
        total_players = 1 + len(self.net.peers)
        ready_count = len(self.player_commits) + (1 if self.has_committed_board else 0)
        if ready_count >= total_players:
            # all ready -> start battle
            self.battle_phase = True
            self.all_players_sorted = sorted(list(self.net.peers.keys()) + [self.net.peer_id])
            self.current_turn_index = 0
            self.attack_boards = []
            # create attack boards (positions will be updated by caller)
            for p in self.net.peers.keys():
                self.attack_boards.append(AttackBoard(p, 0, 100))
            return True
        return False

    def draw(self, screen, font_small, font_normal, font_title, width, height):
        # placement
        if not self.battle_phase:
            if self.my_board:
                self.my_board.draw(screen, font_small)
                if self.my_board.is_ready:
                    ready_count = len(self.player_commits) + (1 if self.has_committed_board else 0)
                    total_players = len(self.net.peers) + 1 if self.net else 1
                    status_text = f"Jugadores listos: {ready_count} / {total_players}"
                    status_lbl = font_normal.render(status_text, True, (200,200,200))
                    screen.blit(status_lbl, (width//2 - status_lbl.get_width()//2, height - 50))
        else:
            # battle drawing
            layout = None
            # basic layout computation (caller may supply compute_battle_layout)
            self.ensure_current_turn_is_alive()
            turn_player = self.all_players_sorted[self.current_turn_index] if self.all_players_sorted else None
            i_am_eliminated = (getattr(self.net, 'peer_id', None) in self.eliminated_players)
            is_my_turn = (not self.game_over and not i_am_eliminated and turn_player == getattr(self.net, 'peer_id', None))
            if self.game_over:
                turn_text = f"🏆 Ganador: {self.winner_peer_id}" if self.winner_peer_id else "Partida terminada"
                color = (255,215,80)
            elif i_am_eliminated:
                turn_text = "Has sido eliminado"
                color = (255,120,120)
            else:
                turn_text = "¡Es tu turno!" if is_my_turn else f"Turno de {turn_player}..."
                color = (50,255,50) if is_my_turn else (200,200,200)
            turn_lbl = font_title.render(turn_text, True, color)
            screen.blit(turn_lbl, (width//2 - turn_lbl.get_width()//2, 40))
            # attack boards
            # Use offsets provided by caller (main layout); only apply defaults when offsets are unset (0)
            y = 100
            for ab in self.attack_boards:
                if not getattr(ab, 'x_offset', 0):
                    ab.x_offset = max(20, width//2 - (BOARD_SIZE * ab.cell_size)//2)
                if not getattr(ab, 'y_offset', 0):
                    ab.y_offset = y
                ab.draw(screen, font_small, is_their_turn=(ab.target_peer_id == turn_player))
                y += BOARD_SIZE*ab.cell_size + 12
            # defense board
            if self.my_board:
                defense_label_y = self.my_board.y_offset - font_small.get_height() - 6
                my_lbl_color = (255,120,120) if i_am_eliminated else ((255,255,0) if is_my_turn else (255,255,255))
                defense_label_txt = "Tu tablero de defensa" + (" (ELIMINADO)" if i_am_eliminated else ":")
                lbl_defense = font_small.render(defense_label_txt, True, my_lbl_color)
                screen.blit(lbl_defense, (self.my_board.x_offset, defense_label_y))
                self.my_board.draw(screen, font_small, show_status_text=False)
            # game over overlay
            if self.game_over:
                overlay = pygame.Surface((width, height), pygame.SRCALPHA)
                overlay.fill((10,10,20,170))
                screen.blit(overlay, (0,0))
                panel_w = min(560, max(360, width - 120))
                panel_h = min(420, max(260, height - 120))
                panel_x = (width - panel_w)//2
                panel_y = (height - panel_h)//2
                panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
                pygame.draw.rect(screen, (30,35,55), panel_rect, border_radius=10)
                pygame.draw.rect(screen, (230,230,230), panel_rect, 2, border_radius=10)
                title = font_title.render("Fin de la partida", True, (255,255,255))
                screen.blit(title, (panel_x + panel_w//2 - title.get_width()//2, panel_y + 18))
                winner_text = f"Ganador: {self.winner_peer_id}" if self.winner_peer_id else "Ganador: (desconocido)"
                winner_lbl = font_normal.render(winner_text, True, (255,215,80))
                screen.blit(winner_lbl, (panel_x + panel_w//2 - winner_lbl.get_width()//2, panel_y + 80))
