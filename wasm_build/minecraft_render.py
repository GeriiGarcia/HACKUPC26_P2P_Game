import pygame
import math
from OpenGL.GL import *
from OpenGL.GLU import *
from minecraft_core import (
    B_AIR, B_DIRT, B_STONE, B_WOOD, B_WHEAT, B_GRASS, B_LEAF,
    B_SAND, B_FLOWER_RED, B_FLOWER_YELLOW, B_CHEST,
    WORLD_WIDTH, WORLD_HEIGHT, ITEM_NAMES, CRAFTING_RECIPES
)

# =====================================================================
# Stardew Valley inspired palette – warm, earthy, cozy
# =====================================================================

# Sky gradient (top → bottom)
SKY_TOP    = (0.42, 0.65, 0.92)    # soft periwinkle
SKY_BOTTOM = (0.72, 0.85, 0.98)    # pale horizon

# Block colours  – each has a base + a subtle highlight for depth
BLOCK_COLORS = {
    B_GRASS:         ((0.36, 0.60, 0.20), (0.48, 0.72, 0.30)),   # lush green
    B_DIRT:          ((0.55, 0.36, 0.18), (0.62, 0.42, 0.22)),   # warm brown
    B_STONE:         ((0.52, 0.50, 0.48), (0.60, 0.58, 0.56)),   # grey-warm
    B_WOOD:          ((0.42, 0.26, 0.12), (0.52, 0.34, 0.16)),   # bark brown
    B_WHEAT:         ((0.88, 0.78, 0.30), (0.96, 0.88, 0.42)),   # golden wheat
    B_LEAF:          ((0.22, 0.52, 0.18), (0.30, 0.62, 0.24)),   # dark forest green
    B_SAND:          ((0.90, 0.82, 0.58), (0.95, 0.88, 0.65)),   # warm sand
    B_FLOWER_RED:    ((0.92, 0.78, 0.15), (0.98, 0.88, 0.25)),   # yellow variant
    B_FLOWER_YELLOW: ((0.95, 0.82, 0.18), (1.00, 0.90, 0.30)),   # sunflower
    B_CHEST:         ((0.60, 0.40, 0.20), (0.75, 0.55, 0.30)),   # larger wooden chest
}

# Players
COLOR_PLAYER       = (0.85, 0.35, 0.28)   # warm terracotta
COLOR_OTHER_PLAYER = (0.30, 0.65, 0.45)   # forest teal

# Item colours for hotbar icons
ITEM_COLORS = {
    1: BLOCK_COLORS[B_DIRT][0],
    2: BLOCK_COLORS[B_STONE][0],
    3: BLOCK_COLORS[B_WOOD][0],
    4: BLOCK_COLORS[B_WHEAT][0],
    7: BLOCK_COLORS[B_SAND][0],
    20: BLOCK_COLORS[B_CHEST][0],
}

BLOCK_SIZE_PX = 32

# Hotbar config
HOTBAR_SLOTS   = 10
HOTBAR_SLOT_SZ = 48
HOTBAR_PAD     = 6
HOTBAR_GAP     = 3
HOTBAR_MARGIN  = 12


