#!/usr/bin/env python3
"""Pygame UI launcher for the Kart P2P game.
Allows creating/joining a room, shows a lobby with peers, and starts `KartGame`.
Uses `ui.Button` and `ui.TextInput` for controls.
"""
import sys
import hashlib
import pygame
import time
import queue
import subprocess

from ui import Button, TextInput
from network import NetworkManager
from kart import KartGame


WIDTH, HEIGHT = 800, 600
FPS = 60

STATE_MENU = 0
STATE_CREATE = 1
STATE_JOIN = 2
STATE_LOBBY = 3


def generate_room_hash(room_name: str) -> str:
    return hashlib.sha256(room_name.encode('utf-8')).hexdigest()


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption('Kart P2P - Lobby')
    clock = pygame.time.Clock()

    font_title = pygame.font.SysFont(None, 56)
    font_normal = pygame.font.SysFont(None, 32)

    current_state = STATE_MENU

    net = None
    is_host = False
    room_hash_display = ''
    msg_q = queue.Queue()

    # UI elements
    btn_create = Button(WIDTH//2 - 160, HEIGHT//2 - 50, 320, 48, 'Create Room', font_normal)
    btn_join = Button(WIDTH//2 - 160, HEIGHT//2 + 10, 320, 48, 'Join Room', font_normal)
    btn_back = Button(20, HEIGHT - 60, 140, 44, 'Back', font_normal)
    btn_start = Button(WIDTH//2 - 90, HEIGHT - 80, 180, 56, 'Start Game', font_normal, bg_color=(50,200,50))
    btn_copy = Button(WIDTH//2 + 120, 88, 160, 40, 'Copy Room Hash', font_normal)

    input_name = TextInput(WIDTH//2 - 200, HEIGHT//2 - 120, 400, 40, font_normal)
    input_room = TextInput(WIDTH//2 - 200, HEIGHT//2 - 60, 400, 40, font_normal)

    peers = []
    copy_msg = None  # (text, ts)

    def on_peer_connected(pid):
        # update peers list asynchronously
        msg_q.put(('peer_connected', pid))

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if current_state == STATE_MENU:
                if btn_create.handle_event(event):
                    input_name.text = ''
                    input_room.text = ''
                    current_state = STATE_CREATE
                if btn_join.handle_event(event):
                    input_name.text = ''
                    input_room.text = ''
                    current_state = STATE_JOIN

            elif current_state in (STATE_CREATE, STATE_JOIN):
                input_name.handle_event(event)
                input_room.handle_event(event)
                if btn_back.handle_event(event):
                    current_state = STATE_MENU
                # enter key to confirm
                if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                    # act like confirm
                    if current_state == STATE_CREATE:
                        room = input_room.text.strip() or 'default_room'
                        room_hash = generate_room_hash(room)
                        is_host = True
                    else:
                        room_hash = input_room.text.strip() or input_room.text.strip()
                        # if user provided a short name, hash it
                        if len(room_hash) != 64:
                            room_hash = generate_room_hash(room_hash or 'default_room')
                        is_host = False

                    # start network
                    try:
                        net = NetworkManager(room_hash)
                        net.on_peer_connected = on_peer_connected
                        # route incoming network messages into our queue
                        net.on_message_received = lambda m: msg_q.put(('net_msg', m))
                        net.start()
                        room_hash_display = room_hash
                        peers = list(net.peers.keys())
                        current_state = STATE_LOBBY
                    except Exception as e:
                        print('Network start error:', e)

            elif current_state == STATE_LOBBY:
                if btn_back.handle_event(event):
                    # stop network and return
                    try:
                        if net:
                            net.stop()
                    except Exception:
                        pass
                    net = None
                    peers = []
                    current_state = STATE_MENU
                if is_host and btn_start.handle_event(event) and net:
                    # broadcast start event, then run locally
                    try:
                        net.send_event('START_GAME')
                    except Exception:
                        pass
                    # instantiate the game and run it (blocking)
                    game = KartGame(net_manager=net)
                    try:
                        game.run()
                    finally:
                        # when game exits, stop networking and return to menu
                        try:
                            net.stop()
                        except Exception:
                            pass
                        net = None
                        peers = []
                        current_state = STATE_MENU
                # Copy hash button
                if btn_copy.handle_event(event) and room_hash_display:
                    ok = copy_to_clipboard(room_hash_display)
                    copy_msg = ('Copied!' if ok else 'Copy failed', time.time())

        # process async peer messages
        try:
            while True:
                typ, val = msg_q.get_nowait()
                if typ == 'peer_connected':
                    if val not in peers:
                        peers.append(val)
                elif typ == 'net_msg':
                    msg = val
                    action = msg.get('action')
                    if action == 'START_GAME':
                        # start local game when host signals
                        if net:
                            game = KartGame(net_manager=net)
                            try:
                                game.run()
                            finally:
                                try:
                                    net.stop()
                                except Exception:
                                    pass
                                net = None
                                peers = []
                                current_state = STATE_MENU
        except Exception:
            pass

        # draw
        screen.fill((30,30,40))
        if current_state == STATE_MENU:
            title = font_title.render('Kart P2P', True, (240,240,240))
            screen.blit(title, (WIDTH//2 - title.get_width()//2, 80))
            btn_create.draw(screen)
            btn_join.draw(screen)

        elif current_state == STATE_CREATE:
            title = font_title.render('Create Room', True, (240,240,240))
            screen.blit(title, (WIDTH//2 - title.get_width()//2, 40))
            lbl = font_normal.render('Your name:', True, (220,220,220))
            screen.blit(lbl, (input_name.rect.x, input_name.rect.y - 28))
            input_name.draw(screen)
            lbl2 = font_normal.render('Room name (seed):', True, (220,220,220))
            screen.blit(lbl2, (input_room.rect.x, input_room.rect.y - 28))
            input_room.draw(screen)
            btn_back.draw(screen)

        elif current_state == STATE_JOIN:
            title = font_title.render('Join Room', True, (240,240,240))
            screen.blit(title, (WIDTH//2 - title.get_width()//2, 40))
            lbl = font_normal.render('Your name:', True, (220,220,220))
            screen.blit(lbl, (input_name.rect.x, input_name.rect.y - 28))
            input_name.draw(screen)
            lbl2 = font_normal.render('Room hash / name:', True, (220,220,220))
            screen.blit(lbl2, (input_room.rect.x, input_room.rect.y - 28))
            input_room.draw(screen)
            btn_back.draw(screen)

        elif current_state == STATE_LOBBY:
            title = font_title.render('Lobby', True, (240,240,240))
            screen.blit(title, (WIDTH//2 - title.get_width()//2, 20))
            room_lbl = font_normal.render('Room: ' + (room_hash_display[:8] if room_hash_display else ''), True, (200,200,255))
            screen.blit(room_lbl, (40, 100))
            btn_copy.draw(screen)

            # show feedback message for copy
            if copy_msg and time.time() - copy_msg[1] < 2.0:
                feedback = font_normal.render(copy_msg[0], True, (180,255,180))
                screen.blit(feedback, (WIDTH//2 - feedback.get_width()//2, 140))

            # peers
            peer_y = 150
            if net:
                my_label = font_normal.render('You: ' + net.peer_id + (' (Host)' if is_host else ''), True, (220,220,220))
                screen.blit(my_label, (40, peer_y))
                peer_y += 36
                for p in net.peers:
                    lbl = font_normal.render('Peer: ' + p, True, (200,200,200))
                    screen.blit(lbl, (40, peer_y))
                    peer_y += 30

            btn_back.draw(screen)
            if is_host:
                btn_start.draw(screen)

        pygame.display.flip()
        clock.tick(FPS)

    # cleanup
    if net:
        try:
            net.stop()
        except Exception:
            pass
    pygame.quit()
    sys.exit(0)


def copy_to_clipboard(text: str) -> bool:
    """Try wl-copy then xclip. Returns True on success."""
    try:
        subprocess.run(['wl-copy'], input=text.encode('utf-8'), check=True, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        try:
            subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode('utf-8'), check=True, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False


if __name__ == '__main__':
    main()
