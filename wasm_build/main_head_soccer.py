import pygame
import sys
import math
import uuid
from network import NetworkManager

# --- Constants ---
WIDTH, HEIGHT = 800, 600
FPS = 60
GRAVITY = 0.6
FRICTION = 0.98

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREEN = (50, 200, 50)
RED = (200, 50, 50)
BLUE = (50, 50, 200)
YELLOW = (200, 200, 50)
GRAY = (150, 150, 150)

# --- Entities ---
class Player:
    def __init__(self, x, y, is_left, peer_id):
        self.peer_id = peer_id
        self.x = x
        self.y = y
        self.vx = 0
        self.vy = 0
        self.is_left = is_left
        
        # Dimensions
        self.head_radius = 35
        self.body_w = 40
        self.body_h = 25
        
        self.speed = 5
        self.jump_force = 13
        
        self.inputs = {"left": False, "right": False, "jump": False, "kick": False, "head": False}
        self.score = 0
        
        # Cooldowns
        self.kick_timer = 0
        self.head_timer = 0
        
    def update(self):
        # Timers
        if self.kick_timer > 0: self.kick_timer -= 1
        if self.head_timer > 0: self.head_timer -= 1
        
        # Horizontal movement
        if self.inputs["left"]:
            self.vx = -self.speed
        elif self.inputs["right"]:
            self.vx = self.speed
        else:
            self.vx *= 0.8 # Friction on ground
            
        # Jump
        if self.inputs["jump"] and self.y >= HEIGHT - 100 - self.body_h:
            self.vy = -self.jump_force
            
        # Kick / Head animation triggers
        if self.inputs["kick"] and self.kick_timer == 0:
            self.kick_timer = 15
        if self.inputs["head"] and self.head_timer == 0:
            self.head_timer = 15
            
        # Apply gravity
        self.vy += GRAVITY
        
        # Apply velocity
        self.x += self.vx
        self.y += self.vy
        
        # Constraints (Ground)
        ground_y = HEIGHT - 100
        if self.y + self.body_h >= ground_y:
            self.y = ground_y - self.body_h
            self.vy = 0
            
        # Screen constraints (don't go into goals completely or off screen)
        # Left goal is x: 0 to 80. Right goal is x: 720 to 800.
        # But players shouldn't enter the goal easily.
        if self.x < 80: self.x = 80
        if self.x + self.body_w > WIDTH - 80: self.x = WIDTH - 80 - self.body_w
            
    def get_head_center(self):
        head_offset_x = self.body_w / 2
        # If heading, move head forward
        if self.head_timer > 0:
            head_offset_x += 20 if self.is_left else -20
        return (self.x + head_offset_x, self.y - self.head_radius + 10)
        
    def get_foot_rect(self):
        # If kicking, extend foot
        foot_w = 20
        if self.kick_timer > 0:
            foot_w = 40
            
        if self.is_left:
            return pygame.Rect(self.x + self.body_w / 2, self.y + self.body_h - 15, foot_w, 15)
        else:
            return pygame.Rect(self.x + self.body_w / 2 - foot_w, self.y + self.body_h - 15, foot_w, 15)

    def draw(self, screen):
        color = BLUE if self.is_left else RED
        # Body
        pygame.draw.rect(screen, color, (self.x, self.y, self.body_w, self.body_h))
        
        # Head
        hx, hy = self.get_head_center()
        pygame.draw.circle(screen, color, (int(hx), int(hy)), self.head_radius)
        
        # Foot
        foot_rect = self.get_foot_rect()
        pygame.draw.rect(screen, YELLOW, foot_rect)
        
        # Eye (just for fun)
        eye_x = hx + (15 if self.is_left else -15)
        pygame.draw.circle(screen, WHITE, (int(eye_x), int(hy - 5)), 8)
        pygame.draw.circle(screen, BLACK, (int(eye_x + (3 if self.is_left else -3)), int(hy - 5)), 3)