class Renderer:
    def __init__(self, width, height):
        self.width  = width
        self.height = height
        self.setup_opengl(width, height)

    # ------------------------------------------------------------------
    # OpenGL init
    # ------------------------------------------------------------------
    def setup_opengl(self, width, height):
        self.width  = width
        self.height = height
        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        blocks_x = width  / BLOCK_SIZE_PX
        blocks_y = height / BLOCK_SIZE_PX
        gluOrtho2D(0, blocks_x, blocks_y, 0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glClearColor(*SKY_TOP, 1.0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    # ------------------------------------------------------------------
    # Main render
    # ------------------------------------------------------------------
    def render(self, world, players, my_peer_id,
               show_tab=False, show_inv=False, show_crafting=False, font=None):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        my_player = players.get(my_peer_id)
        if not my_player:
            return

        surf = pygame.display.get_surface()
        sw, sh = surf.get_size()
        if sw != self.width or sh != self.height:
            self.setup_opengl(sw, sh)

        blocks_x = self.width  / BLOCK_SIZE_PX
        blocks_y = self.height / BLOCK_SIZE_PX
        cam_x = max(0, min(my_player.x - blocks_x / 2.0, WORLD_WIDTH  - blocks_x))
        cam_y = max(0, min(my_player.y - blocks_y / 2.0, WORLD_HEIGHT - blocks_y))

        # Draw sky gradient BEFORE translating camera
        self._draw_sky(blocks_x, blocks_y)

        glTranslatef(-cam_x, -cam_y, 0)

        # Visible region
        sx = int(cam_x);          ex = int(cam_x + blocks_x) + 2
        sy = int(cam_y);          ey = int(cam_y + blocks_y) + 2

        # --- Blocks with depth shading ---
        glBegin(GL_QUADS)
        for y in range(max(0, sy), min(WORLD_HEIGHT, ey)):
            for x in range(max(0, sx), min(WORLD_WIDTH, ex)):
                b = world.get_block(x, y)
                if b == B_AIR:
                    continue
                colors = BLOCK_COLORS.get(b)
                if not colors:
                    continue
                base, hi = colors

                # Pseudo-random tint per block for organic feel
                noise = ((x * 374761393 + y * 668265263) & 0xFFFF) / 65535.0
                t = noise * 0.15  # 0..0.15 blend towards highlight
                r = base[0] + (hi[0] - base[0]) * t
                g = base[1] + (hi[1] - base[1]) * t
                bb = base[2] + (hi[2] - base[2]) * t
                glColor3f(r, g, bb)

                glVertex2f(x,     y    )
                glVertex2f(x + 1, y    )
                glVertex2f(x + 1, y + 1)
                glVertex2f(x,     y + 1)
        glEnd()

        # --- Soft block edges (subtle, not harsh grid) ---
        glColor4f(0, 0, 0, 0.08)
        glBegin(GL_LINES)
        for y in range(max(0, sy), min(WORLD_HEIGHT, ey)):
            for x in range(max(0, sx), min(WORLD_WIDTH, ex)):
                b = world.get_block(x, y)
                if b == B_AIR:
                    continue
                # Only draw edge where neighbour is air (silhouette)
                if world.get_block(x, y - 1) == B_AIR:
                    glVertex2f(x, y); glVertex2f(x + 1, y)
                if world.get_block(x + 1, y) == B_AIR:
                    glVertex2f(x + 1, y); glVertex2f(x + 1, y + 1)
                if world.get_block(x, y + 1) == B_AIR:
                    glVertex2f(x, y + 1); glVertex2f(x + 1, y + 1)
                if world.get_block(x - 1, y) == B_AIR:
                    glVertex2f(x, y); glVertex2f(x, y + 1)
        glEnd()

        # --- Grass tufts on top of grass blocks ---
        glColor4f(0.30, 0.55, 0.18, 0.9)
        glBegin(GL_TRIANGLES)
        for y in range(max(0, sy), min(WORLD_HEIGHT, ey)):
            for x in range(max(0, sx), min(WORLD_WIDTH, ex)):
                if world.get_block(x, y) == B_GRASS and world.get_block(x, y - 1) == B_AIR:
                    # Small grass blade triangles on top
                    cx = x + 0.3
                    glVertex2f(cx,       y)
                    glVertex2f(cx + 0.15, y - 0.18)
                    glVertex2f(cx + 0.3,  y)

                    cx2 = x + 0.6
                    glVertex2f(cx2,       y)
                    glVertex2f(cx2 + 0.1, y - 0.14)
                    glVertex2f(cx2 + 0.2, y)
        glEnd()

        # --- Players (Stardew-style coloured characters) ---
        for p_id, p in players.items():
            self._draw_player(p, p_id == my_peer_id, p_id, font, cam_x, cam_y)

        # --- HUD ---
        if font:
            self.draw_hotbar(my_player, font)
            if show_tab:
                self.draw_player_list(players, my_peer_id, font)
            if show_inv:
                self.draw_inventory_popup(my_player.inventory, font)
            if show_crafting:
                self.draw_crafting_menu(my_player.inventory, font)

    # ------------------------------------------------------------------
    # Sky gradient
    # ------------------------------------------------------------------
    def _draw_sky(self, blocks_x, blocks_y):
        """Full-screen gradient quad behind everything."""
        glBegin(GL_QUADS)
        glColor3f(*SKY_TOP)
        glVertex2f(0, 0)
        glVertex2f(blocks_x, 0)
        glColor3f(*SKY_BOTTOM)
        glVertex2f(blocks_x, blocks_y)
        glVertex2f(0, blocks_y)
        glEnd()

    # ------------------------------------------------------------------
    # Player drawing – simple but with body/head/eyes
    # ------------------------------------------------------------------
    def _draw_player(self, p, is_me, p_id, font, cam_x, cam_y):
        base = COLOR_PLAYER if is_me else COLOR_OTHER_PLAYER
        # Body
        glColor3f(*base)
        glBegin(GL_QUADS)
        glVertex2f(p.x,           p.y + 0.5)
        glVertex2f(p.x + p.width, p.y + 0.5)
        glVertex2f(p.x + p.width, p.y + p.height)
        glVertex2f(p.x,           p.y + p.height)
        glEnd()
        # Head
        hx = p.x + p.width * 0.1
        hw = p.width * 0.8
        glColor3f(0.92, 0.76, 0.60)  # skin tone
        glBegin(GL_QUADS)
        glVertex2f(hx,      p.y)
        glVertex2f(hx + hw, p.y)
        glVertex2f(hx + hw, p.y + 0.55)
        glVertex2f(hx,      p.y + 0.55)
        glEnd()
        # Eyes
        glColor3f(0.15, 0.15, 0.15)
        ex1 = p.x + p.width * 0.25
        ex2 = p.x + p.width * 0.55
        ey  = p.y + 0.18
        esz = 0.12
        glBegin(GL_QUADS)
        glVertex2f(ex1,       ey);       glVertex2f(ex1 + esz, ey)
        glVertex2f(ex1 + esz, ey + esz); glVertex2f(ex1,       ey + esz)
        glVertex2f(ex2,       ey);       glVertex2f(ex2 + esz, ey)
        glVertex2f(ex2 + esz, ey + esz); glVertex2f(ex2,       ey + esz)
        glEnd()
        # Outline
        darker = tuple(max(0, c - 0.2) for c in base)
        glColor3f(*darker)
        glLineWidth(1.5)
        glBegin(GL_LINE_LOOP)
        glVertex2f(p.x,           p.y)
        glVertex2f(p.x + p.width, p.y)
        glVertex2f(p.x + p.width, p.y + p.height)
        glVertex2f(p.x,           p.y + p.height)
        glEnd()
        glLineWidth(1)

        # Name above head
        if font and p_id:
            screen_x = (p.x - cam_x) * BLOCK_SIZE_PX
            screen_y = (p.y - cam_y) * BLOCK_SIZE_PX
            tw = font.size(p_id)[0]
            self.draw_text(p_id, screen_x + (p.width * BLOCK_SIZE_PX)/2 - tw/2, screen_y - 20, font, (255, 255, 255, 255))

    # ------------------------------------------------------------------
    # Hotbar (bottom centre)
    # ------------------------------------------------------------------
    def draw_hotbar(self, player, font):
        inv = player.inventory
        items = [(iid, amt) for iid, amt in inv.items()][:HOTBAR_SLOTS]

        n = HOTBAR_SLOTS
        total_w = n * HOTBAR_SLOT_SZ + (n - 1) * HOTBAR_GAP
        bar_x = (self.width - total_w) // 2
        bar_y = self.height - HOTBAR_SLOT_SZ - HOTBAR_MARGIN

        # Warm wooden bar background
        self._draw_rect_px(bar_x - 6, bar_y - 6,
                           total_w + 12, HOTBAR_SLOT_SZ + 12,
                           (0.28, 0.18, 0.08, 0.85))
        self._draw_rect_outline_px(bar_x - 6, bar_y - 6,
                                   total_w + 12, HOTBAR_SLOT_SZ + 12,
                                   (0.50, 0.35, 0.15, 1.0))

        for i in range(n):
            sx = bar_x + i * (HOTBAR_SLOT_SZ + HOTBAR_GAP)
            sy = bar_y

            is_selected = (i < len(items) and items[i][0] == player.selected_item)
            # Slot bg
            if is_selected:
                slot_bg = (0.92, 0.75, 0.25, 0.95)
            else:
                slot_bg = (0.22, 0.16, 0.08, 0.80)
            self._draw_rect_px(sx, sy, HOTBAR_SLOT_SZ, HOTBAR_SLOT_SZ, slot_bg)

            # Border
            if is_selected:
                border = (1.0, 0.88, 0.35, 1.0)
                self._draw_rect_outline_px(sx - 1, sy - 1,
                                           HOTBAR_SLOT_SZ + 2, HOTBAR_SLOT_SZ + 2, border)
            else:
                border = (0.45, 0.32, 0.15, 0.9)
                self._draw_rect_outline_px(sx, sy, HOTBAR_SLOT_SZ, HOTBAR_SLOT_SZ, border)

            if i < len(items):
                item_id, amount = items[i]
                # Block icon
                color = ITEM_COLORS.get(item_id, (0.7, 0.7, 0.7))
                pad = HOTBAR_PAD + 3
                self._draw_rect_px(sx + pad, sy + pad,
                                   HOTBAR_SLOT_SZ - pad * 2,
                                   HOTBAR_SLOT_SZ - pad * 2,
                                   (*color, 1.0))
                # Highlight edge on icon
                hi = tuple(min(1, c + 0.15) for c in color)
                self._draw_rect_outline_px(sx + pad, sy + pad,
                                           HOTBAR_SLOT_SZ - pad * 2,
                                           HOTBAR_SLOT_SZ - pad * 2,
                                           (*hi, 0.6))
                # Amount
                self.draw_text(str(amount),
                               sx + HOTBAR_SLOT_SZ - font.get_height(),
                               sy + HOTBAR_SLOT_SZ - font.get_height() - 2,
                               font, (255, 248, 200, 255))

        # Selected item label
        if player.selected_item in inv:
            name = ITEM_NAMES.get(player.selected_item, "")
            tw = font.size(f"[{name}]")[0] if hasattr(font, 'size') else len(name) * 8
            self.draw_text(f"[{name}]",
                           self.width // 2 - tw // 2,
                           bar_y - font.get_height() - 10,
                           font, (255, 240, 180, 255))

    def hotbar_slot_hit(self, mouse_x, mouse_y, inventory):
        items = [(iid, amt) for iid, amt in inventory.items()][:HOTBAR_SLOTS]
        n = HOTBAR_SLOTS
        total_w = n * HOTBAR_SLOT_SZ + (n - 1) * HOTBAR_GAP
        bar_x = (self.width - total_w) // 2
        bar_y = self.height - HOTBAR_SLOT_SZ - HOTBAR_MARGIN
        for i in range(len(items)):
            sx = bar_x + i * (HOTBAR_SLOT_SZ + HOTBAR_GAP)
            sy = bar_y
            if sx <= mouse_x <= sx + HOTBAR_SLOT_SZ and sy <= mouse_y <= sy + HOTBAR_SLOT_SZ:
                return items[i][0]
        return None

    # ------------------------------------------------------------------
    # Player list (TAB)
    # ------------------------------------------------------------------
    def draw_player_list(self, players, my_peer_id, font):
        panel_w = 280
        panel_h = 36 + len(players) * 30 + 14
        px = (self.width - panel_w) // 2
        py = 35
        self._draw_rect_px(px, py, panel_w, panel_h, (0.12, 0.10, 0.06, 0.88))
        self._draw_rect_outline_px(px, py, panel_w, panel_h, (0.55, 0.45, 0.20, 1.0))
        self.draw_text("Jugadores", px + 14, py + 8, font, (255, 230, 150, 255))
        y = py + 36
        for p_id in players.keys():
            c = (120, 230, 120, 255) if p_id == my_peer_id else (220, 215, 200, 255)
            tag = " (tu)" if p_id == my_peer_id else ""
            self.draw_text(f"  {p_id}{tag}", px + 14, y, font, c)
            y += 30

    # ------------------------------------------------------------------
    # Inventory popup (E)
    # ------------------------------------------------------------------
    def draw_inventory_popup(self, inventory, font):
        items = list(inventory.items())
        rows = max(1, len(items))
        panel_w = 300
        panel_h = 42 + rows * 28 + 14
        px = 24
        py = 24
        self._draw_rect_px(px, py, panel_w, panel_h, (0.10, 0.08, 0.04, 0.90))
        self._draw_rect_outline_px(px, py, panel_w, panel_h, (0.50, 0.40, 0.18, 1.0))
        self.draw_text("Inventario  [E]", px + 14, py + 10, font, (180, 240, 220, 255))
        y = py + 40
        if not items:
            self.draw_text("(vacio)", px + 18, y, font, (160, 155, 140, 255))
        else:
            for item_id, amount in items:
                name = ITEM_NAMES.get(item_id, f"#{item_id}")
                # small colour swatch
                color = ITEM_COLORS.get(item_id, (0.6, 0.6, 0.6))
                self._draw_rect_px(px + 18, y + 2, 14, 14, (*color, 1.0))
                self.draw_text(f"  {name}: x{amount}", px + 36, y, font, (230, 225, 210, 255))
                y += 28

    # ==================================================================
    def draw_crafting_menu(self, player_inventory, font):
        """Dibuja el menú de fabricación con los items que se pueden hacer."""
        panel_w = 400
        recipes_list = list(CRAFTING_RECIPES.items())
        rows = max(1, len(recipes_list))
        panel_h = 42 + rows * 28 + 14
        px = 24
        py = 24
        self._draw_rect_px(px, py, panel_w, panel_h, (0.15, 0.12, 0.08, 0.90))
        self._draw_rect_outline_px(px, py, panel_w, panel_h, (0.70, 0.55, 0.30, 1.0))
        self.draw_text("Menú de Fabricación  [C]", px + 14, py + 10, font, (220, 200, 120, 255))
        y = py + 40
        
        if not recipes_list:
            self.draw_text("(sin recetas)", px + 18, y, font, (160, 155, 140, 255))
        else:
            for item_id, requirements in recipes_list:
                name = ITEM_NAMES.get(item_id, f"#{item_id}")
                
                # Verificar si se puede fabricar
                can_craft = True
                req_text = []
                for req_id, req_qty in requirements.items():
                    player_qty = player_inventory.get(req_id, 0)
                    can_craft = can_craft and (player_qty >= req_qty)
                    req_name = ITEM_NAMES.get(req_id, f"#{req_id}")
                    req_text.append(f"{req_qty}x {req_name}")
                
                # Color según disponibilidad
                text_color = (100, 255, 100, 255) if can_craft else (255, 100, 100, 255)
                req_str = " + ".join(req_text) if req_text else "?"
                self.draw_text(f"  {name}: {req_str}", px + 18, y, font, text_color)
                y += 28

    def _chest_ui_layout(self, player_inventory, chest_inventory):
        p_items = sorted(player_inventory.items(), key=lambda kv: kv[0])
        c_items = sorted(chest_inventory.items(), key=lambda kv: kv[0])
        rows = max(1, len(p_items), len(c_items))

        panel_w = min(760, max(560, self.width - 40))
        panel_h = 86 + rows * 30 + 16
        px = (self.width - panel_w) // 2
        py = 24

        col_gap = 18
        col_w = (panel_w - 36 - col_gap) // 2
        left_x = px + 18
        right_x = left_x + col_w + col_gap
        header_y = py + 50
        row_h = 30

        return {
            "p_items": p_items,
            "c_items": c_items,
            "rows": rows,
            "px": px,
            "py": py,
            "panel_w": panel_w,
            "panel_h": panel_h,
            "left_x": left_x,
            "right_x": right_x,
            "col_w": col_w,
            "header_y": header_y,
            "row_h": row_h,
        }

    def draw_chest_popup(self, player_inventory, chest, font):
        """UI de cofre con transferencia click-to-transfer."""
        layout = self._chest_ui_layout(player_inventory, chest.inventory)
        px, py = layout["px"], layout["py"]
        panel_w, panel_h = layout["panel_w"], layout["panel_h"]
        left_x, right_x = layout["left_x"], layout["right_x"]
        col_w, row_h = layout["col_w"], layout["row_h"]
        p_items, c_items = layout["p_items"], layout["c_items"]

        self._draw_rect_px(px, py, panel_w, panel_h, (0.14, 0.10, 0.06, 0.94))
        self._draw_rect_outline_px(px, py, panel_w, panel_h, (0.78, 0.62, 0.32, 1.0))

        owner = getattr(chest, "owner_peer_id", "?")
        self.draw_text(f"Cofre de {owner}  [Click derecho para cerrar]", px + 14, py + 10, font, (240, 220, 150, 255))
        self.draw_text("Click en un item para mover 1 unidad", px + 14, py + 30, font, (200, 190, 170, 255))

        self.draw_text("Tu inventario", left_x, py + 52, font, (180, 240, 220, 255))
        self.draw_text("Contenido del cofre", right_x, py + 52, font, (240, 220, 150, 255))

        start_y = py + 74
        for i in range(layout["rows"]):
            y = start_y + i * row_h
            # fondos de slots
            self._draw_rect_px(left_x, y, col_w, 24, (0.10, 0.14, 0.10, 0.72))
            self._draw_rect_outline_px(left_x, y, col_w, 24, (0.30, 0.45, 0.30, 0.95))
            self._draw_rect_px(right_x, y, col_w, 24, (0.16, 0.12, 0.08, 0.72))
            self._draw_rect_outline_px(right_x, y, col_w, 24, (0.55, 0.42, 0.22, 0.95))

            if i < len(p_items):
                item_id, amount = p_items[i]
                name = ITEM_NAMES.get(item_id, f"#{item_id}")
                color = ITEM_COLORS.get(item_id, (0.6, 0.6, 0.6))
                self._draw_rect_px(left_x + 6, y + 5, 14, 14, (*color, 1.0))
                self.draw_text(f"{name}: x{amount}", left_x + 26, y + 4, font, (225, 230, 220, 255))

            if i < len(c_items):
                item_id, amount = c_items[i]
                name = ITEM_NAMES.get(item_id, f"#{item_id}")
                color = ITEM_COLORS.get(item_id, (0.6, 0.6, 0.6))
                self._draw_rect_px(right_x + 6, y + 5, 14, 14, (*color, 1.0))
                self.draw_text(f"{name}: x{amount}", right_x + 26, y + 4, font, (230, 225, 210, 255))

    def chest_ui_hit(self, mouse_x, mouse_y, player_inventory, chest_inventory):
        """Devuelve ('player'|'chest', item_id) si se clicó un slot del UI."""
        layout = self._chest_ui_layout(player_inventory, chest_inventory)
        left_x, right_x = layout["left_x"], layout["right_x"]
        col_w, row_h = layout["col_w"], layout["row_h"]
        start_y = layout["py"] + 74
        p_items, c_items = layout["p_items"], layout["c_items"]

        for i, (item_id, _amount) in enumerate(p_items):
            y = start_y + i * row_h
            if left_x <= mouse_x <= left_x + col_w and y <= mouse_y <= y + 24:
                return ("player", item_id)

        for i, (item_id, _amount) in enumerate(c_items):
            y = start_y + i * row_h
            if right_x <= mouse_x <= right_x + col_w and y <= mouse_y <= y + 24:
                return ("chest", item_id)

        return None

    # Low-level pixel helpers
    # ==================================================================
    def _set_pixel_projection(self):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        gluOrtho2D(0, self.width, 0, self.height)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

    def _restore_projection(self):
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def _draw_rect_px(self, x, y, w, h, color):
        self._set_pixel_projection()
        bx, by = x, self.height - y - h
        glColor4f(*color)
        glBegin(GL_QUADS)
        glVertex2f(bx, by); glVertex2f(bx + w, by)
        glVertex2f(bx + w, by + h); glVertex2f(bx, by + h)
        glEnd()
        self._restore_projection()

    def _draw_rect_outline_px(self, x, y, w, h, color):
        self._set_pixel_projection()
        bx, by = x, self.height - y - h
        glColor4f(*color)
        glLineWidth(2)
        glBegin(GL_LINE_LOOP)
        glVertex2f(bx, by); glVertex2f(bx + w, by)
        glVertex2f(bx + w, by + h); glVertex2f(bx, by + h)
        glEnd()
        glLineWidth(1)
        self._restore_projection()

    def draw_text(self, text, x, y, font, color=(255, 255, 255, 255)):
        if not text:
            return
        surf = font.render(text, True, color[:3])
        data = pygame.image.tostring(surf, "RGBA", True)
        tw, th = surf.get_size()
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        gluOrtho2D(0, self.width, 0, self.height)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        gy = self.height - y - th
        glRasterPos2i(int(x), int(gy))
        glDrawPixels(tw, th, GL_RGBA, GL_UNSIGNED_BYTE, data)
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def crafting_menu_hit(self, mouse_x, mouse_y, show_crafting):
        """Detecta si el usuario hizo click en algún item del menú de fabricación.
        Retorna el item_id si se hizo click, None si no."""
        if not show_crafting:
            return None
        
        panel_w = 400
        recipes_list = list(CRAFTING_RECIPES.items())
        rows = max(1, len(recipes_list))
        panel_h = 42 + rows * 28 + 14
        px = 24
        py = 24
        
        # Verificar si el click está dentro del panel
        if not (px <= mouse_x <= px + panel_w and py <= mouse_y <= py + panel_h):
            return None
        
        # Verificar en qué fila hizo click (cada fila tiene 28 pixels de alto)
        row_start = py + 40  # Inicio de los items
        relative_y = mouse_y - row_start
        
        if relative_y < 0:
            return None
        
        row = relative_y // 28
        
        if row < len(recipes_list):
            return recipes_list[row][0]
        
        return None
