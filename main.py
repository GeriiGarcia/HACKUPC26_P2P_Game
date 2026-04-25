import hashlib
import json
import queue
import subprocess
import sys
import threading

import pygame
import pygame.midi


WINDOW_WIDTH = 980
WINDOW_HEIGHT = 320
FPS = 60

WHITE_KEY_W = 100
WHITE_KEY_H = 220
BLACK_KEY_W = 60
BLACK_KEY_H = 140

HIGHLIGHT_MS = 300


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
}


class SilentMidiOutput:
    """Fallback output when no MIDI device is available."""

    def note_on(self, *_args, **_kwargs):
        return None

    def note_off(self, *_args, **_kwargs):
        return None

    def close(self):
        return None


def build_key_layout():
    base_x = 80
    y = 70

    white_notes = [60, 62, 64, 65, 67, 69, 71]
    black_notes = [61, 63, 66, 68, 70]

    white_keys = []
    for i, note in enumerate(white_notes):
        rect = pygame.Rect(base_x + i * WHITE_KEY_W, y, WHITE_KEY_W, WHITE_KEY_H)
        white_keys.append({"note": note, "rect": rect})

    black_pos = {
        61: base_x + WHITE_KEY_W - BLACK_KEY_W // 2,
        63: base_x + 2 * WHITE_KEY_W - BLACK_KEY_W // 2,
        66: base_x + 4 * WHITE_KEY_W - BLACK_KEY_W // 2,
        68: base_x + 5 * WHITE_KEY_W - BLACK_KEY_W // 2,
        70: base_x + 6 * WHITE_KEY_W - BLACK_KEY_W // 2,
    }

    black_keys = []
    for note in black_notes:
        rect = pygame.Rect(black_pos[note], y, BLACK_KEY_W, BLACK_KEY_H)
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
    tip = font.render("Keyboard: A W S E D F T G Y H U J (C4..B4)", True, (220, 220, 220))
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

    midi_out = None
    try:
        default_id = pygame.midi.get_default_output_id()
        if default_id == -1:
            raise RuntimeError("No MIDI output device available")
        midi_out = pygame.midi.Output(default_id)
        midi_out.set_instrument(0)  # Acoustic Grand Piano
    except Exception as exc:
        print(f"Warning: MIDI output unavailable ({exc}). Running silently.", file=sys.stderr)
        midi_out = SilentMidiOutput()

    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("P2P Piano (C4-B4)")
    clock = pygame.time.Clock()

    white_keys, black_keys = build_key_layout()

    pressed_local = set()
    active_counts = {}  # note -> number of active note_on events (local + remote)
    remote_highlights = {}  # note -> expiry timestamp in ms

    def play_note(note):
        count = active_counts.get(note, 0)
        if count == 0:
            midi_out.note_on(note, 110)
        active_counts[note] = count + 1

    def stop_note(note):
        count = active_counts.get(note, 0)
        if count <= 1:
            active_counts.pop(note, None)
            midi_out.note_off(note, 0)
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

    midi_out.close()
    pygame.midi.quit()
    pygame.quit()


if __name__ == "__main__":
    main()
