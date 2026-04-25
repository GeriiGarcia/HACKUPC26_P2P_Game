import hashlib
import json
import math
import queue
import subprocess
import sys
import threading
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

NOTE_MIN = 60  # C4
NOTE_MAX = 77  # F5 (C4 + 1.5 octaves)

WHITE_PCS = {0, 2, 4, 5, 7, 9, 11}
BLACK_PCS = {1, 3, 6, 8, 10}


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


def spawn_p2p_process(topic_hex):
    return subprocess.Popen(
        ["node", "pear_p2p.js", topic_hex],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def stdout_reader_thread(proc, incoming_queue, stop_event):
    """
    Read subprocess stdout in a dedicated thread.

    Why this is needed:
    - readline() blocks until a full line arrives.
    - If we do this in the pygame loop, rendering/input/audio would freeze while waiting.
    - A separate thread can block safely and push parsed JSON into a queue.
    - The main pygame loop stays responsive and only polls queue.get_nowait().
    """
    while not stop_event.is_set():
        line = proc.stdout.readline()
        if line == "":
            break

        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        incoming_queue.put(msg)


def stderr_reader_thread(proc, stop_event):
    while not stop_event.is_set():
        line = proc.stderr.readline()
        if line == "":
            break
        if line.strip():
            print(f"[pear] {line.strip()}", file=sys.stderr)


def send_json_line(proc, payload):
    if proc.stdin is None:
        return
    try:
        proc.stdin.write(json.dumps(payload) + "\n")
        proc.stdin.flush()
    except (BrokenPipeError, OSError):
        pass


def draw_piano(screen, white_keys, black_keys, pressed_local, remote_highlights):
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


def main():
    room_code = input("Enter room code: ").strip()
    if not room_code:
        room_code = "default-room"

    topic_hex = hashlib.sha256(room_code.encode("utf-8")).hexdigest()
    proc = spawn_p2p_process(topic_hex)

    incoming_queue = queue.Queue()
    stop_event = threading.Event()

    out_thread = threading.Thread(
        target=stdout_reader_thread,
        args=(proc, incoming_queue, stop_event),
        daemon=True,
    )
    err_thread = threading.Thread(
        target=stderr_reader_thread,
        args=(proc, stop_event),
        daemon=True,
    )
    out_thread.start()
    err_thread.start()

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
    pygame.display.set_caption("P2P Piano (C4-F5)")
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
                    send_json_line(proc, {"type": "note_on", "note": note})

            elif event.type == pygame.KEYUP:
                note = KEYBOARD_NOTE_MAP.get(event.key)
                if note is not None and note in pressed_local:
                    pressed_local.remove(note)
                    stop_note(note)
                    send_json_line(proc, {"type": "note_off", "note": note})

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                note = get_note_from_mouse(event.pos, white_keys, black_keys)
                if note is not None and note not in pressed_local:
                    pressed_local.add(note)
                    mouse_active_note = note
                    play_note(note)
                    send_json_line(proc, {"type": "note_on", "note": note})

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if mouse_active_note is not None and mouse_active_note in pressed_local:
                    pressed_local.remove(mouse_active_note)
                    stop_note(mouse_active_note)
                    send_json_line(proc, {"type": "note_off", "note": mouse_active_note})
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

        draw_piano(screen, white_keys, black_keys, pressed_local, remote_highlights)
        pygame.display.flip()
        clock.tick(FPS)

    # Graceful shutdown
    stop_event.set()

    try:
        if proc.stdin:
            proc.stdin.close()
    except OSError:
        pass

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

    audio_out.close()
    pygame.midi.quit()
    pygame.quit()


if __name__ == "__main__":
    main()
