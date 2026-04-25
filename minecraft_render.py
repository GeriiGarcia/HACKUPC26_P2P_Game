import pygame
from OpenGL.GL import *
from OpenGL.GLU import *
from minecraft_core import B_DIRT, B_STONE, B_WOOD, B_WHEAT, WORLD_WIDTH, WORLD_HEIGHT

# Colores (R, G, B)
COLOR_SKY = (0.5, 0.7, 1.0)
COLOR_DIRT = (0.54, 0.27, 0.07)
COLOR_STONE = (0.5, 0.5, 0.5)
COLOR_WOOD = (0.35, 0.16, 0.04)
COLOR_WHEAT = (0.9, 0.8, 0.2)
COLOR_PLAYER = (0.8, 0.2, 0.2)
COLOR_OTHER_PLAYER = (0.2, 0.8, 0.2)

BLOCK_SIZE_PX = 32

class Renderer:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.setup_opengl(width, height)
        
    def setup_opengl(self, width, height):
        self.width = width
        self.height = height
        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        # Ortho projection: left, right, bottom, top
        # We want coordinates to be in "blocks"
        blocks_x = width / BLOCK_SIZE_PX
        blocks_y = height / BLOCK_SIZE_PX
        gluOrtho2D(0, blocks_x, blocks_y, 0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glClearColor(*COLOR_SKY, 1.0)
        
        # Activar blending para transparencia si hiciera falta
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def render(self, world, players, my_peer_id):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        my_player = players.get(my_peer_id)
        if not my_player:
            return
            
        # Camera translation (center player on screen)
        blocks_x = self.width / BLOCK_SIZE_PX
        blocks_y = self.height / BLOCK_SIZE_PX
        
        cam_x = my_player.x - blocks_x / 2.0
        cam_y = my_player.y - blocks_y / 2.0
        
        # Clamp camera to world bounds
        cam_x = max(0, min(cam_x, WORLD_WIDTH - blocks_x))
        cam_y = max(0, min(cam_y, WORLD_HEIGHT - blocks_y))
        
        glTranslatef(-cam_x, -cam_y, 0)
        
        # Determine visible area to cull rendering
        start_x = int(cam_x)
        end_x = int(cam_x + blocks_x) + 1
        start_y = int(cam_y)
        end_y = int(cam_y + blocks_y) + 1
        
        # --- Draw Blocks ---
        glBegin(GL_QUADS)
        for y in range(max(0, start_y), min(WORLD_HEIGHT, end_y)):
            for x in range(max(0, start_x), min(WORLD_WIDTH, end_x)):
                b = world.get_block(x, y)
                if b == B_DIRT:
                    glColor3f(*COLOR_DIRT)
                elif b == B_STONE:
                    glColor3f(*COLOR_STONE)
                elif b == B_WOOD:
                    glColor3f(*COLOR_WOOD)
                elif b == B_WHEAT:
                    glColor3f(*COLOR_WHEAT)
                else:
                    continue # Aire
                    
                glVertex2f(x, y)
                glVertex2f(x + 1, y)
                glVertex2f(x + 1, y + 1)
                glVertex2f(x, y + 1)
        glEnd()
        
        # --- Draw Block Outlines (Grid) ---
        glColor4f(0, 0, 0, 0.2)
        glBegin(GL_LINES)
        for y in range(max(0, start_y), min(WORLD_HEIGHT, end_y)):
            for x in range(max(0, start_x), min(WORLD_WIDTH, end_x)):
                if world.get_block(x, y) != 0:
                    glVertex2f(x, y)
                    glVertex2f(x + 1, y)
                    
                    glVertex2f(x + 1, y)
                    glVertex2f(x + 1, y + 1)
                    
                    glVertex2f(x + 1, y + 1)
                    glVertex2f(x, y + 1)
                    
                    glVertex2f(x, y + 1)
                    glVertex2f(x, y)
        glEnd()

        # --- Draw Players ---
        for p_id, p in players.items():
            if p_id == my_peer_id:
                glColor3f(*COLOR_PLAYER)
            else:
                glColor3f(*COLOR_OTHER_PLAYER)
                
            glBegin(GL_QUADS)
            glVertex2f(p.x, p.y)
            glVertex2f(p.x + p.width, p.y)
            glVertex2f(p.x + p.width, p.y + p.height)
            glVertex2f(p.x, p.y + p.height)
            glEnd()
            
            # Player Outline
            glColor3f(0, 0, 0)
            glBegin(GL_LINE_LOOP)
            glVertex2f(p.x, p.y)
            glVertex2f(p.x + p.width, p.y)
            glVertex2f(p.x + p.width, p.y + p.height)
            glVertex2f(p.x, p.y + p.height)
            glEnd()
            
    def render_hud(self, surface, player):
        """Renderizamos el HUD usando la surface de pygame por encima del contexto GL.
        Nota: Pygame con OpenGL double buffer no soporta facilmente blit encima.
        Por lo que lo dibujaremos usando texto de Pygame renderizado como textura o simplemente no lo mezclaremos,
        sino que usaremos Pygame para renderizar texto y luego lo convertimos a textura GL."""
        # Para simplificar en esta iteración sin texturas GL complejas, 
        # confiaremos en que el usuario vea su inventario en terminal, o implementaremos 
        # text blitting básico.
        pass

    def draw_text(self, text, x, y, font, color=(255, 255, 255, 255)):
        """Dibuja texto sobre OpenGL usando PyGame."""
        textSurface = font.render(text, True, color)
        textData = pygame.image.tostring(textSurface, "RGBA", True)
        width, height = textSurface.get_size()
        
        # Configurar proyeccion ortogonal 1:1 pixel
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        gluOrtho2D(0, self.width, 0, self.height)
        
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        
        glRasterPos2i(int(x), int(self.height - y - height))
        glDrawPixels(width, height, GL_RGBA, GL_UNSIGNED_BYTE, textData)
        
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
