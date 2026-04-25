import argparse
import hashlib
import json
import math
import os
import queue
import secrets
import socket
import string
import subprocess
import sys
import threading
import time
from array import array

import pygame
import pygame.midi


WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 320
FPS = 60

WHITE_KEY_W = 100
WHITE_KEY_H = 220
BLACK_KEY_W = 60
BLACK_KEY_H = 140

HIGHLIGHT_MS = 300
ROOM_CODE_LENGTH = 6
DEFAULT_LAN_PORT = 5000

NOTE_MIN = 60  # C4
NOTE_MAX = 77  # F5 (C4 + 1.5 octaves)

WHITE_PCS = {0, 2, 4, 5, 7, 9, 11}
BLACK_PCS = {1, 3, 6, 8, 10}

ROOM_CODE_ALPHABET = string.ascii_uppercase + string.digits


KEYBOARD_NOTE_MAP = {
    pygame.K_a: 60,  # C4
    pygame.K_w: 61,  # C#4
    pygame.K_s: 62,  # D4
    pygame.K_e: 63,  # D#4
    pygame.K_d: 64,  # E4
    pygame.K_f: 65,  # F4
    pygame.K_t: 66,  # F#4
    pygame.K_g: 67,  # G4
    pygame.K_y: 68,  # G#4
    pygame.K_h: 69,  # A4
    pygame.K_u: 70,  # A#4
    pygame.K_j: 71,  # B4
    pygame.K_k: 72,  # C5
    pygame.K_o: 73,  # C#5
    pygame.K_l: 74,  # D5
    pygame.K_p: 75,  # D#5
    pygame.K_SEMICOLON: 76,  # E5
    pygame.K_QUOTE: 77,  # F5
}


class SilentAudioOutput:
    """Last-resort fallback output when no audio backend is available."""

    def note_on(self, *_args, **_kwargs):
        return None

    def note_off(self, *_args, **_kwargs):
        return None

    def close(self):
        return None


class SynthFallbackOutput:
    """
    Software synth fallback using pygame.mixer.

    This is used when no system MIDI output device exists (common on Linux
    without a running synth such as PipeWire/ALSA synth). It keeps the app
    audible instead of running silently.
    """

    def __init__(self, sample_rate=44100):
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=sample_rate, size=-16, channels=1, buffer=512)

        self.sample_rate = sample_rate
        self.wave_cache = {}
        self.note_channels = {}
        pygame.mixer.set_num_channels(64)

    @staticmethod
    def note_to_freq(note):
        return 440.0 * (2.0 ** ((note - 69) / 12.0))

    def _wave_for_note(self, note):
        cached = self.wave_cache.get(note)
        if cached is not None:
            return cached

        freq = self.note_to_freq(note)
        duration_s = 1.0
        total = int(self.sample_rate * duration_s)
        fade = int(self.sample_rate * 0.01)  # 10ms anti-click fade
        amp = 11000

        buf = array("h")
        for i in range(total):
            t = i / self.sample_rate
            v = math.sin(2.0 * math.pi * freq * t)

            env = 1.0
            if i < fade:
                env = i / max(1, fade)
            elif i > total - fade:
                env = (total - i) / max(1, fade)

            buf.append(int(amp * v * env))

        snd = pygame.mixer.Sound(buffer=buf.tobytes())
        self.wave_cache[note] = snd
        return snd

    def note_on(self, note, velocity=110):
        if note in self.note_channels:
            return

        sound = self._wave_for_note(note)
        channel = pygame.mixer.find_channel(True)
        channel.set_volume(min(1.0, max(0.05, velocity / 127.0)))
        channel.play(sound, loops=-1)
        self.note_channels[note] = channel

    def note_off(self, note, _velocity=0):
        channel = self.note_channels.pop(note, None)
        if channel is not None:
            channel.fadeout(30)

    def close(self):
        for channel in self.note_channels.values():
            try:
                channel.stop()
            except Exception:
                pass
        self.note_channels.clear()


def build_key_layout():
    base_x = 80
    y = 70

    note_range = range(NOTE_MIN, NOTE_MAX + 1)

    white_keys = []
    white_index_by_note = {}
    white_i = 0
    for note in note_range:
        if note % 12 in WHITE_PCS:
            rect = pygame.Rect(base_x + white_i * WHITE_KEY_W, y, WHITE_KEY_W, WHITE_KEY_H)
            white_keys.append({"note": note, "rect": rect})
            white_index_by_note[note] = white_i
            white_i += 1

    black_keys = []
    for note in note_range:
        if note % 12 not in BLACK_PCS:
            continue

        left_white = note - 1
        if left_white not in white_index_by_note:
            continue

        rect = pygame.Rect(
            base_x + (white_index_by_note[left_white] + 1) * WHITE_KEY_W - BLACK_KEY_W // 2,
            y,
            BLACK_KEY_W,
            BLACK_KEY_H,
        )
        black_keys.append({"note": note, "rect": rect})

    return white_keys, black_keys


