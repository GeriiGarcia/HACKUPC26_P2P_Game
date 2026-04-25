import pygame
import random
import string
import hashlib

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

# Ya disparada (agua o barco dañado/hundido)
        if cell == 2:
            return {"hit": False, "sunk": False, "sunk_cells": [], "eliminated": self.are_all_ships_sunk()}

        if cell in (3, 4):
            already_hit = cell in (3, 4)
            # No revelar las celdas del barco si no las golpeaste vos.
            # Si el barco ya estaba hundido (por otro atacante), solo confirmar hit.
            return {"hit": already_hit, "sunk": False, "sunk_cells": [], "eliminated": self.are_all_ships_sunk()}

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
                
                grid_x = (mouse_x - self.x_offset) // self.cell_size
                grid_y = (mouse_y - self.y_offset) // self.cell_size
                
                if self.grid[grid_y][grid_x] == UNEXPLORED or self.grid[grid_y][grid_x] == SELECTED:
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
