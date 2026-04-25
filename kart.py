#!/usr/bin/env python3
"""Simple Pygame demo: move the circle with arrow keys, Esc or window close to quit."""
import sys
import pygame
import math
import json
import os
import time

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



def _load_track_from_json():
    """Load track configuration from a JSON file located in ASSETS_DIR/mapes.
    Expected JSON keys:
      - tilemap: 2D list of integers
      - offset: [x, y]
      - start_direction: int
      - checkpoints: int
    If no JSON is found or loading fails, this function leaves the defaults intact.
    """
    global track_1_tilemap, track_1_offset, track_1_start_direction, track_1_checkpoints
    candidates = []
    mapes_dir = os.path.join(ASSETS_DIR, 'mapes')
    if os.path.isdir(mapes_dir):
        # prefer common filenames
        for name in ('track.json', 'track_1.json', 'track1.json', 'map.json'):
            candidates.append(os.path.join(mapes_dir, name))
        # also include any other .json in the folder
        for fname in os.listdir(mapes_dir):
            if fname.lower().endswith('.json'):
                candidates.append(os.path.join(mapes_dir, fname))
    else:
        return

    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            # Validate and apply
            tm = data.get('tilemap') or data.get('track_1_tilemap')
            off = data.get('offset') or data.get('track_1_offset')
            sd = data.get('start_direction') or data.get('track_1_start_direction')
            cp = data.get('checkpoints') or data.get('track_1_checkpoints')
            if tm and isinstance(tm, list):
                track_1_tilemap = tm
            if off and (isinstance(off, list) or isinstance(off, tuple)) and len(off) >= 2:
                track_1_offset = (int(off[0]), int(off[1]))
            if sd is not None:
                track_1_start_direction = int(sd)
            if cp is not None:
                track_1_checkpoints = int(cp)
            print(f"Loaded track config from {path}")
            return
        except Exception as e:
            # try next
            print(f"Failed to load track config from {path}: {e}")


# Attempt to load track config from JSON next to the images
_load_track_from_json()


class Player:
    def __init__(self, peer_id='local', x=0.0, y=0.0, direction=0.0, speed=0.0):
        self.peer_id = peer_id
        self.x = float(x)
        self.y = float(y)
        self.direction = float(direction)
        self.speed = float(speed)
        self.prev_x = float(x)
        self.prev_y = float(y)
        self.last_seen = time.time()
        self.eliminated = False