def get_note_from_mouse(pos, white_keys, black_keys):
    # Check black keys first because they visually overlap white keys.
    for key in black_keys:
        if key["rect"].collidepoint(pos):
            return key["note"]
    for key in white_keys:
        if key["rect"].collidepoint(pos):
            return key["note"]
    return None


def send_json_line_socket(sock_obj, payload):
    try:
        data = (json.dumps(payload) + "\n").encode("utf-8")
        sock_obj.sendall(data)
        return True
    except OSError:
        return False


def normalize_topic_hex(raw_topic):
    text = (raw_topic or "").strip()
    if not text:
        return None

    if len(text) == 64 and all(ch in string.hexdigits for ch in text):
        return text.lower()

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def start_pear_transport(topic_hex, incoming_queue, stop_event, node_cmd="node"):
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pear_p2p.js")
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"pear_p2p.js not found at: {script_path}")

    proc = subprocess.Popen(
        [node_cmd, script_path, topic_hex],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    send_lock = threading.Lock()

    def stdout_reader():
        while not stop_event.is_set():
            try:
                line = proc.stdout.readline() if proc.stdout else ""
            except Exception:
                break

            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.01)
                continue

            line = line.strip()
            if not line:
                continue

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            incoming_queue.put(msg)

    def stderr_reader():
        while not stop_event.is_set():
            try:
                line = proc.stderr.readline() if proc.stderr else ""
            except Exception:
                break

            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue

            print(f"[pear] {line.rstrip()}", file=sys.stderr)

    threading.Thread(target=stdout_reader, daemon=True).start()
    threading.Thread(target=stderr_reader, daemon=True).start()

    def send(payload):
        if proc.poll() is not None:
            return

        line = json.dumps(payload) + "\n"
        try:
            with send_lock:
                if proc.stdin:
                    proc.stdin.write(line)
                    proc.stdin.flush()
        except OSError:
            return

    def close():
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass

        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    return {"send": send, "close": close}


def socket_reader_thread(sock_obj, incoming_queue, stop_event, on_disconnect=None):
    """Read newline-delimited JSON from a socket in a background thread."""
    buffer = ""
    sock_obj.settimeout(0.5)

    while not stop_event.is_set():
        try:
            chunk = sock_obj.recv(4096)
        except socket.timeout:
            continue
        except OSError:
            break

        if not chunk:
            break

        buffer += chunk.decode("utf-8", errors="ignore")
        while True:
            idx = buffer.find("\n")
            if idx == -1:
                break

            line = buffer[:idx].strip()
            buffer = buffer[idx + 1 :]
            if not line:
                continue

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            incoming_queue.put(msg)

    if on_disconnect:
        on_disconnect(sock_obj)


def start_host_transport(port, incoming_queue, stop_event):
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("0.0.0.0", port))
    server_sock.listen()
    server_sock.settimeout(0.5)

    clients = set()
    clients_lock = threading.Lock()

    def remove_client(client_sock):
        with clients_lock:
            clients.discard(client_sock)
        try:
            client_sock.close()
        except OSError:
            pass

    def accept_loop():
        while not stop_event.is_set():
            try:
                client_sock, addr = server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            print(f"[net] Peer connected from {addr[0]}:{addr[1]}")
            with clients_lock:
                clients.add(client_sock)

            threading.Thread(
                target=socket_reader_thread,
                args=(client_sock, incoming_queue, stop_event, remove_client),
                daemon=True,
            ).start()

    accept_thread = threading.Thread(target=accept_loop, daemon=True)
    accept_thread.start()

    def send(payload):
        with clients_lock:
            snapshot = list(clients)

        dead = []
        for client_sock in snapshot:
            if not send_json_line_socket(client_sock, payload):
                dead.append(client_sock)

        for client_sock in dead:
            remove_client(client_sock)

    def close():
        try:
            server_sock.close()
        except OSError:
            pass

        with clients_lock:
            snapshot = list(clients)
            clients.clear()

        for client_sock in snapshot:
            try:
                client_sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                client_sock.close()
            except OSError:
                pass

    return {"send": send, "close": close}


