import pygame

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
                    # Pegar desde el portapapeles
                    import subprocess
                    try:
                        res = subprocess.run(['wl-paste'], capture_output=True, text=True, check=True)
                        self.text += res.stdout.strip()
                    except (FileNotFoundError, subprocess.CalledProcessError):
                        try:
                            res = subprocess.run(['xclip', '-selection', 'clipboard', '-o'], capture_output=True, text=True, check=True)
                            self.text += res.stdout.strip()
                        except (FileNotFoundError, subprocess.CalledProcessError):
                            pass
                else:
                    # Evitar caracteres raros si se presiona Ctrl
                    if not (pygame.key.get_mods() & pygame.KMOD_CTRL):
                        self.text += event.unicode