class KartGame:
    def __init__(self, net_manager=None, screen_size=(WIDTH, HEIGHT)):
        self.net = net_manager
        self.width, self.height = screen_size

        # Pygame setup (only initialize display here; caller may have initialized pygame)
        if not pygame.get_init():
            pygame.init()
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Pygame Kart - P2P")
        self.clock = pygame.time.Clock()

        # Load assets
        self.tile_green = pygame.image.load(ASSETS_DIR + "imatges/tilemap1/green.png").convert()
        self.tile_gray = pygame.image.load(ASSETS_DIR + "imatges/tilemap1/gray.png").convert()
        self.tile_yellow = pygame.image.load(ASSETS_DIR + "imatges/tilemap1/yellow.png").convert()
        self.tile_blue = pygame.image.load(ASSETS_DIR + "imatges/tilemap1/blue.png").convert()
        self.tile_checkpoint = pygame.image.load(ASSETS_DIR + "imatges/tilemap1/gray.png").convert()
        self.tile_finish_line = pygame.image.load(ASSETS_DIR + "imatges/tilemap1/blue.png").convert()

        # Player state
        self.player = Player(peer_id=(self.net.peer_id if self.net else 'local'))
        # Spawn at tile (8,8) in the tilemap. Convert tile indices to world coordinates by adding map offset.
        self.player.x = 8 + track_1_offset[0]
        self.player.y = 8 + track_1_offset[1]
        self.player.direction = track_1_start_direction
        self.player.speed = 0.001
        self.checkpoint_counter = 0
        self.last_tile = 0

        # Opponents state: peer_id -> dict with received target and rendered positions
        # Each entry will contain: x_target, y_target, direction_target, speed, render_x, render_y, last_seen, eliminated
        self.opponents = {}

        # Network callback
        if self.net:
            def _on_msg(msg):
                try:
                    action = msg.get('action')
                    peer = msg.get('peerId')
                    if not peer or peer == self.net.peer_id:
                        return
                    if action == 'STATE':
                        tx = float(msg.get('x', 0.0))
                        ty = float(msg.get('y', 0.0))
                        td = float(msg.get('direction', 0.0))
                        spd = float(msg.get('speed', 0.0))
                        now_t = time.time()
                        p = self.opponents.get(peer)
                        if p is None:
                            # first time, set rendered positions to target immediately
                            self.opponents[peer] = {
                                'x_target': tx,
                                'y_target': ty,
                                'direction_target': td,
                                'speed': spd,
                                'render_x': tx,
                                'render_y': ty,
                                'render_direction': td,
                                'last_seen': now_t,
                                'eliminated': False
                            }
                        else:
                            p['x_target'] = tx
                            p['y_target'] = ty
                            p['direction_target'] = td
                            p['speed'] = spd
                            p['last_seen'] = now_t
                            # keep p['render_x']/render_y unchanged; smoothing will move them towards target
                    elif action == 'PLAYER_ELIMINATED':
                        if peer in self.opponents:
                            self.opponents[peer]['eliminated'] = True
                except Exception:
                    pass

            self.net.on_message_received = _on_msg

        self.running = False

    def send_state(self):
        if not self.net:
            return
        try:
            self.net.send_event('STATE', x=self.player.x, y=self.player.y, direction=self.player.direction, speed=self.player.speed)
        except Exception:
            pass

    def handle_input(self):
        keys = pygame.key.get_pressed()
        # store previous position to allow robust collision rollback
        self.player.prev_x = self.player.x
        self.player.prev_y = self.player.y
        if keys[pygame.K_ESCAPE]:
            self.running = False

        # Turning
        if keys[pygame.K_LEFT]:
            self.player.direction = (self.player.direction - 1) % 360
            self.player.speed = max(min_speed, self.player.speed * turning_deceleration)
        if keys[pygame.K_RIGHT]:
            self.player.direction = (self.player.direction + 1) % 360
            self.player.speed = max(min_speed, self.player.speed * turning_deceleration)

        # Acceleration / braking
        if keys[pygame.K_UP]:
            self.player.speed = min(max_speed, max(min_start_speed, self.player.speed * acceleration))
            self.player.y += self.player.speed * math.sin(math.radians(self.player.direction))
            self.player.x += self.player.speed * math.cos(math.radians(self.player.direction))
        elif keys[pygame.K_DOWN]:
            self.player.speed = max(max_back_speed, self.player.speed * break_deceleration)
            self.player.x += self.player.speed * math.cos(math.radians(self.player.direction))
            self.player.y += self.player.speed * math.sin(math.radians(self.player.direction))
        else:
            self.player.speed = max(min_speed, self.player.speed * no_gas_deceleration)
            self.player.x += self.player.speed * math.cos(math.radians(self.player.direction))
            self.player.y += self.player.speed * math.sin(math.radians(self.player.direction))

    def update(self):
        # Collision resolution
        tile_under = get_tile_type(self.screen, self.player.x, self.player.y)
        if wall_collision(tile_under):
            # Collision: restore previous position recorded before movement and stop
            self.player.x = getattr(self.player, 'prev_x', self.player.x)
            self.player.y = getattr(self.player, 'prev_y', self.player.y)
            self.player.speed = 0

        # Checkpoints
        if tile_under == 4 and self.last_tile != 4:
            self.checkpoint_counter += 1
            print(f"Checkpoint reached! Total checkpoints: {self.checkpoint_counter}")
        elif tile_under == 5 and self.last_tile != 5:
            if self.checkpoint_counter >= track_1_checkpoints:
                print("Finish line reached!")
                win_window(self.screen)
        self.last_tile = tile_under

        # purge stale opponents
        now = time.time()
        for p in list(self.opponents.keys()):
            if now - self.opponents[p].get('last_seen', 0) > 10:
                del self.opponents[p]

        # Smooth remote players toward their last received target (no extrapolation)
        # Use exponential smoothing based on frame dt set by run()
        dt = getattr(self, '_frame_dt', 1.0 / FPS)
        # smoothing rate: larger -> faster converge
        rate = 8.0
        alpha = 1.0 - math.exp(-rate * dt)
        for peer_id, p in self.opponents.items():
            # Only update render positions if targets exist
            if 'x_target' in p and 'render_x' in p:
                p['render_x'] += (p['x_target'] - p['render_x']) * alpha
                p['render_y'] += (p['y_target'] - p['render_y']) * alpha
                # smooth direction (wrap-aware)
                rd = p.get('render_direction', p.get('direction_target', 0.0))
                td = p.get('direction_target', rd)
                diff = (td - rd + 180) % 360 - 180
                rd += diff * alpha
                p['render_direction'] = rd % 360

    def draw(self):
        # Clear
        self.screen.fill((0, 0, 0))

        # Tilemap drawing
        for row in range(len(track_1_tilemap)):
            for col in range(len(track_1_tilemap[row])):
                tile_type = track_1_tilemap[row][col]
                # Convert tile (col,row) into screen coordinates centered on the local player
                pos = (
                    self.width//2 + int((col + track_1_offset[0] - self.player.x) * tile_size),
                    self.height//2 + int((row + track_1_offset[1] - self.player.y) * tile_size)
                )
                if tile_type == 0:
                    self.screen.blit(self.tile_green, pos)
                elif tile_type == 1:
                    self.screen.blit(self.tile_gray, pos)
                elif tile_type == 2:
                    self.screen.blit(self.tile_yellow, pos)
                elif tile_type == 3:
                    self.screen.blit(self.tile_blue, pos)
                elif tile_type == 4:
                    self.screen.blit(self.tile_checkpoint, pos)
                elif tile_type == 5:
                    self.screen.blit(self.tile_finish_line, pos)

        # Debug rectangle last drawn tile (keep behavior similar)
        pygame.draw.rect(self.screen, (255, 0, 255), (col * tile_size, row * tile_size, tile_size, tile_size))

        # Draw local player at center
        pygame.draw.circle(self.screen, (200, 30, 30), (self.width//2, self.height//2), 30)

        # Draw opponents
        for peer_id, st in self.opponents.items():
            # deterministic color per peer
            color = (100, 100, 100) if st.get('eliminated') else self._color_for_peer(peer_id)
            rx = st.get('render_x', st.get('x_target', 0.0))
            ry = st.get('render_y', st.get('y_target', 0.0))
            screen_x = self.width//2 + int((rx - self.player.x) * tile_size)
            screen_y = self.height//2 + int((ry - self.player.y) * tile_size)
            pygame.draw.circle(self.screen, color, (screen_x, screen_y), 24)
            font = pygame.font.SysFont(None, 20)
            text = font.render(peer_id, True, (255, 255, 255))
            self.screen.blit(text, (screen_x + 26, screen_y - 10))

        draw_speedometer(self.screen, self.player.speed * 1000)
        draw_debug_info(self.screen, self.player.x, self.player.y, self.player.direction)

        pygame.display.flip()

    def _color_for_peer(self, peer_id):
        # Lightweight deterministic color from peer id
        s = sum(ord(c) for c in str(peer_id))
        r = 80 + (s * 97) % 160
        g = 60 + (s * 193) % 160
        b = 80 + (s * 71) % 160
        return (r, g, b)

    def run(self):
        self.running = True
        while self.running:
            # frame delta in seconds
            dt = self.clock.tick(FPS) / 1000.0
            self._frame_dt = dt

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

            self.handle_input()
            self.update()
            # send state update
            self.send_state()
            self.draw()


def main():
    # Run the Kart game using the refactored KartGame class
    game = KartGame()
    try:
        game.run()
    finally:
        pygame.quit()
        sys.exit(0)




def get_tile_type(screen, x, y):
    # Map world coordinates (x,y) in tile units to tilemap indices.
    # World -> tile index: tile_index = int(world_coord - map_offset)
    tile_x = int(x-track_1_offset[0]-0.5) #int((WIDTH/2/tile_size + track_1_offset[0] + x))
    tile_y = int(y-track_1_offset[1]-0.5) #int((HEIGHT/2/tile_size + track_1_offset[1] + y))

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