def start_join_transport(host_ip, port, incoming_queue, stop_event):
    sock_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_obj.settimeout(6)
    sock_obj.connect((host_ip, port))

    threading.Thread(
        target=socket_reader_thread,
        args=(sock_obj, incoming_queue, stop_event),
        daemon=True,
    ).start()

    def send(payload):
        send_json_line_socket(sock_obj, payload)

    def close():
        try:
            sock_obj.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock_obj.close()
        except OSError:
            pass

    return {"send": send, "close": close}


def generate_room_code(length=ROOM_CODE_LENGTH):
    return "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(length))


def detect_local_ip():
    sock_obj = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock_obj.connect(("8.8.8.8", 80))
        return sock_obj.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock_obj.close()


def parse_port(raw):
    text = raw.strip()
    if not text:
        return DEFAULT_LAN_PORT
    if not text.isdigit():
        return None
    value = int(text)
    if 1 <= value <= 65535:
        return value
    return None


def prompt_network_session():
    print("=== P2P Piano ===")
    print("1) Host (LAN)")
    print("2) Join (LAN)")

    while True:
        choice = input("Choose option [1/2]: ").strip()

        if choice == "1":
            room_code = generate_room_code()
            local_ip = detect_local_ip()

            while True:
                port = parse_port(input(f"Port [{DEFAULT_LAN_PORT}]: "))
                if port is not None:
                    break
                print("Invalid port. Use a number between 1 and 65535.")

            print("\nHost session created")
            print(f"Room code: {room_code}")
            print(f"Share with joiners -> IP: {local_ip}  Port: {port}\n")
            return {
                "mode": "host",
                "room_code": room_code,
                "host_ip": local_ip,
                "port": port,
            }

        if choice == "2":
            while True:
                entered_room = input("Enter room code (from host): ").strip().upper()
                if entered_room:
                    break
                print("Room code cannot be empty.")

            while True:
                host_ip = input("Host IP: ").strip()
                if host_ip:
                    break
                print("Host IP cannot be empty.")

            while True:
                port = parse_port(input(f"Host port [{DEFAULT_LAN_PORT}]: "))
                if port is not None:
                    break
                print("Invalid port. Use a number between 1 and 65535.")

            print(f"\nJoining room {entered_room} at {host_ip}:{port}\n")
            return {
                "mode": "join",
                "room_code": entered_room,
                "host_ip": host_ip,
                "port": port,
            }

        print("Invalid option. Type 1 to create or 2 to join.")


def draw_piano(screen, white_keys, black_keys, pressed_local, remote_highlights, session_label):
    screen.fill((24, 24, 28))

    now_ms = pygame.time.get_ticks()

    # White keys
    for key in white_keys:
        note = key["note"]
        rect = key["rect"]

        color = (245, 245, 245)
        if note in pressed_local:
            color = (130, 210, 255)
        elif note in remote_highlights and remote_highlights[note] > now_ms:
            color = (255, 200, 120)

        pygame.draw.rect(screen, color, rect)
        pygame.draw.rect(screen, (30, 30, 30), rect, 2)

    # Black keys
    for key in black_keys:
        note = key["note"]
        rect = key["rect"]

        color = (22, 22, 22)
        if note in pressed_local:
            color = (70, 150, 210)
        elif note in remote_highlights and remote_highlights[note] > now_ms:
            color = (210, 120, 50)

        pygame.draw.rect(screen, color, rect)
        pygame.draw.rect(screen, (8, 8, 8), rect, 2)

    font = pygame.font.SysFont(None, 24)
    tip = font.render(
        "Keyboard: A W S E D F T G Y H U J K O L P ; ' (C4..F5)",
        True,
        (220, 220, 220),
    )
    screen.blit(tip, (80, 20))

    status = font.render(session_label, True, (180, 210, 180))
    screen.blit(status, (80, 44))


