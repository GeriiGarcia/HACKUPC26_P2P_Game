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
                    print("Intentando pegar desde el portapapeles (Ctrl+V detectado)...")
                    success = False
                    
                    # 1. Intentar con Tkinter (Nativo de Python y suele funcionar bien)
                    try:
                        import tkinter as tk
                        root = tk.Tk()
                        root.withdraw()
                        pasted_text = root.clipboard_get()
                        if pasted_text:
                            self.text += pasted_text.strip()
                            success = True
                        root.destroy()
                    except Exception as e:
                        print(f"[DEBUG] Tkinter falló: {e}")
                    
                    # 2. Intentar con wl-paste (Wayland)
                    if not success:
                        import subprocess
                        try:
                            res = subprocess.run(['wl-paste'], capture_output=True, text=True, check=True)
                            if res.stdout:
                                self.text += res.stdout.strip()
                                success = True
                        except Exception as e:
                            print(f"[DEBUG] wl-paste falló: {e}")
                            
                    # 3. Intentar con xclip (X11)
                    if not success:
                        try:
                            res = subprocess.run(['xclip', '-selection', 'clipboard', '-o'], capture_output=True, text=True, check=True)
                            if res.stdout:
                                self.text += res.stdout.strip()
                                success = True
                        except Exception as e:
                            print(f"[DEBUG] xclip falló: {e}")
                            
                    if not success:
                        print("❌ No se pudo pegar. Asegúrate de tener 'wl-clipboard' o 'xclip' instalado, o pega el texto a mano.")
                else:
                    # Evitar caracteres raros si se presiona Ctrl
                    if not (pygame.key.get_mods() & pygame.KMOD_CTRL):
                        self.text += event.unicode


class CraftingMenu:
    """Menú gráfico para fabricar items. Muestra recetas y permite click para crear."""
    
    def __init__(self, crafting_recipes, item_names, x=50, y=50, item_size=80, gap=10):
        """
        crafting_recipes: dict {item_id: {req_id: qty, ...}}
        item_names: dict {item_id: "name"}
        """
        self.crafting_recipes = crafting_recipes
        self.item_names = item_names
        self.x = x
        self.y = y
        self.item_size = item_size
        self.gap = gap
        self.items_buttons = {}  # item_id -> Button para cada item que se puede fabricar
        self.is_open = False
        self._build_buttons()
    
    def _build_buttons(self):
        """Construye botones para cada item que se puede fabricar."""
        self.items_buttons = {}
        row, col = 0, 0
        for item_id in sorted(self.crafting_recipes.keys()):
            item_name = self.item_names.get(item_id, f"Item {item_id}")
            btn_x = self.x + col * (self.item_size + self.gap)
            btn_y = self.y + row * (self.item_size + self.gap)
            
            # Crear botón cuadrado para el item
            btn = Button(btn_x, btn_y, self.item_size, self.item_size, item_name, 
                        font=pygame.font.SysFont(None, 16),
                        bg_color=(100, 150, 100), text_color=(255, 255, 255),
                        hover_color=(150, 200, 150))
            self.items_buttons[item_id] = btn
            
            col += 1
            if col >= 3:  # 3 items por fila
                col = 0
                row += 1
    
    def open(self):
        self.is_open = True
    
    def close(self):
        self.is_open = False
    
    def toggle(self):
        self.is_open = not self.is_open
    
    def draw(self, screen, font_small, player_inventory):
        """Dibuja el menú si está abierto."""
        if not self.is_open:
            return
        
        # Título del menú
        title_font = pygame.font.SysFont(None, 32, bold=True)
        title_text = title_font.render("MENÚ DE FABRICACIÓN (Presiona E para cerrar)", True, (255, 255, 255))
        screen.blit(title_text, (self.x, self.y - 50))
        
        # Dibujar cada botón de item
        for item_id, btn in self.items_buttons.items():
            btn.draw(screen)
            
            # Dibujar requisitos debajo del botón
            recipe = self.crafting_recipes.get(item_id, {})
            can_craft = self._can_craft(item_id, player_inventory)
            
            # Color de disponibilidad
            req_color = (100, 255, 100) if can_craft else (255, 100, 100)
            req_text = self._format_recipe(recipe)
            req_surf = font_small.render(req_text, True, req_color)
            req_rect = req_surf.get_rect(topleft=(btn.rect.x, btn.rect.y + btn.rect.height + 5))
            screen.blit(req_surf, req_rect)
    
    def _can_craft(self, item_id, player_inventory):
        """Verifica si el jugador puede fabricar un item."""
        recipe = self.crafting_recipes.get(item_id, {})
        for req_id, req_qty in recipe.items():
            if player_inventory.get(req_id, 0) < req_qty:
                return False
        return True
    
    def _format_recipe(self, recipe):
        """Formatea los requisitos en string legible."""
        parts = []
        for item_id, qty in recipe.items():
            name = self.item_names.get(item_id, f"Item {item_id}")
            parts.append(f"{qty}x {name}")
        return " + ".join(parts) if parts else "Desconocido"
    
    def handle_event(self, event, player_inventory, on_craft_callback=None):
        """
        Maneja eventos del menú.
        on_craft_callback: función que se llama con (item_id) cuando se fabrica algo.
        """
        if not self.is_open:
            return False
        
        for item_id, btn in self.items_buttons.items():
            if btn.handle_event(event):
                if self._can_craft(item_id, player_inventory):
                    if on_craft_callback:
                        on_craft_callback(item_id)
                    return True
        return False
