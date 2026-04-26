#!/usr/bin/env python3
"""Simple Pygame demo: move the circle with arrow keys, Esc or window close to quit."""
import sys
import pygame
import math
import json
import os
import time
from ui import EscapeMenu

WIDTH, HEIGHT = 800, 600
FPS = 60

ASSETS_DIR = "assets/Kart/"

# Game constants 
acceleration = 1.04
turning_deceleration = 0.99
no_gas_deceleration = 0.98
break_deceleration = 0.95
max_speed = 0.1
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
        # prefer the new filename `track2.json`, then common variants
        for name in ('track2.json', 'track_2.json', 'track.json', 'map.json'):
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
        self.font = pygame.font.SysFont(None, 24)

        # Load assets
        self.tile_dot1 = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/dot1.png").convert()
        self.tile_dot2 = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/dot2.png").convert()
        self.tile_dot3 = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/dot3.png").convert()
        self.tile_dot4 = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/dot4.png").convert()
        self.tile_grass = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/grass.png").convert()
        self.tile_interrogant23 = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/interrogant23.png").convert()
        self.tile_kerb1 = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/kerb1.png").convert()
        self.tile_kerb2 = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/kerb2.png").convert()
        self.tile_kerb3 = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/kerb3.png").convert()
        self.tile_kerb4 = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/kerb4.png").convert()
        self.tile_meta = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/meta.png").convert()
        self.tile_checkpoint = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/road_middle.png").convert()
        # Load player sprites with alpha so transparency is preserved
        self.tile_P1 = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/P1.png").convert_alpha()
        self.tile_P2 = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/P2.png").convert_alpha()
        self.tile_P3 = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/P3.png").convert_alpha()
        # Player sprite registry
        self.player_images = {
            'P1': self.tile_P1,
            'P2': self.tile_P2,
            'P3': self.tile_P3,
        }
        self.tile_road_down = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/road_down.png").convert()
        self.tile_road_left = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/road_left.png").convert()
        self.tile_road_right = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/road_right.png").convert()
        self.tile_road_top = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/road_top.png").convert()
        self.tile_road_bottom_right = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/road_bottom_tight.png").convert() # File is named "tight" but it's actually the inner corner tile
        self.tile_road_right_top = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/road_right_top.png").convert() 
        self.tile_road_top_left = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/road_top_left.png").convert() 
        self.tile_road_left_bottom = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/road_left_bottom.png").convert()  
        self.tile_wall = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/wall.png").convert()
        self.tile_road_middle = pygame.image.load(ASSETS_DIR + "imatges/tilemap2/road_middle.png").convert()
        
        
        # Player state
        self.player = Player(peer_id=(self.net.peer_id if self.net else 'local'))
        # Spawn at tile (8,8) in the tilemap. Convert tile indices to world coordinates by adding map offset.
        self.player.x = 8 + track_1_offset[0]
        self.player.y = 8 + track_1_offset[1]
        self.player.direction = track_1_start_direction
        self.player.speed = 0.001
        self.checkpoint_counter = 0
        self.last_tile = 0

        # Laps and race state
        self.lap_count = 0
        self.laps_total = 3
        self.race_over = False
        self.race_winner = None
        # finishing order list (peer ids in order of finish)
        self.finishing_order = []

        # Car assignment: local uses P1 by default; peers get unique cars from available pool
        self.local_car = 'P1'
        self.available_cars = ['P1', 'P2', 'P3']
        self.peer_car_map = {}
        self.used_cars = set([self.local_car])

        # Opponents state: peer_id -> dict with received target and rendered positions
        # Each entry will contain: x_target, y_target, direction_target, speed, render_x, render_y, last_seen, eliminated
        self.opponents = {}

        # Network callback
        if self.net:
            def _on_msg(msg):
                try:
                    action = msg.get('action')
                    peer = msg.get('peerId') or msg.get('peer_id')
                    # be tolerant: if no explicit peer in the payload, skip processing
                    if not peer or (self.net and peer == self.net.peer_id):
                        return
                    if action == 'STATE':
                        tx = float(msg.get('x', 0.0))
                        ty = float(msg.get('y', 0.0))
                        td = float(msg.get('direction', 0.0))
                        spd = float(msg.get('speed', 0.0))
                        lap = int(float(msg.get('lap', 0)))
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
                                # assign a car sprite for this peer
                                try:
                                    car = self._assign_car_to_peer(peer)
                                    self.opponents[peer]['car'] = car
                                except Exception:
                                    self.opponents[peer]['car'] = 'P2'
                                # record lap count
                                self.opponents[peer]['lap_count'] = lap
                        else:
                            p['x_target'] = tx
                            p['y_target'] = ty
                            p['direction_target'] = td
                            p['speed'] = spd
                            # update lap count if provided
                            try:
                                p['lap_count'] = int(float(msg.get('lap', p.get('lap_count', 0))))
                            except Exception:
                                pass
                            p['last_seen'] = now_t
                            # keep p['render_x']/render_y unchanged; smoothing will move them towards target
                    elif action == 'PLAYER_ELIMINATED':
                        if peer in self.opponents:
                            self.opponents[peer]['eliminated'] = True
                    elif action == 'PLAYER_FINISHED':
                        # remote peer declared finish; try to read explicit winner id
                        winner = msg.get('winner') or peer
                        if winner not in self.finishing_order:
                            self.finishing_order.append(winner)
                        # set race_over so overlay shows
                        self.race_over = True
                        # first finisher is winner if we don't already have one
                        if not self.race_winner and self.finishing_order:
                            self.race_winner = self.finishing_order[0]
                    else:
                        # unexpected/other actions: ignore but keep debug print for diagnostics
                        pass
                except Exception:
                    pass

            self.net.on_message_received = _on_msg

            # Pre-populate opponents from any peers NetworkManager already knows about
            try:
                for p in list(self.net.peers.keys()):
                    if p and p != getattr(self.net, 'peer_id', None) and p not in self.opponents:
                        self.opponents[p] = {
                            'x_target': self.player.x,
                            'y_target': self.player.y,
                            'render_x': self.player.x,
                            'render_y': self.player.y,
                            'render_direction': self.player.direction,
                            'last_seen': time.time(),
                            'eliminated': False,
                            'car': self._assign_car_to_peer(p),
                            'lap_count': 0,
                        }
            except Exception:
                pass

            # Hook into on_peer_connected to add opponents as soon as TCP handshake completes
            def _on_peer_connected_local(pid):
                try:
                    if pid and pid not in self.opponents:
                        self.opponents[pid] = {
                            'x_target': self.player.x,
                            'y_target': self.player.y,
                            'render_x': self.player.x,
                            'render_y': self.player.y,
                            'render_direction': self.player.direction,
                            'last_seen': time.time(),
                            'eliminated': False,
                            'car': self._assign_car_to_peer(pid),
                            'lap_count': 0,
                        }
                except Exception:
                    pass

            try:
                prev = getattr(self.net, 'on_peer_connected', None)
                def combined_peer_connected(pid):
                    try:
                        if prev:
                            try:
                                prev(pid)
                            except Exception:
                                pass
                        _on_peer_connected_local(pid)
                    except Exception:
                        pass
                self.net.on_peer_connected = combined_peer_connected
            except Exception:
                try:
                    self.net.on_peer_connected = _on_peer_connected_local
                except Exception:
                    pass

        self.running = False

    def send_state(self):
        if not self.net:
            return
        try:
            # include lap count so peers can know progress
            self.net.send_event('STATE', x=self.player.x, y=self.player.y, direction=self.player.direction, speed=self.player.speed, lap=self.lap_count)
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
            # finish line: count lap if all checkpoints passed
            if self.checkpoint_counter >= track_1_checkpoints:
                self.lap_count += 1
                print(f"Lap {self.lap_count}/{self.laps_total} completed!")
                # reset checkpoint counter for next lap
                self.checkpoint_counter = 0
                # notify peers that we've finished if race complete
                if self.lap_count >= self.laps_total:
                    # local finished
                    if self.player.peer_id not in self.finishing_order:
                        self.finishing_order.append(self.player.peer_id)
                    self.race_over = True
                    self.race_winner = self.finishing_order[0]
                    try:
                        if self.net:
                            self.net.send_event('PLAYER_FINISHED', winner=self.player.peer_id)
                    except Exception:
                        pass
        self.last_tile = tile_under

        # purge stale opponents
        now = time.time()
        for p in list(self.opponents.keys()):
            if now - self.opponents[p].get('last_seen', 0) > 10:
                # free up car assignment if present
                car = self.opponents[p].get('car')
                if car and car in self.used_cars:
                    self.used_cars.discard(car)
                if p in self.peer_car_map:
                    del self.peer_car_map[p]
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
                    self.screen.blit(self.tile_grass, pos)
                elif tile_type == 1:
                    self.screen.blit(self.tile_road_middle, pos)
                elif tile_type == 2:
                    self.screen.blit(self.tile_wall, pos)
                elif tile_type == 3:
                    self.screen.blit(self.tile_interrogant, pos)
                elif tile_type == 4:
                    self.screen.blit(self.tile_checkpoint, pos)
                elif tile_type == 5:
                    self.screen.blit(self.tile_meta, pos)
                elif tile_type == 6:
                    self.screen.blit(self.tile_P1, pos)
                elif tile_type == 7:
                    self.screen.blit(self.tile_P2, pos)
                elif tile_type == 8:
                    self.screen.blit(self.tile_road_down, pos)
                elif tile_type == 9:
                    self.screen.blit(self.tile_road_left, pos)
                elif tile_type == 10:
                    self.screen.blit(self.tile_road_right, pos)
                elif tile_type == 11:
                    self.screen.blit(self.tile_road_top, pos)
                elif tile_type == 12:
                    self.screen.blit(self.tile_road_bottom_right, pos)
                elif tile_type == 13:
                    self.screen.blit(self.tile_road_right_top, pos)
                elif tile_type == 14:                    
                    self.screen.blit(self.tile_road_top_left, pos)
                elif tile_type == 15:
                    self.screen.blit(self.tile_road_left_bottom, pos)
                elif tile_type == 16:
                    self.screen.blit(self.tile_road_middle, pos)
                elif tile_type == 17:
                    self.screen.blit(self.tile_dot1, pos)
                elif tile_type == 18:
                    self.screen.blit(self.tile_dot2, pos)
                elif tile_type == 19:
                    self.screen.blit(self.tile_dot3, pos)
                elif tile_type == 20:
                    self.screen.blit(self.tile_dot4, pos)
                elif tile_type == 21:
                    self.screen.blit(self.tile_kerb1, pos)
                elif tile_type == 22:
                    self.screen.blit(self.tile_kerb2, pos)
                elif tile_type == 23:
                    self.screen.blit(self.tile_kerb3, pos)
                elif tile_type == 24:
                    self.screen.blit(self.tile_kerb4, pos)
                
                
                # unknown tile type; draw a placeholder
        # Debug rectangle last drawn tile (keep behavior similar)
        pygame.draw.rect(self.screen, (255, 0, 255), (col * tile_size, row * tile_size, tile_size, tile_size))

        # Draw local player sprite (centered)
        try:
            img = pygame.transform.rotate(self.tile_P1, -self.player.direction)
            rect = img.get_rect(center=(self.width//2, self.height//2))
            self.screen.blit(img, rect)
        except Exception:
            # fallback to simple circle if image missing
            pygame.draw.circle(self.screen, (200, 30, 30), (self.width//2, self.height//2), 30)

        # Draw opponents
        for peer_id, st in self.opponents.items():
            rx = st.get('render_x', st.get('x_target', 0.0))
            ry = st.get('render_y', st.get('y_target', 0.0))
            screen_x = self.width//2 + int((rx - self.player.x) * tile_size)
            screen_y = self.height//2 + int((ry - self.player.y) * tile_size)
            # choose car sprite for this peer
            car = st.get('car') or self.peer_car_map.get(peer_id) or 'P2'
            img = self.player_images.get(car)
            if img:
                try:
                    rim = pygame.transform.rotate(img, -st.get('render_direction', 0.0))
                    rrect = rim.get_rect(center=(screen_x, screen_y))
                    self.screen.blit(rim, rrect)
                except Exception:
                    pygame.draw.circle(self.screen, self._color_for_peer(peer_id), (screen_x, screen_y), 24)
            else:
                pygame.draw.circle(self.screen, self._color_for_peer(peer_id), (screen_x, screen_y), 24)
            font = pygame.font.SysFont(None, 20)
            text = font.render(peer_id, True, (255, 255, 255))
            self.screen.blit(text, (screen_x + 26, screen_y - 10))
            # show lap count under the name
            lap_text = font.render(f"Lap: {st.get('lap_count', 0)}/{self.laps_total}", True, (255, 255, 255))
            self.screen.blit(lap_text, (screen_x + 26, screen_y + 6))

        draw_speedometer(self.screen, self.player.speed * 1000)
        draw_debug_info(self.screen, self.player.x, self.player.y, self.player.direction)

        # If race over, draw podium overlay
        if self.race_over:
            overlay = pygame.Surface((self.width, self.height), flags=pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 200))
            self.screen.blit(overlay, (0, 0))
            title_font = pygame.font.SysFont(None, 64)
            pod_font = pygame.font.SysFont(None, 36)
            title = title_font.render("Race Results", True, (255, 215, 0))
            self.screen.blit(title, title.get_rect(center=(self.width//2, 80)))

            # draw top-3 podium columns (2 left, 1 center, 3 right)
            center_x = self.width // 2
            base_y = 220
            col_w = 180
            # positions: 2nd, 1st, 3rd
            positions = [1, 0, 2]
            offsets = [-col_w, 0, col_w]
            for i, pos in enumerate(positions):
                idx = pos
                x = center_x + offsets[i]
                # height: first is taller
                height = 220 if pos == 0 else 160
                rect = pygame.Rect(x - 70, base_y + (220 - height), 140, height)
                pygame.draw.rect(self.screen, (200, 200, 200), rect)
                # get finisher id if present
                fin_id = self.finishing_order[idx] if idx < len(self.finishing_order) else None
                if fin_id:
                    # draw car sprite if available
                    car_key = self.peer_car_map.get(fin_id) if fin_id in self.peer_car_map else ( 'P1' if fin_id == self.player.peer_id else None )
                    img = self.player_images.get(car_key) if car_key else None
                    if img:
                        simg = pygame.transform.scale(img, (64, 64))
                        self.screen.blit(simg, simg.get_rect(center=(x, rect.top + 40)))
                    # name
                    name_text = pod_font.render(fin_id, True, (0, 0, 0))
                    self.screen.blit(name_text, name_text.get_rect(center=(x, rect.top + 110)))
                    # place number
                    place = pod_font.render(f"#{idx+1}", True, (0, 0, 0))
                    self.screen.blit(place, place.get_rect(center=(x, rect.bottom - 20)))
                else:
                    none_text = pod_font.render("---", True, (0,0,0))
                    self.screen.blit(none_text, none_text.get_rect(center=(x, rect.top + 80)))

        pygame.display.flip()

    def _color_for_peer(self, peer_id):
        # Lightweight deterministic color from peer id
        s = sum(ord(c) for c in str(peer_id))
        r = 80 + (s * 97) % 160
        g = 60 + (s * 193) % 160
        b = 80 + (s * 71) % 160
        return (r, g, b)

    def _assign_car_to_peer(self, peer_id):
        """Assign a car id ('P1','P2','P3') to a peer, trying to keep them unique.
        Returns the assigned car key.
        """
        # first try available cars not used yet
        for c in self.available_cars:
            if c not in self.used_cars:
                self.peer_car_map[peer_id] = c
                self.used_cars.add(c)
                return c
        # if all used, pick deterministically by hash (cycle)
        idx = abs(hash(peer_id)) % len(self.available_cars)
        c = self.available_cars[idx]
        self.peer_car_map[peer_id] = c
        return c

    def run(self):
        self.running = True
        while self.running:
            # frame delta in seconds
            dt = self.clock.tick(FPS) / 1000.0
            self._frame_dt = dt

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        menu = EscapeMenu(self.screen, self.clock, self.font)
                        res = menu.show()
                        if res == "LOBBY":
                            self.running = False
                            continue
                        elif res == "EXIT":
                            pygame.quit()
                            sys.exit()

            # If race over, stop updating gameplay but keep drawing and handling quit
            if not self.race_over:
                self.handle_input()
                self.update()
                # send state update
                self.send_state()
            else:
                # still allow input events (handled above) but skip game updates
                pass
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

