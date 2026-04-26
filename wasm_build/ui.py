import pygame
import sys

class Button:
    def __init__(self, x, y, width, height, text, font, bg_color=(100, 100, 100), text_color=(255, 255, 255), hover_color=(150, 150, 150)):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.font = font
        self.bg_color = bg_color
        self.text_color = text_color
        self.hover_color = hover_color
        self.is_hovered = False

    def draw(self, screen):
        color = self.hover_color if self.is_hovered else self.bg_color
        pygame.draw.rect(screen, color, self.rect, border_radius=5)
        pygame.draw.rect(screen, (0, 0, 0), self.rect, 2, border_radius=5) # Border
        
        text_surf = self.font.render(self.text, True, self.text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.is_hovered:
                return True
        return False


class TextInput:
    def __init__(self, x, y, width, height, font, text_color=(0, 0, 0), bg_color=(255, 255, 255), active_color=(200, 255, 200)):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = ""
        self.font = font
        self.text_color = text_color
        self.bg_color = bg_color
        self.active_color = active_color
        self.is_active = False

    def draw(self, screen):
        color = self.active_color if self.is_active else self.bg_color
        pygame.draw.rect(screen, color, self.rect)
        pygame.draw.rect(screen, (0, 0, 0), self.rect, 2) # Border
        
        # Render text
        text_surf = self.font.render(self.text, True, self.text_color)
        # Handle text longer than input box
        if text_surf.get_width() > self.rect.width - 10:
            text_surf = self.font.render(self.text[-(self.rect.width//10):], True, self.text_color) # Simple truncation for now
            
        screen.blit(text_surf, (self.rect.x + 5, self.rect.y + (self.rect.height - text_surf.get_height()) // 2))

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self.is_active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN:
            if self.is_active:
                if event.key == pygame.K_RETURN:
                    pass # Handled externally usually
                elif event.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                elif event.key == pygame.K_v and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    print("Intentando pegar desde el portapapeles (Ctrl+V detectado)...")
                    # En WASM, solo permitimos pegar a través de un prompt del navegador por simplicidad y seguridad
                    if sys.platform == 'emscripten':
                        # En WASM, Ctrl+V suele estar bloqueado o causar problemas de foco.
                        # Usaremos un botón dedicado en la UI que invoque el pegado de forma segura.
                        print("Ctrl+V detectado en WASM. Por favor, usa el botón 'Pegar'.")
                        pass
                    else:
                        # Fallbacks nativos (Tkinter, wl-paste, xclip) - SOLO EN DESKTOP
                        success = False
                        try:
                            import tkinter as tk
                            root = tk.Tk()
                            root.withdraw()
                            pasted_text = root.clipboard_get()
                            if pasted_text:
                                self.text += pasted_text.strip()
                                success = True
                            root.destroy()
                        except: pass

                        if not success:
                            import subprocess
                            try:
                                res = subprocess.run(['wl-paste'], capture_output=True, text=True, check=True)
                                if res.stdout:
                                    self.text += res.stdout.strip()
                                    success = True
                            except: pass
                            
                        if not success:
                            try:
                                res = subprocess.run(['xclip', '-selection', 'clipboard', '-o'], capture_output=True, text=True, check=True)
                                if res.stdout:
                                    self.text += res.stdout.strip()
                                    success = True
                            except: pass
                    
                    if not success:
                        print("❌ No se pudo pegar. Asegúrate de tener 'wl-clipboard' o 'xclip' instalado, o pega el texto a mano.")
                else:
                    # Evitar caracteres raros si se presiona Ctrl
                    if not (pygame.key.get_mods() & pygame.KMOD_CTRL):
                        self.text += event.unicode

class CraftingMenu:
    def __init__(self, recipes, item_names):
        self.recipes = recipes
        self.item_names = item_names
        self.is_open = False

    def toggle(self):
        self.is_open = not self.is_open

class EscapeMenu:
    def __init__(self, screen, clock, font):
        self.screen = screen
        self.clock = clock
        self.font = font
        self.width, self.height = screen.get_size()
        
        # Colors
        self.overlay_color = (10, 10, 20, 180)
        self.panel_color = (30, 35, 55)
        self.border_color = (230, 230, 230)
        self.blue = (40, 120, 255)
        self.dark_blue = (20, 80, 200)
        
        # Panel dimensions
        self.panel_w = 400
        self.panel_h = 300
        self.panel_x = (self.width - self.panel_w) // 2
        self.panel_y = (self.height - self.panel_h) // 2
        
        # Buttons
        btn_w, btn_h = 300, 44
        btn_x = self.panel_x + (self.panel_w - btn_w) // 2
        
        self.btn_resume = Button(btn_x, self.panel_y + 80, btn_w, btn_h, "Volver", font, bg_color=self.blue, hover_color=self.dark_blue)
        self.btn_lobby = Button(btn_x, self.panel_y + 140, btn_w, btn_h, "Volver al Lobby", font)
        self.btn_exit = Button(btn_x, self.panel_y + 200, btn_w, btn_h, "Salir de la APP", font, bg_color=(200, 50, 50), hover_color=(255, 80, 80))

    def show(self):
        running = True
        result = "RESUME"
        
        # Create a surface for the semi-transparent overlay
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill(self.overlay_color)
        
        while running:
            self.screen.blit(overlay, (0, 0))
            
            # Draw Panel
            pygame.draw.rect(self.screen, self.panel_color, (self.panel_x, self.panel_y, self.panel_w, self.panel_h), border_radius=10)
            pygame.draw.rect(self.screen, self.border_color, (self.panel_x, self.panel_y, self.panel_w, self.panel_h), 2, border_radius=10)
            
            # Title
            title_surf = self.font.render("MENÚ DE PAUSA", True, (255, 255, 255))
            self.screen.blit(title_surf, (self.panel_x + (self.panel_w - title_surf.get_width()) // 2, self.panel_y + 25))
            
            # Draw Buttons
            self.btn_resume.draw(self.screen)
            self.btn_lobby.draw(self.screen)
            self.btn_exit.draw(self.screen)
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "EXIT"
                
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return "RESUME"
                
                if self.btn_resume.handle_event(event):
                    return "RESUME"
                if self.btn_lobby.handle_event(event):
                    return "LOBBY"
                if self.btn_exit.handle_event(event):
                    return "EXIT"
            
            pygame.display.flip()
            self.clock.tick(60)
        
        return result