def main(topic=None, node_cmd="node", embedded=False):
    args_topic = topic
    args_node_cmd = node_cmd

    if args_topic is None:
        parser = argparse.ArgumentParser(description="P2P Piano")
        parser.add_argument(
            "--topic",
            help="Pear topic hex (64 chars) or room seed text. If provided, uses pear_p2p.js transport.",
        )
        parser.add_argument(
            "--node-cmd",
            default="node",
            help="Node command used to execute pear_p2p.js (default: node)",
        )
        args = parser.parse_args()
        args_topic = args.topic
        args_node_cmd = args.node_cmd

    incoming_queue = queue.Queue()
    stop_event = threading.Event()

    if args_topic:
        topic_hex = normalize_topic_hex(args_topic)
        if not topic_hex:
            print("Invalid topic/room seed.", file=sys.stderr)
            return

        try:
            transport = start_pear_transport(topic_hex, incoming_queue, stop_event, node_cmd=args_node_cmd)
            mode = "pear"
            room_code = topic_hex[:ROOM_CODE_LENGTH]
            session_label = f"PEAR topic {topic_hex[:12]}... | Room: {room_code}"
        except (OSError, FileNotFoundError) as exc:
            print(f"Pear transport startup failed: {exc}", file=sys.stderr)
            return
    else:
        session = prompt_network_session()
        mode = session["mode"]
        room_code = session["room_code"]
        port = session["port"]

        try:
            if mode == "host":
                transport = start_host_transport(port, incoming_queue, stop_event)
                session_label = f"HOST {session['host_ip']}:{port} | Room: {room_code}"
            else:
                transport = start_join_transport(session["host_ip"], port, incoming_queue, stop_event)
                session_label = f"JOIN {session['host_ip']}:{port} | Room: {room_code}"
        except OSError as exc:
            print(f"Network startup failed: {exc}", file=sys.stderr)
            return

    pygame.init()
    pygame.midi.init()

    audio_out = None
    try:
        default_id = pygame.midi.get_default_output_id()
        if default_id == -1:
            raise RuntimeError("No MIDI output device available")
        audio_out = pygame.midi.Output(default_id)
        audio_out.set_instrument(0)  # Acoustic Grand Piano
    except Exception as exc:
        print(
            f"Warning: MIDI output unavailable ({exc}). Switching to software synth fallback.",
            file=sys.stderr,
        )
        try:
            audio_out = SynthFallbackOutput()
        except Exception as synth_exc:
            print(
                f"Warning: software synth failed ({synth_exc}). Running silently.",
                file=sys.stderr,
            )
            audio_out = SilentAudioOutput()

    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption(f"P2P Piano LAN ({mode.upper()} - {room_code})")
    clock = pygame.time.Clock()

    white_keys, black_keys = build_key_layout()

    pressed_local = set()
    active_counts = {}  # note -> number of active note_on events (local + remote)
    remote_highlights = {}  # note -> expiry timestamp in ms

    def play_note(note):
        count = active_counts.get(note, 0)
        if count == 0:
            audio_out.note_on(note, 110)
        active_counts[note] = count + 1

    def stop_note(note):
        count = active_counts.get(note, 0)
        if count <= 1:
            active_counts.pop(note, None)
            audio_out.note_off(note, 0)
        else:
            active_counts[note] = count - 1

    running = True
    mouse_active_note = None

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                note = KEYBOARD_NOTE_MAP.get(event.key)
                if note is not None and note not in pressed_local:
                    pressed_local.add(note)
                    play_note(note)
                    transport["send"]({"type": "note_on", "note": note})

            elif event.type == pygame.KEYUP:
                note = KEYBOARD_NOTE_MAP.get(event.key)
                if note is not None and note in pressed_local:
                    pressed_local.remove(note)
                    stop_note(note)
                    transport["send"]({"type": "note_off", "note": note})

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                note = get_note_from_mouse(event.pos, white_keys, black_keys)
                if note is not None and note not in pressed_local:
                    pressed_local.add(note)
                    mouse_active_note = note
                    play_note(note)
                    transport["send"]({"type": "note_on", "note": note})

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if mouse_active_note is not None and mouse_active_note in pressed_local:
                    pressed_local.remove(mouse_active_note)
                    stop_note(mouse_active_note)
                    transport["send"]({"type": "note_off", "note": mouse_active_note})
                mouse_active_note = None

        # Consume all messages from JS process without blocking frame updates.
        while True:
            try:
                msg = incoming_queue.get_nowait()
            except queue.Empty:
                break

            msg_type = msg.get("type")
            note = msg.get("note")
            if not isinstance(note, int):
                continue

            if msg_type == "note_on":
                play_note(note)
                remote_highlights[note] = pygame.time.get_ticks() + HIGHLIGHT_MS
            elif msg_type == "note_off":
                stop_note(note)

        # Clean expired highlights
        now_ms = pygame.time.get_ticks()
        expired = [n for n, until in remote_highlights.items() if until <= now_ms]
        for n in expired:
            remote_highlights.pop(n, None)

        draw_piano(screen, white_keys, black_keys, pressed_local, remote_highlights, session_label)
        pygame.display.flip()
        clock.tick(FPS)

    # Graceful shutdown
    stop_event.set()
    transport["close"]()

    audio_out.close()
    pygame.midi.quit()
    if not embedded:
        pygame.quit()


if __name__ == "__main__":
    main()
