#!/usr/bin/env python3
"""Simple Pygame demo: move the circle with arrow keys, Esc or window close to quit."""
import sys
import pygame
import math

WIDTH, HEIGHT = 800, 600
FPS = 60

ASSETS_DIR = "assets/Kart/"

# Game constants 
acceleration = 1.02
turning_deceleration = 0.99
no_gas_deceleration = 0.98
break_deceleration = 0.95
max_speed = 0.075
max_back_speed = -0.03
min_speed = 0.0001
min_start_speed = 0.01
    
# Tile map
tile_size = 32

track_1_tilemap = [
    [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2],
    [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
    [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
    [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,4,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,4,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,4,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,4,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,4,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,5,5,5,5,5,0,0,0,0,0,2,2,2,2,2,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,2,2,2,2,2,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,2,2,2,2,2,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,2,2,2,2,2,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,2,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,4,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,4,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,4,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,2],
    [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
    [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
    [2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2],
    [2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2]
]
track_1_offset = (5, -2)
track_1_start_direction = 270
track_1_checkpoints = 2




def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Pygame Demo")
    clock = pygame.time.Clock()


    # Variables del joc
    x, y = 0, 0
    direction = track_1_start_direction
    total_speed = 0.001
    checkpoint_counter = 0
    last_tile = 0
    
    # Carreguem les imatges
    tile_green = pygame.image.load(ASSETS_DIR + "imatges/tilemap1/green.png").convert()
    tile_gray = pygame.image.load(ASSETS_DIR + "imatges/tilemap1/gray.png").convert()
    tile_yellow = pygame.image.load(ASSETS_DIR + "imatges/tilemap1/yellow.png").convert()
    tile_blue = pygame.image.load(ASSETS_DIR + "imatges/tilemap1/blue.png").convert()
    tile_checkpoint = pygame.image.load(ASSETS_DIR + "imatges/tilemap1/gray.png").convert()
    tile_finish_line = pygame.image.load(ASSETS_DIR + "imatges/tilemap1/blue.png").convert()
    
    running = True
    while running:
        
        # Esborrar la pantalla
        screen.fill((0, 0, 0))
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        
        # Tilemap drawing
        for row in range(len(track_1_tilemap)):
            for col in range(len(track_1_tilemap[row])):
                tile_type = track_1_tilemap[row][col]
                if tile_type == 0:
                    screen.blit(tile_green, ((col + track_1_offset[0] + x) * tile_size, (row + track_1_offset[1] + y) * tile_size))
                elif tile_type == 1:
                    screen.blit(tile_gray, ((col + track_1_offset[0] + x) * tile_size, (row + track_1_offset[1] + y) * tile_size))
                elif tile_type == 2:
                    screen.blit(tile_yellow, ((col + track_1_offset[0] + x) * tile_size, (row + track_1_offset[1] + y) * tile_size))
                elif tile_type == 3:
                    screen.blit(tile_blue, ((col + track_1_offset[0] + x) * tile_size, (row + track_1_offset[1] + y) * tile_size))
                elif tile_type == 4:
                    screen.blit(tile_checkpoint, ((col + track_1_offset[0] + x) * tile_size, (row + track_1_offset[1] + y) * tile_size))
                elif tile_type == 5:
                    screen.blit(tile_finish_line, ((col + track_1_offset[0] + x) * tile_size, (row + track_1_offset[1] + y) * tile_size))
                      
        
        pygame.draw.rect(screen, (255, 0, 255), (col * tile_size, row * tile_size, tile_size, tile_size))   
        
        
        # Handle inputs
        
        keys = pygame.key.get_pressed()
        # remember previous position to resolve collisions
        prev_x, prev_y = x, y
        if keys[pygame.K_ESCAPE]:
            running = False
            
        # Turning logic
        if keys[pygame.K_LEFT]:
            direction += 1
            if direction >= 360:
                direction = 0
            total_speed = max(min_speed, total_speed * turning_deceleration)
        if keys[pygame.K_RIGHT]:
            direction -= 1
            if direction < 0:
                direction = 359
            total_speed = max(min_speed, total_speed * turning_deceleration)
            
        # Acceleration logic
        if keys[pygame.K_UP]:
            total_speed = min(max_speed, max(min_start_speed, total_speed * acceleration))
            y += total_speed * math.sin(math.radians(direction))
            x += total_speed * math.cos(math.radians(direction))
        if keys[pygame.K_DOWN]:
            total_speed = min(max_back_speed, total_speed * break_deceleration)
            x += total_speed * math.cos(math.radians(direction))
            y += total_speed * math.sin(math.radians(direction))
        if (not keys[pygame.K_UP] and not keys[pygame.K_DOWN]):
            total_speed = max(min_speed, total_speed * no_gas_deceleration)
            x += total_speed * math.cos(math.radians(direction))
            y += total_speed * math.sin(math.radians(direction))
        
        # After movement, check collision with wall tiles and resolve
        tile_under = get_tile_type(screen, x, y)
        if wall_collision(tile_under):
            # revert movement along dominant axis and stop the player
            dx = x - prev_x
            dy = y - prev_y
            if abs(dx) > abs(dy):
                x = prev_x
            else:
                y = prev_y
            total_speed = 0


        # Checkpoint logic
        if tile_under == 4 and last_tile != 4:
            checkpoint_counter += 1
            print(f"Checkpoint reached! Total checkpoints: {checkpoint_counter}")
        elif tile_under == 5 and last_tile != 5:
            if checkpoint_counter >= track_1_checkpoints:
                print("Finish line reached!")
                win_window(screen)
        last_tile = tile_under

        # Player drawing
        pygame.draw.circle(screen, (200, 30, 30), (WIDTH/2, HEIGHT/2), 30)
        draw_speedometer(screen, total_speed * 1000)
        draw_debug_info(screen, x, y, direction)
        pygame.display.flip()
        clock.tick(FPS)
        
        

    pygame.quit()
    sys.exit(0)




def get_tile_type(screen, x, y):
    tile_x = int((WIDTH/2/tile_size - track_1_offset[0] - x)) 
    tile_y = int((HEIGHT/2/tile_size - track_1_offset[1] - y))

    font = pygame.font.SysFont(None, 24)
    text = font.render(f"X: {tile_x} Y: {tile_y}", True, (255, 255, 255))
    screen.blit(text, (10, 70))
    
    if 0 <= tile_y < len(track_1_tilemap) and 0 <= tile_x < len(track_1_tilemap[tile_y]):
        return track_1_tilemap[tile_y][tile_x]
    return None


def wall_collision(tile_type):
    """Return True if the tile type represents a wall."""
    return tile_type == 2

# UI functions
def draw_speedometer(screen, speed):
    font = pygame.font.SysFont(None, 24)
    text = font.render(f"Speed: {speed:.0f}", True, (255, 255, 255))
    screen.blit(text, (10, 10))
    
def draw_debug_info(screen, x, y, direction):
    font = pygame.font.SysFont(None, 24)
    text = font.render(f"X: {x:.2f} Y: {y:.2f} Dir: {direction} TileOnTop: {get_tile_type(screen, x, y)}", True, (255, 255, 255))
    screen.blit(text, (10, 40))

def win_window(screen):
    font = pygame.font.SysFont(None, 48)
    text = font.render("You win!", True, (255, 255, 255))
    text_rect = text.get_rect(center=(WIDTH/2, HEIGHT/2))
    screen.blit(text, text_rect)
    
def lose_window(screen):
    font = pygame.font.SysFont(None, 48)
    text = font.render("You lose!", True, (255, 255, 255))
    text_rect = text.get_rect(center=(WIDTH/2, HEIGHT/2))
    screen.blit(text, text_rect)
    
if __name__ == "__main__":
    main()

