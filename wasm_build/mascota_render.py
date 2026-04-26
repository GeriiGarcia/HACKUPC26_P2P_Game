import pygame
import math
from ui import Button
from mascota_core import STATE_IDLE, STATE_EATING, STATE_SLEEPING, STATE_PLAYING, STATE_DIRTY

# Colores de la habitación
BG_COLOR = (245, 230, 200)       # Paredes (crema cálido)
FLOOR_COLOR = (140, 100, 70)     # Suelo (madera)

# Colores UI
BAR_BG = (100, 100, 100)
COLOR_HUNGER = (220, 80, 80)
COLOR_ENERGY = (220, 200, 50)
COLOR_FUN = (80, 180, 80)
COLOR_CLEAN = (80, 150, 220)

class Renderer:
    def __init__(self, width, height, font_normal):
        self.width = width
        self.height = height
        self.font = font_normal
        
        # Botones UI globales (acciones a enviar sobre la mascota seleccionada o propia)
        btn_w, btn_h = 100, 40
        padding = 10
        start_x = width // 2 - (btn_w * 4 + padding * 3) // 2
        y_pos = height - 60
        
        self.btn_feed = Button(start_x, y_pos, btn_w, btn_h, "Dar Comida", font_normal, bg_color=(200, 80, 80))
        self.btn_play = Button(start_x + (btn_w + padding), y_pos, btn_w, btn_h, "Jugar", font_normal, bg_color=(80, 180, 80))
        self.btn_sleep = Button(start_x + (btn_w + padding)*2, y_pos, btn_w, btn_h, "Dormir", font_normal, bg_color=(200, 200, 50))
        self.btn_clean = Button(start_x + (btn_w + padding)*3, y_pos, btn_w, btn_h, "Limpiar", font_normal, bg_color=(80, 150, 200))

        self.buttons = [self.btn_feed, self.btn_play, self.btn_sleep, self.btn_clean]

    def resize(self, width, height):
        self.width = width
        self.height = height
        btn_w, btn_h = 100, 40
        padding = 10
        start_x = width // 2 - (btn_w * 4 + padding * 3) // 2
        y_pos = height - 60
        
        self.btn_feed.rect.x = start_x
        self.btn_feed.rect.y = y_pos
        self.btn_play.rect.x = start_x + (btn_w + padding)
        self.btn_play.rect.y = y_pos
        self.btn_sleep.rect.x = start_x + (btn_w + padding)*2
        self.btn_sleep.rect.y = y_pos
        self.btn_clean.rect.x = start_x + (btn_w + padding)*3
        self.btn_clean.rect.y = y_pos

    def handle_event(self, event):
        """Procesa eventos de UI y devuelve el nombre de la acción si se hace click"""
        if self.btn_feed.handle_event(event): return "feed"
        if self.btn_play.handle_event(event): return "play"
        if self.btn_sleep.handle_event(event): return "sleep"
        if self.btn_clean.handle_event(event): return "clean"
        return None

    def _draw_room(self, screen):
        # Pared
        screen.fill(BG_COLOR)
        # Suelo
        floor_rect = pygame.Rect(0, 400, self.width, self.height - 400)
        pygame.draw.rect(screen, FLOOR_COLOR, floor_rect)
        # Zócalo
        zocalo_rect = pygame.Rect(0, 390, self.width, 10)
        pygame.draw.rect(screen, (100, 70, 50), zocalo_rect)

    def _draw_bar(self, screen, x, y, width, height, value, color):
        pygame.draw.rect(screen, BAR_BG, (x, y, width, height))
        fill_width = int(width * (value / 100.0))
        if fill_width > 0:
            pygame.draw.rect(screen, color, (x, y, fill_width, height))
        pygame.draw.rect(screen, (0,0,0), (x, y, width, height), 1)

    def _draw_pet(self, screen, pet, is_mine):
        # Base body
        color = (255, 150, 150) if is_mine else (150, 150, 255)
        pet_w, pet_h = 60, 60
        
        # Animación básica según estado
        y_offset = 0
        if pet.state == STATE_PLAYING:
            y_offset = math.sin(pygame.time.get_ticks() / 100) * 10
        elif pet.state == STATE_SLEEPING:
            pet_w, pet_h = 70, 40
            y_offset = 20
        
        draw_x = int(pet.x - pet_w/2)
        draw_y = int(pet.y - pet_h) + y_offset

        # Cuerpo
        pygame.draw.ellipse(screen, color, (draw_x, draw_y, pet_w, pet_h))
        pygame.draw.ellipse(screen, (0,0,0), (draw_x, draw_y, pet_w, pet_h), 2)

        # Ojos
        if pet.state == STATE_SLEEPING:
            pygame.draw.line(screen, (0,0,0), (draw_x + 15, draw_y + 20), (draw_x + 25, draw_y + 20), 2)
            pygame.draw.line(screen, (0,0,0), (draw_x + 35, draw_y + 20), (draw_x + 45, draw_y + 20), 2)
        elif pet.state == STATE_EATING:
            pygame.draw.circle(screen, (0,0,0), (draw_x + 20, draw_y + 20), 4)
            pygame.draw.circle(screen, (0,0,0), (draw_x + 40, draw_y + 20), 4)
            # Boca abierta
            pygame.draw.circle(screen, (0,0,0), (draw_x + 30, draw_y + 35), 6)
        else:
            pygame.draw.circle(screen, (0,0,0), (draw_x + 20, draw_y + 20), 4)
            pygame.draw.circle(screen, (0,0,0), (draw_x + 40, draw_y + 20), 4)
            # Boca
            pygame.draw.arc(screen, (0,0,0), (draw_x + 20, draw_y + 25, 20, 10), 3.14, 0, 2)

        # Suciedad
        if pet.cleanliness < 30 or pet.state == STATE_DIRTY:
            pygame.draw.circle(screen, (100, 100, 50), (draw_x + 10, draw_y + 10), 5)
            pygame.draw.circle(screen, (100, 100, 50), (draw_x + 50, draw_y + 40), 6)
            pygame.draw.circle(screen, (100, 100, 50), (draw_x + 20, draw_y + 50), 4)

        # Etiqueta de nombre
        tag = f"{pet.owner_id}" + (" (Tú)" if is_mine else "")
        lbl = self.font.render(tag, True, (0, 0, 0))
        screen.blit(lbl, (draw_x + pet_w//2 - lbl.get_width()//2, draw_y - 25))

        # Barras de estado arriba de la mascota
        bar_w = 40
        bar_x = draw_x + pet_w//2 - bar_w//2
        bar_y = draw_y - 40
        self._draw_bar(screen, bar_x, bar_y, bar_w, 4, pet.hunger, COLOR_HUNGER)
        self._draw_bar(screen, bar_x, bar_y - 6, bar_w, 4, pet.energy, COLOR_ENERGY)
        self._draw_bar(screen, bar_x, bar_y - 12, bar_w, 4, pet.fun, COLOR_FUN)
        self._draw_bar(screen, bar_x, bar_y - 18, bar_w, 4, pet.cleanliness, COLOR_CLEAN)

    def render(self, screen, pets, my_peer_id):
        self._draw_room(screen)

        # Dibujar mascotas (ordenar por Y para perspectiva fake si se movieran en Y, pero aquí Y es estático, así que da igual)
        for p_id, pet in pets.items():
            self._draw_pet(screen, pet, is_mine=(p_id == my_peer_id))

        # Dibujar UI
        for btn in self.buttons:
            btn.draw(screen)

        # Si hay más de un jugador (una visita), mostrar cartel
        if len(pets) > 1:
            lbl = self.font.render(f"¡Tienes visitas! ({len(pets)-1} amigo/s en la sala)", True, (50, 100, 50))
            screen.blit(lbl, (self.width // 2 - lbl.get_width() // 2, 20))
