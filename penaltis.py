import pygame
import time

class PenaltiesGame:
    def __init__(self, net_manager, is_host=False, players=None):
        # net_manager may be None for local testing
        self.net = net_manager
        self.is_host = bool(is_host)
        self.role = 'shooter' if self.is_host else 'keeper'
        self.peer_ids = []
        # initialize scores and peer list; allow caller to provide canonical players order
        self.scores = {}
        if players and isinstance(players, (list, tuple)):
            # players is expected to be an ordered list including host
            self.all_players_sorted = list(players)
            for p in self.all_players_sorted:
                self.scores[p] = 0
        elif self.net:
            # fallback: use net peer list + our id
            self.peer_ids = list(self.net.peers.keys())
            self.all_players_sorted = [self.net.peer_id] + [p for p in self.peer_ids if p != self.net.peer_id]
            self.scores[self.net.peer_id] = 0
            for p in self.net.peers.keys():
                self.scores[p] = 0
        else:
            # local play placeholders
            self.scores['You'] = 0
            self.scores['Opponent'] = 0
            if not hasattr(self, 'all_players_sorted'):
                self.all_players_sorted = ['You', 'Opponent']
        self.shots = []  # list of dicts: {x,y,timestamp,from}
        self.anim_ttl = 1.2
        self.game_over = False
        self.winner = None
        self.last_result_text = ""
        self.result_text_time = 0
        # compatibility flags expected by main.py
        self.battle_phase = False
        self.current_turn_index = 0
        # keep any all_players_sorted set earlier (don't overwrite)
        self.eliminated_players = set()
        self.player_commits = {}
        self.my_board = None
        # shooter input state: pending shot (pointing) before kick
        self.pending_shot = None
        # kicker index defaults to 0
        self.current_kicker_index = 0
        self.my_board = None

    def start(self, width, height):
        self.WIDTH = width
        self.HEIGHT = height
        # define goal rectangle
        gw = int(self.WIDTH * 0.6)
        gh = int(self.HEIGHT * 0.35)
        self.goal_rect = pygame.Rect((self.WIDTH - gw)//2, 40, gw, gh)
        # initialize kicker/keeper roles; if all_players_sorted already set (from constructor or START_GAME), keep it
        if not self.all_players_sorted:
            if self.net:
                peers = list(self.net.peers.keys())
                self.all_players_sorted = [self.net.peer_id] + [p for p in peers if p != self.net.peer_id]
            else:
                self.all_players_sorted = list(self.scores.keys())
        # start with first player as kicker
        self.current_kicker_index = 0
        self._assign_roles()
        # resting ball position below goal
        rx = self.WIDTH//2
        ry = self.goal_rect.y + self.goal_rect.height + 40
        self.ball_rest_pos = (rx, ry)

    # Compatibility methods used by main.py for different games
    def start_placement(self, width, height, cell_size=30):
        # for penalties, placement phase is trivial; prepare and mark battle ready
        self.start(width, height)
        self.battle_phase = True


    def start_battle_if_ready(self):
        # always ready once started for penalties
        return self.battle_phase

    def _assign_roles(self):
        # Set role for this client based on current_kicker_index
        if not self.all_players_sorted:
            self.role = 'keeper'
            return
        kicker = self.all_players_sorted[self.current_kicker_index % len(self.all_players_sorted)]
        my_id = (self.net.peer_id if self.net else 'You')
        self.role = 'shooter' if my_id == kicker else 'keeper'

    def _advance_kicker(self):
        if not self.all_players_sorted:
            return
        self.current_kicker_index = (self.current_kicker_index + 1) % len(self.all_players_sorted)
        self._assign_roles()

    def handle_event(self, event):
        # shooter uses SPACE to shoot; we capture current mouse pos
        if self.game_over:
            return False
        # New input flow: shooter first points (left click) then clicks again to kick.
        if self.role == 'shooter':
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                # if no pending shot, set the aim point
                if not self.pending_shot:
                    # only allow pointing toward goal area
                    if my < self.goal_rect.y + self.goal_rect.height + 40:
                        self.pending_shot = (mx, my)
                        return True
                else:
                    # second click: commit shot at pending_shot
                    sx, sy = self.pending_shot
                    # send shot to peers
                    if self.net:
                        try:
                            shot_id = f"{self.net.peer_id}:{time.time()}"
                            # include kicker index so everyone can compute authoritative next index
                            self.net.send_event('PENALTY_SHOT', x=sx, y=sy, shooter=self.net.peer_id, shot_id=shot_id, start_time=time.time(), duration=0.5, kicker_index=self.current_kicker_index)
                            local_shot_id = shot_id
                        except Exception:
                            pass
                    # locally add a shot entry (works for both net and local)
                    shot_entry = {'x': sx, 'y': sy, 'shooter': (self.net.peer_id if self.net else 'You'), 'start_time': time.time(), 'duration': 0.5, 'shot_id': (locals().get('local_shot_id') if 'local_shot_id' in locals() else f"{(self.net.peer_id if self.net else 'You')}:{time.time()}"), 'kicker_index': self.current_kicker_index, 'results': {'saves': set()}, 'finalized': False, 'checked': False}
                    self.shots.append(shot_entry)
                    self.pending_shot = None
                    return True
        else:
            # keepers don't handle clicks specially here
            pass
        return False

    def on_network_message(self, msg):
        a = msg.get('action')
        if a == 'PENALTY_SHOT':
            x = msg.get('x')
            y = msg.get('y')
            shooter = msg.get('shooter') or msg.get('peerId')
            shot_id = msg.get('shot_id') or f"{shooter}:{msg.get('start_time', time.time())}"
            start_time = msg.get('start_time') or time.time()
            duration = msg.get('duration') or 0.5
            kicker_idx = msg.get('kicker_index')
            # add shot animation
            shot_entry = {'x': x, 'y': y, 'shooter': shooter, 'start_time': start_time, 'duration': duration, 'shot_id': shot_id, 'kicker_index': kicker_idx, 'results': {'saves': set()}, 'finalized': False, 'checked': False}
            self.shots.append(shot_entry)
        elif a == 'PENALTY_RESULT':
            result = msg.get('result')
            shooter = msg.get('shooter')
            keeper = msg.get('keeper')
            shot_id = msg.get('shot_id')
            # find matching shot
            matched = None
            for s in self.shots:
                if s.get('shot_id') == shot_id:
                    matched = s
                    break
            # apply result: saves increment keeper and are recorded; goal increments shooter and finalizes
            # if sender provided authoritative next_kicker_index, apply it instead of local advance
            next_kicker = msg.get('next_kicker_index')
            if next_kicker is not None and isinstance(next_kicker, int):
                self.current_kicker_index = next_kicker
                self._assign_roles()

            if result == 'save':
                if keeper not in self.scores:
                    self.scores[keeper] = 0
                # avoid double counting
                if matched and keeper not in matched['results']['saves']:
                    self.scores[keeper] += 1
                    matched['results']['saves'].add(keeper)
                # record authoritative next_kicker if provided
                if matched and next_kicker is not None:
                    matched['next_kicker_index'] = next_kicker
                # if authoritative scores snapshot provided, adopt it
                final_scores = msg.get('scores')
                if isinstance(final_scores, dict):
                    self.scores = {k: int(v) for k, v in final_scores.items()}
                self.last_result_text = f"Saved by {keeper}!"
                self.result_text_time = time.time()
                self._check_game_over()
            else:
                # goal
                if shooter not in self.scores:
                    self.scores[shooter] = 0
                # avoid double counting goals
                # if authoritative scores snapshot provided, adopt it
                final_scores = msg.get('scores')
                if isinstance(final_scores, dict):
                    self.scores = {k: int(v) for k, v in final_scores.items()}
                else:
                    if matched and not matched.get('finalized'):
                        self.scores[shooter] += 1
                self.last_result_text = f"Goal by {shooter}!"
                self.result_text_time = time.time()
                # finalize and advance
                if matched:
                    matched['finalized'] = True
                    # record authoritative next_kicker if provided
                    if next_kicker is not None:
                        matched['next_kicker_index'] = next_kicker
                self._check_game_over()
                # if no authoritative next_kicker was provided, advance locally
                if next_kicker is None:
                    self._advance_kicker()
        elif a == 'PENALTY_GAME_OVER':
            # authoritative final scores and winner announced
            final_scores = msg.get('scores') or {}
            winner = msg.get('winner')
            # merge/update local scores with authoritative ones
            for k, v in final_scores.items():
                self.scores[k] = v
            self.winner = winner
            self.game_over = True

    def _check_game_over(self):
        for p, s in self.scores.items():
            if s >= 3:
                self.game_over = True
                self.winner = p
                # Broadcast authoritative game-over with final scores so all peers show the podium
                if self.net:
                    try:
                        self.net.send_event('PENALTY_GAME_OVER', winner=self.winner, scores=self.scores)
                    except Exception:
                        pass

    def draw(self, screen, font_small, font_normal, font_title, WIDTH, HEIGHT):
        # If start not called via main, ensure layout
        if not hasattr(self, 'WIDTH'):
            self.start(WIDTH, HEIGHT)
        # background: sky above bottom of goal, grass below
        sky_color = (135, 206, 235)
        grass_color = (60, 160, 60)
        sky_h = self.goal_rect.y + self.goal_rect.height
        screen.fill(sky_color)
        pygame.draw.rect(screen, grass_color, (0, sky_h, WIDTH, HEIGHT - sky_h))
        # draw goal (white rectangle) on top of sky
        pygame.draw.rect(screen, (250, 250, 250), self.goal_rect)
        pygame.draw.rect(screen, (120, 120, 120), self.goal_rect, 4)

        # role specific UI
        mx, my = pygame.mouse.get_pos()
        if self.role == 'shooter':
            # draw aim circle
            # draw live cursor and pending aim marker
            pygame.draw.circle(screen, (255, 80, 80), (mx, my), 12, 3)
            instr = font_normal.render('Apunta amb el ratolí. Clica per marcar, clica de nou per xutar.', True, (220,220,220))
            screen.blit(instr, (20, HEIGHT - 40))
            if self.pending_shot:
                px, py = self.pending_shot
                pygame.draw.circle(screen, (255, 220, 80), (int(px), int(py)), 10, 2)
                pending_lbl = font_small.render('Click again to kick', True, (255,220,80))
                screen.blit(pending_lbl, (int(px) + 12, int(py) - 6))
        else:
            # draw keeper hands (square following mouse)
            hand_rect = pygame.Rect(mx - 30, my - 30, 60, 60)
            pygame.draw.rect(screen, (200,200,255), hand_rect)
            pygame.draw.rect(screen, (80,80,140), hand_rect, 3)
            instr = font_normal.render('Mou el ratolí per parar.', True, (220,220,220))
            screen.blit(instr, (20, HEIGHT - 40))

        # draw shots (animate fade)
        now = time.time()
        # animate and resolve shots
        for s in list(self.shots):
            elapsed = now - s['start_time']
            duration = s.get('duration', 1.0)
            t = min(1.0, max(0.0, elapsed / duration))
            # interpolate from rest to target
            rx, ry = self.ball_rest_pos
            tx, ty = s['x'], s['y']
            px = int(rx + (tx - rx) * t)
            py = int(ry + (ty - ry) * t)
            # draw larger black ball
            ball_r = 14
            alpha = max(0, 255 - int((elapsed / (duration + 0.001)) * 255))
            surf = pygame.Surface((ball_r*2, ball_r*2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (0, 0, 0, alpha), (ball_r, ball_r), ball_r)
            screen.blit(surf, (px-ball_r, py-ball_r))

            # when travel finished, allow keepers to check for save once
            if elapsed >= duration and not s.get('checked'):
                s['checked'] = True
                # keepers check and broadcast saves
                if self.role == 'keeper':
                    mx, my = pygame.mouse.get_pos()
                    hand_rect = pygame.Rect(mx - 30, my - 30, 60, 60)
                    ball_rect = pygame.Rect(px-ball_r, py-ball_r, ball_r*2, ball_r*2)
                    saved = hand_rect.colliderect(ball_rect)
                    if saved:
                        # broadcast save
                        if self.net:
                            try:
                                # compute authoritative next kicker index from the original kicker_index
                                next_idx = None
                                if self.all_players_sorted:
                                    kidx = s.get('kicker_index')
                                    if isinstance(kidx, int):
                                        next_idx = (kidx + 1) % len(self.all_players_sorted)
                                    else:
                                        next_idx = (self.current_kicker_index + 1) % len(self.all_players_sorted)
                                self.net.send_event('PENALTY_RESULT', result='save', shooter=s['shooter'], keeper=(self.net.peer_id if self.net else 'You'), shot_id=s['shot_id'], next_kicker_index=next_idx)
                                # update our local score immediately so sender sees instant feedback
                                k = (self.net.peer_id if self.net else 'You')
                                if k not in self.scores:
                                    self.scores[k] = 0
                                if k not in s['results']['saves']:
                                    self.scores[k] += 1
                                    s['results']['saves'].add(k)
                                self._check_game_over()
                                # apply authoritative next kicker locally and mark it on the shot to avoid double-advance
                                if next_idx is not None:
                                    s['next_kicker_index'] = next_idx
                                    self.current_kicker_index = next_idx
                                    self._assign_roles()
                            except Exception:
                                pass
                            # include authoritative scores snapshot in the broadcast
                            try:
                                self.net.send_event('PENALTY_RESULT', result='save', shooter=s['shooter'], keeper=(self.net.peer_id if self.net else 'You'), shot_id=s['shot_id'], next_kicker_index=next_idx, scores=self.scores)
                            except Exception:
                                pass
                        else:
                            # local fallback: update scores
                            if (self.net is None) and ('Opponent' in self.scores):
                                self.scores['Opponent'] += 1
                # schedule finalization after short delay for all clients
            # finalize after small buffer
            if elapsed >= duration + 0.12 and not s.get('finalized'):
                # if there were any saves recorded, finalize and advance
                if s['results']['saves']:
                    s['finalized'] = True
                    # compose result text
                    savers = ', '.join(list(s['results']['saves']))
                    self.last_result_text = f"Saved by {savers}!"
                    self.result_text_time = time.time()
                    self._check_game_over()
                    # only advance locally if no authoritative next_kicker was recorded
                    if s.get('next_kicker_index') is None:
                        self._advance_kicker()
                else:
                    # no saves: shooter is responsible to broadcast goal (if networked)
                    if self.net and (self.net.peer_id == s['shooter']):
                        try:
                            # send authoritative next kicker index along with goal (based on original kicker)
                            next_idx = None
                            if self.all_players_sorted:
                                kidx = s.get('kicker_index')
                                if isinstance(kidx, int):
                                    next_idx = (kidx + 1) % len(self.all_players_sorted)
                                else:
                                    next_idx = (self.current_kicker_index + 1) % len(self.all_players_sorted)
                                # increment local shooter score and include authoritative scores snapshot
                                sc = s['shooter']
                                if sc not in self.scores:
                                    self.scores[sc] = 0
                                # only increment once
                                if not s.get('finalized'):
                                    self.scores[sc] += 1
                                self.last_result_text = f"Goal by {sc}!"
                                self.result_text_time = time.time()
                                try:
                                    self.net.send_event('PENALTY_RESULT', result='goal', shooter=s['shooter'], keeper=None, shot_id=s['shot_id'], next_kicker_index=next_idx, scores=self.scores)
                                except Exception:
                                    pass
                            # mark shot to avoid double advance locally
                            s['next_kicker_index'] = next_idx
                            s['finalized'] = True
                            if next_idx is not None:
                                self.current_kicker_index = next_idx
                                self._assign_roles()
                        except Exception:
                            pass
                    elif not self.net:
                        # local game: award shooter
                        if s['shooter'] not in self.scores:
                            self.scores[s['shooter']] = 0
                        self.scores[s['shooter']] += 1
                        self.last_result_text = f"Goal by {s['shooter']}!"
                        self.result_text_time = time.time()
                        s['finalized'] = True
                        self._check_game_over()
                        self._advance_kicker()

            # remove old animations (keep record for finalized state briefly)
            if elapsed > duration + 3.0:
                try:
                    self.shots.remove(s)
                except Exception:
                    pass

        # scores
        y = HEIGHT - 120
        x = 24
        score_text = 'Scores: '
        if self.net:
            entries = list(self.scores.items())
        else:
            entries = list(self.scores.items())
        for i, (p, sc) in enumerate(entries):
            lbl = font_small.render(f"{p}: {sc}", True, (240,240,240))
            screen.blit(lbl, (x, y + i*22))

        # last result text
        if self.last_result_text and time.time() - self.result_text_time < 2.5:
            lbl = font_title.render(self.last_result_text, True, (255, 220, 80))
            screen.blit(lbl, (WIDTH//2 - lbl.get_width()//2, self.goal_rect.y + self.goal_rect.height + 12))

        # if game over overlay
        if self.game_over:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0,0,0,180))
            screen.blit(overlay, (0,0))
            panel_w, panel_h = 480, 220
            px = (WIDTH - panel_w)//2
            py = (HEIGHT - panel_h)//2
            pygame.draw.rect(screen, (30,30,40), (px,py,panel_w,panel_h))
            pygame.draw.rect(screen, (200,200,200), (px,py,panel_w,panel_h), 2)
            title = font_title.render('Fi de la partida', True, (255,255,255))
            screen.blit(title, (px + panel_w//2 - title.get_width()//2, py + 12))
            win_lbl = font_normal.render(f'Guanyador: {self.winner}', True, (200,255,200))
            screen.blit(win_lbl, (px + panel_w//2 - win_lbl.get_width()//2, py + 72))
            # Draw podium: sort players by score descending
            sorted_players = sorted(self.scores.items(), key=lambda kv: kv[1], reverse=True)
            # show top 3 (or fewer if less players)
            start_y = py + 110
            for idx, (pname, pscore) in enumerate(sorted_players[:3]):
                pos_lbl = font_normal.render(f"{idx+1}. {pname} — {pscore} pts", True, (240,240,240))
                screen.blit(pos_lbl, (px + 28, start_y + idx*28))
            # if more players, list them below
            if len(sorted_players) > 3:
                more_y = start_y + 3*28 + 8
                for jdx, (pname, pscore) in enumerate(sorted_players[3:8]):
                    pos_lbl = font_small.render(f"{4+jdx}. {pname} — {pscore}", True, (200,200,200))
                    screen.blit(pos_lbl, (px + 28, more_y + jdx*20))