class Ball:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vx = 0
        self.vy = 0
        self.radius = 15
        
    def update(self):
        self.vy += GRAVITY
        
        self.vx *= FRICTION
        self.vy *= FRICTION
        
        self.x += self.vx
        self.y += self.vy
        
        # Ground bounce
        ground_y = HEIGHT - 100
        if self.y + self.radius >= ground_y:
            self.y = ground_y - self.radius
            self.vy = -self.vy * 0.7
            
        # Ceiling bounce
        if self.y - self.radius <= 0:
            self.y = self.radius
            self.vy = -self.vy * 0.7
            
        # Walls (Goals are open, but above goals is wall)
        goal_height = 200
        if self.x - self.radius <= 80 and self.y < HEIGHT - 100 - goal_height:
            self.x = 80 + self.radius
            self.vx = -self.vx * 0.7
            
        if self.x + self.radius >= WIDTH - 80 and self.y < HEIGHT - 100 - goal_height:
            self.x = WIDTH - 80 - self.radius
            self.vx = -self.vx * 0.7
            
        # Back of the goal bounce
        if self.x - self.radius <= 0:
            self.x = self.radius
            self.vx = -self.vx * 0.7
        if self.x + self.radius >= WIDTH:
            self.x = WIDTH - self.radius
            self.vx = -self.vx * 0.7

    def draw(self, screen):
        pygame.draw.circle(screen, WHITE, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(screen, BLACK, (int(self.x), int(self.y)), self.radius, 2)


# --- Game State ---
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("P2P Head Soccer")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 36, bold=True)
        self.big_font = pygame.font.SysFont("Arial", 72, bold=True)
        
        self.state = "WAITING" # WAITING, PLAYING, GAME_OVER
        self.winner = None
        
        # P2P Network
        self.peer_id = f"HS_{str(uuid.uuid4())[:6]}"
        self.net = NetworkManager("HeadSoccerRoom", self.peer_id)
        self.net.on_peer_connected = self.on_peer_connected
        self.net.on_peer_disconnected = self.on_peer_disconnected
        self.net.on_message_received = self.on_message_received
        
        self.other_peer_id = None
        self.is_host = False
        
        # Entities
        self.players = {}
        self.ball = Ball(WIDTH // 2, HEIGHT // 2)
        

        self.goal_timer = 0
        self.countdown_timer = 0
        
        self.net.start()
        
    def reset_positions(self):
        # Host is always left
        if self.is_host:
            my_x, other_x = 200, WIDTH - 200 - 40
            my_is_left, other_is_left = True, False
        else:
            my_x, other_x = WIDTH - 200 - 40, 200
            my_is_left, other_is_left = False, True
            
        self.players[self.peer_id].x = my_x
        self.players[self.peer_id].y = HEIGHT - 150
        self.players[self.peer_id].vx = 0
        self.players[self.peer_id].vy = 0
        self.players[self.peer_id].is_left = my_is_left
        
        self.players[self.other_peer_id].x = other_x
        self.players[self.other_peer_id].y = HEIGHT - 150
        self.players[self.other_peer_id].vx = 0
        self.players[self.other_peer_id].vy = 0
        self.players[self.other_peer_id].is_left = other_is_left
        
        self.ball.x = WIDTH // 2
        self.ball.y = HEIGHT // 2 - 100
        self.ball.vx = 0
        self.ball.vy = 0
        
        self.goal_timer = 0

    def on_peer_connected(self, peer_id):
        if self.state == "WAITING" and not self.other_peer_id:
            self.other_peer_id = peer_id
            self.is_host = self.peer_id < self.other_peer_id
            
            # Create players
            self.players[self.peer_id] = Player(0, 0, True, self.peer_id)
            self.players[self.other_peer_id] = Player(0, 0, False, self.other_peer_id)
            
            self.reset_positions()
            self.state = "PLAYING"
            self.countdown_timer = 90 # 1.5s countdown
            print(f"Game started with {peer_id}. Host: {self.is_host}")
            
    def on_peer_disconnected(self, peer_id):
        if peer_id == self.other_peer_id:
            print("Opponent disconnected.")
            self.state = "WAITING"
            self.other_peer_id = None
            self.players = {}

    def on_message_received(self, msg):
        action = msg.get("action")
        if action == "INPUT" and self.other_peer_id in self.players:
            self.players[self.other_peer_id].inputs = msg.get("inputs")
        elif action == "SYNC" and not self.is_host:
            # Client receives sync from host
            if "ball" in msg:
                self.ball.x = msg["ball"]["x"]
                self.ball.y = msg["ball"]["y"]
                self.ball.vx = msg["ball"]["vx"]
                self.ball.vy = msg["ball"]["vy"]
            if "players" in msg and self.other_peer_id in self.players and self.peer_id in self.players:
                # the msg["players"] dict keys are the peer_ids
                for pid, pdata in msg["players"].items():
                    if pid in self.players:
                        # Soft sync to avoid jitter, but we'll do hard sync for simplicity
                        self.players[pid].x = pdata["x"]
                        self.players[pid].y = pdata["y"]
                        self.players[pid].vx = pdata["vx"]
                        self.players[pid].vy = pdata["vy"]
                        self.players[pid].score = pdata["score"]
        elif action == "GOAL":
            # Just to trigger animations or sounds, but positions are synced by host anyway
            scorer = msg.get("scorer")
            if scorer in self.players:
                self.players[scorer].score = msg.get("score")
            self.goal_timer = 60 # 1 second pause
        elif action == "REMATCH":
            if self.state == "GAME_OVER":
                self.reset_positions()
                for p in self.players.values():
                    p.score = 0
                self.state = "PLAYING"
                self.countdown_timer = 90
        elif action == "GAME_OVER":
            self.state = "GAME_OVER"
            self.winner = msg.get("winner")
        elif action == "GOAL":
            # Sync score and trigger goal delay
            scorer = msg.get("scorer")
            if scorer in self.players:
                self.players[scorer].score = msg.get("score")
            self.goal_timer = 60 # 1 second post-goal physics
            self.countdown_timer = 0 # Ensure no countdown during ball flight.

    def handle_inputs(self):
        keys = pygame.key.get_pressed()
        new_inputs = {
            "left": keys[pygame.K_a],
            "right": keys[pygame.K_d],
            "jump": keys[pygame.K_w],
            "kick": keys[pygame.K_SPACE],
            "head": keys[pygame.K_w]
        }
        
        # Send only if changed or periodically
        if self.state == "PLAYING" and self.peer_id in self.players:
            p = self.players[self.peer_id]
            if new_inputs != p.inputs:
                p.inputs = new_inputs
                self.net.send_event("INPUT", inputs=new_inputs)
                
    def resolve_collisions(self):
        if len(self.players) < 2: return
        
        p1 = self.players[self.peer_id]
        p2 = self.players[self.other_peer_id]
        
        # Player vs Player (simple bounding box overlap push)
        r1 = pygame.Rect(p1.x, p1.y, p1.body_w, p1.body_h)
        r2 = pygame.Rect(p2.x, p2.y, p2.body_w, p2.body_h)
        if r1.colliderect(r2):
            # Push apart horizontally
            if p1.x < p2.x:
                p1.x -= 2
                p2.x += 2
                p1.vx = min(p1.vx, 0)
                p2.vx = max(p2.vx, 0)
            else:
                p1.x += 2
                p2.x -= 2
                p1.vx = max(p1.vx, 0)
                p2.vx = min(p2.vx, 0)
                
        # Players vs Ball
        for p in self.players.values():
            # Head collision (Circle vs Circle)
            hx, hy = p.get_head_center()
            dist = math.hypot(self.ball.x - hx, self.ball.y - hy)
            if dist < self.ball.radius + p.head_radius:
                # Overlap resolution
                overlap = (self.ball.radius + p.head_radius) - dist
                nx = (self.ball.x - hx) / dist
                ny = (self.ball.y - hy) / dist
                self.ball.x += nx * overlap
                self.ball.y += ny * overlap
                
                # Header physics
                if p.head_timer > 0:
                    force = 15
                    self.ball.vx = nx * force
                    self.ball.vy = ny * force - 5 # extra upward
                else:
                    # Normal bounce
                    self.ball.vx += nx * 2
                    self.ball.vy += ny * 2
                    
            # Body collision (Rect vs Circle)
            body_rect = pygame.Rect(p.x, p.y, p.body_w, p.body_h)
            # Find closest point on rect to circle center
            cx = max(body_rect.left, min(self.ball.x, body_rect.right))
            cy = max(body_rect.top, min(self.ball.y, body_rect.bottom))
            dist_body = math.hypot(self.ball.x - cx, self.ball.y - cy)
            
            if dist_body < self.ball.radius:
                # Push ball out
                if self.ball.y < body_rect.top:
                    self.ball.y = body_rect.top - self.ball.radius
                    self.ball.vy *= -0.5
                elif self.ball.x < body_rect.left:
                    self.ball.x = body_rect.left - self.ball.radius
                    self.ball.vx *= -0.5
                elif self.ball.x > body_rect.right:
                    self.ball.x = body_rect.right + self.ball.radius
                    self.ball.vx *= -0.5
                    
            # Kick collision
            foot_rect = p.get_foot_rect()
            cx_f = max(foot_rect.left, min(self.ball.x, foot_rect.right))
            cy_f = max(foot_rect.top, min(self.ball.y, foot_rect.bottom))
            dist_foot = math.hypot(self.ball.x - cx_f, self.ball.y - cy_f)
            
            if dist_foot < self.ball.radius and p.kick_timer > 0:
                # Powerful kick, height depends on distance
                direction = 1 if p.is_left else -1
                dist_ratio = max(0.0, min(1.0, dist_foot / self.ball.radius))
                vertical_kick = -16 * (1 - dist_ratio) - 4 * dist_ratio
                self.ball.vx = direction * 18
                self.ball.vy = vertical_kick
                p.kick_timer = 0 # consume kick

    def check_goals(self):
        # A goal is when ball is completely inside goal bounds
        # Left goal: x < 80, Right goal: x > WIDTH - 80
        # Height: y > HEIGHT - 100 - 200
        if self.goal_timer > 0:
            self.goal_timer -= 1
            if self.goal_timer == 0:
                self.reset_positions()
                self.countdown_timer = 90
            return

        ground_y = HEIGHT - 100
        goal_height = 200
        
        # Determine who is who
        host_p = self.players[self.peer_id] if self.is_host else self.players[self.other_peer_id]
        client_p = self.players[self.other_peer_id] if self.is_host else self.players[self.peer_id]
        
        if self.ball.y > ground_y - goal_height and self.ball.y < ground_y:
            scorer = None
            if self.ball.x + self.ball.radius < 80:
                # Scored in left goal (Host's goal -> Client scores)
                scorer = client_p
            elif self.ball.x - self.ball.radius > WIDTH - 80:
                # Scored in right goal (Client's goal -> Host scores)
                scorer = host_p
                
            if scorer:
                if self.is_host:
                    scorer.score += 1
                    self.net.send_event("GOAL", scorer=scorer.peer_id, score=scorer.score)
                    self.goal_timer = 60
                    
                    if scorer.score >= 5:
                        self.state = "GAME_OVER"
                        self.winner = scorer.peer_id
                        self.net.send_event("GAME_OVER", winner=self.winner)

    def draw_goals(self):
        ground_y = HEIGHT - 100
        goal_w = 80
        goal_h = 200
        
        # Left Goal
        pygame.draw.rect(self.screen, GRAY, (0, ground_y - goal_h, goal_w, goal_h), 3)
        # Net pattern
        for i in range(0, goal_h, 20):
            pygame.draw.line(self.screen, GRAY, (0, ground_y - goal_h + i), (goal_w, ground_y - goal_h + i), 1)
        for i in range(0, goal_w, 20):
            pygame.draw.line(self.screen, GRAY, (i, ground_y - goal_h), (i, ground_y), 1)
            
        # Right Goal
        pygame.draw.rect(self.screen, GRAY, (WIDTH - goal_w, ground_y - goal_h, goal_w, goal_h), 3)
        for i in range(0, goal_h, 20):
            pygame.draw.line(self.screen, GRAY, (WIDTH - goal_w, ground_y - goal_h + i), (WIDTH, ground_y - goal_h + i), 1)
        for i in range(0, goal_w, 20):
            pygame.draw.line(self.screen, GRAY, (WIDTH - goal_w + i, ground_y - goal_h), (WIDTH - goal_w + i, ground_y), 1)

    def draw_score(self):
        if len(self.players) < 2: return
        p1 = self.players[self.peer_id] if self.is_host else self.players[self.other_peer_id]
        p2 = self.players[self.other_peer_id] if self.is_host else self.players[self.peer_id]
        
        txt = self.font.render(f"{p1.score} - {p2.score}", True, BLACK)
        self.screen.blit(txt, (WIDTH//2 - txt.get_width()//2, 30))

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if self.state == "GAME_OVER" and event.key == pygame.K_RETURN:
                        self.net.send_event("REMATCH")
                        self.reset_positions()
                        for p in self.players.values():
                            p.score = 0
                        self.state = "PLAYING"
            
            self.handle_inputs()
            
            if self.state == "PLAYING":
                # Physics and Logic
                # Physics runs during normal gameplay or during the 1s post-goal flight
                if self.countdown_timer == 0:
                    for p in self.players.values():
                        p.update()
                    self.ball.update()
                    self.resolve_collisions()
                else:
                    # During countdown, players are frozen
                    self.countdown_timer -= 1
                    
                self.check_goals()
                
                # Host sync
                if self.is_host:
                    sync_data = {
                        "ball": {"x": self.ball.x, "y": self.ball.y, "vx": self.ball.vx, "vy": self.ball.vy},
                        "players": {
                            pid: {"x": p.x, "y": p.y, "vx": p.vx, "vy": p.vy, "score": p.score}
                            for pid, p in self.players.items()
                        }
                    }
                    self.net.send_event("SYNC", **sync_data)
                        
            # Drawing
            self.screen.fill((135, 206, 235)) # Sky blue
            
            # Ground
            pygame.draw.rect(self.screen, GREEN, (0, HEIGHT - 100, WIDTH, 100))
            
            if self.state == "WAITING":
                txt = self.font.render("Waiting for opponent...", True, BLACK)
                self.screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2))
            else:
                self.draw_goals()
                self.draw_score()
                
                for p in self.players.values():
                    p.draw(self.screen)
                self.ball.draw(self.screen)
                
                if self.countdown_timer > 0:
                    val = math.ceil(self.countdown_timer / 30)
                    txt = self.big_font.render(str(val), True, YELLOW)
                    self.screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2 - 50))
                
                if self.state == "GAME_OVER":
                    # Overlay
                    s = pygame.Surface((WIDTH, HEIGHT))
                    s.set_alpha(128)
                    s.fill(BLACK)
                    self.screen.blit(s, (0,0))
                    
                    msg = "YOU WIN!" if self.winner == self.peer_id else "YOU LOSE!"
                    txt = self.big_font.render(msg, True, YELLOW)
                    self.screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2 - 100))
                    
                    txt2 = self.font.render("Press ENTER to play again", True, WHITE)
                    self.screen.blit(txt2, (WIDTH//2 - txt2.get_width()//2, HEIGHT//2 + 50))
            
            pygame.display.flip()
            self.clock.tick(FPS)
            
        self.net.stop()
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    game = Game()
    game.run()
