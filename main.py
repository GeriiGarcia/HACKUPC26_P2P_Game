import pygame
import sys
import hashlib
import subprocess
import queue
from ui import Button, TextInput
from network import NetworkManager
from game import Board

# Configuración básica
WIDTH, HEIGHT = 800, 600
FPS = 60

# Colores
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
BLUE = (100, 150, 255)
DARK_BLUE = (50, 100, 200)

# Estados del juego
STATE_MENU = 0
STATE_CREATE_ROOM = 1
STATE_JOIN_ROOM = 2
STATE_ROOM_CREATED = 3
STATE_GAME = 4
STATE_LOBBY = 5

def generate_room_hash(room_name):
    """Genera un hash SHA-256 a partir del nombre de la sala (Semilla)."""
    return hashlib.sha256(room_name.encode('utf-8')).hexdigest()

def copy_to_clipboard(text):
    """Intenta copiar texto al portapapeles de forma robusta en Linux (Wayland/X11)."""
    try:
        subprocess.run(['wl-copy'], input=text.encode('utf-8'), check=True, stderr=subprocess.DEVNULL)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        try:
            subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode('utf-8'), check=True, stderr=subprocess.DEVNULL)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

def main():
    pygame.init()
        
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Hundir la Flota P2P")
    clock = pygame.time.Clock()

    font_title = pygame.font.SysFont(None, 64)
    font_normal = pygame.font.SysFont(None, 36)
    font_small = pygame.font.SysFont(None, 24)

    current_state = STATE_MENU

    net_manager = None
    is_host = False
    msg_queue = queue.Queue()
    
    # Variables de Partida
    my_board = None
    has_committed_board = False
    player_commits = {} # Aquí guardaremos los board_hash de los rivales

    def on_message_received(msg):
        msg_queue.put(msg)

    # Elementos UI - Menú Principal
    btn_create = Button(WIDTH//2 - 150, HEIGHT//2 - 50, 300, 50, "Crear una nueva sala", font_normal)
    btn_join = Button(WIDTH//2 - 150, HEIGHT//2 + 20, 300, 50, "Unirse a una sala", font_normal)

    # Elementos UI - Crear Sala
    input_create_room = TextInput(WIDTH//2 - 150, HEIGHT//2 - 50, 300, 40, font_normal)
    btn_create_confirm = Button(WIDTH//2 + 10, HEIGHT//2 + 20, 140, 40, "Crear sala", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)
    btn_create_back = Button(WIDTH//2 - 150, HEIGHT//2 + 20, 140, 40, "Volver", font_normal)
    
    # Elementos UI - Sala Creada
    room_hash_display = ""
    btn_copy_hash = Button(WIDTH//2 - 150, HEIGHT//2 + 20, 300, 40, "Copiar Hash al Portapapeles", font_normal)
    btn_goto_lobby = Button(WIDTH//2 - 150, HEIGHT//2 + 80, 300, 40, "Ir a la Sala de Espera", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)

    # Elementos UI - Lobby
    btn_start_lobby = Button(WIDTH//2 - 150, HEIGHT - 100, 300, 40, "Empezar Partida", font_normal, bg_color=(50, 200, 50), hover_color=(50, 150, 50))

    # Elementos UI - Unirse a Sala
    input_join_room = TextInput(WIDTH//2 - 200, HEIGHT//2 - 50, 400, 40, font_normal)
    btn_join_confirm = Button(WIDTH//2 + 10, HEIGHT//2 + 20, 140, 40, "Unirse", font_normal, bg_color=BLUE, hover_color=DARK_BLUE)
    btn_join_back = Button(WIDTH//2 - 150, HEIGHT//2 + 20, 140, 40, "Volver", font_normal)

    running = True
    while running:
        screen.fill(GRAY)
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if current_state == STATE_MENU:
                if btn_create.handle_event(event):
                    current_state = STATE_CREATE_ROOM
                    input_create_room.text = ""
                if btn_join.handle_event(event):
                    current_state = STATE_JOIN_ROOM
                    input_join_room.text = ""
            
            elif current_state == STATE_CREATE_ROOM:
                input_create_room.handle_event(event)
                if btn_create_confirm.handle_event(event):
                    if input_create_room.text.strip():
                        room_hash_display = generate_room_hash(input_create_room.text.strip())
                        is_host = True
                        net_manager = NetworkManager(room_hash_display)
                        net_manager.on_message_received = on_message_received
                        net_manager.start()
                        current_state = STATE_ROOM_CREATED
                if btn_create_back.handle_event(event):
                    current_state = STATE_MENU
            
            elif current_state == STATE_ROOM_CREATED:
                if btn_copy_hash.handle_event(event):
                    if copy_to_clipboard(room_hash_display):
                        print(f"Hash copiado con éxito: {room_hash_display}")
                    else:
                        print("Error copiando: No se encontró wl-copy ni xclip en el sistema. Asegúrate de tener 'wl-clipboard' instalado.")
                if btn_goto_lobby.handle_event(event):
                    current_state = STATE_LOBBY
                    
            elif current_state == STATE_JOIN_ROOM:
                input_join_room.handle_event(event)
                if btn_join_confirm.handle_event(event):
                    room_hash = input_join_room.text.strip()
                    if room_hash:
                        print(f"Conectando a sala con Hash/Topic: {room_hash}")
                        is_host = False
                        net_manager = NetworkManager(room_hash)
                        net_manager.on_message_received = on_message_received
                        net_manager.start()
                        current_state = STATE_LOBBY
                if btn_join_back.handle_event(event):
                    current_state = STATE_MENU

            elif current_state == STATE_LOBBY:
                if is_host and btn_start_lobby.handle_event(event):
                    # El host decide empezar
                    players_list = list(net_manager.peers.keys())
                    net_manager.send_event("START_GAME", players=players_list)
                    
                    my_board = Board(WIDTH//2 - (12 * 30)//2, HEIGHT//2 - (12 * 30)//2)
                    has_committed_board = False
                    current_state = STATE_GAME
            
            elif current_state == STATE_GAME:
                if my_board:
                    my_board.handle_event(event)
                    
                    # Si acabamos de colocar todos los barcos, hacemos COMMIT
                    if my_board.is_ready and not has_committed_board:
                        board_hash = my_board.get_board_hash()
                        print(f"Enviando COMMIT_BOARD: {board_hash}")
                        net_manager.send_event("COMMIT_BOARD", board_hash=board_hash)
                        has_committed_board = True

        # Procesar mensajes de red entrantes
        while not msg_queue.empty():
            msg = msg_queue.get()
            if msg.get("action") == "START_GAME":
                print(f"El Host ha iniciado la partida. Jugadores: {msg.get('players')}")
                my_board = Board(WIDTH//2 - (12 * 30)//2, HEIGHT//2 - (12 * 30)//2)
                has_committed_board = False
                current_state = STATE_GAME
            elif msg.get("action") == "COMMIT_BOARD":
                peer_id = msg.get("peerId")
                b_hash = msg.get("board_hash")
                player_commits[peer_id] = b_hash
                print(f"[JUEGO] El jugador {peer_id} ha fijado su flota.")

        # Lógica de dibujado
        if current_state == STATE_MENU:
            title = font_title.render("Hundir la Flota P2P", True, BLACK)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, HEIGHT//4))
            btn_create.draw(screen)
            btn_join.draw(screen)
            
        elif current_state == STATE_CREATE_ROOM:
            title = font_title.render("Crear Nueva Sala", True, BLACK)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, HEIGHT//4))
            
            label = font_normal.render("Introduce un nombre o semilla para la sala:", True, BLACK)
            screen.blit(label, (WIDTH//2 - label.get_width()//2, HEIGHT//2 - 90))
            
            input_create_room.draw(screen)
            btn_create_confirm.draw(screen)
            btn_create_back.draw(screen)
            
        elif current_state == STATE_ROOM_CREATED:
            title = font_title.render("Sala Creada", True, BLACK)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, HEIGHT//4 - 50))
            
            label = font_normal.render("Comparte este Hash con tus amigos para que se unan:", True, BLACK)
            screen.blit(label, (WIDTH//2 - label.get_width()//2, HEIGHT//2 - 100))
            
            # Mostrar el hash (cortado si es muy largo, pero como es SHA256 son 64 chars)
            # Lo dividimos en dos líneas o usamos font_small
            hash_surf1 = font_small.render(room_hash_display[:32], True, DARK_BLUE)
            hash_surf2 = font_small.render(room_hash_display[32:], True, DARK_BLUE)
            screen.blit(hash_surf1, (WIDTH//2 - hash_surf1.get_width()//2, HEIGHT//2 - 50))
            screen.blit(hash_surf2, (WIDTH//2 - hash_surf2.get_width()//2, HEIGHT//2 - 20))
            
            btn_copy_hash.draw(screen)
            btn_goto_lobby.draw(screen)
            
        elif current_state == STATE_JOIN_ROOM:
            title = font_title.render("Unirse a la Sala", True, BLACK)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, HEIGHT//4))
            
            label = font_normal.render("Introduce el Hash / Semilla de la sala:", True, BLACK)
            screen.blit(label, (WIDTH//2 - label.get_width()//2, HEIGHT//2 - 90))
            
            input_join_room.draw(screen)
            btn_join_confirm.draw(screen)
            btn_join_back.draw(screen)
            
        elif current_state == STATE_LOBBY:
            title = font_title.render("Sala de Espera", True, BLACK)
            screen.blit(title, (WIDTH//2 - title.get_width()//2, 50))
            
            # Listar jugadores
            y_offset = 150
            
            if net_manager:
                you_lbl = font_normal.render(f"Tú: {net_manager.peer_id} " + ("(Host)" if is_host else ""), True, DARK_BLUE)
                screen.blit(you_lbl, (WIDTH//2 - you_lbl.get_width()//2, y_offset))
                y_offset += 40
                
                for peer_id in net_manager.peers:
                    peer_lbl = font_normal.render(f"Jugador conectado: {peer_id}", True, BLACK)
                    screen.blit(peer_lbl, (WIDTH//2 - peer_lbl.get_width()//2, y_offset))
                    y_offset += 40
                    
            if is_host:
                btn_start_lobby.draw(screen)
            else:
                wait_lbl = font_normal.render("Esperando a que el host inicie la partida...", True, (100, 100, 100))
                screen.blit(wait_lbl, (WIDTH//2 - wait_lbl.get_width()//2, HEIGHT - 100))

        elif current_state == STATE_GAME:
            screen.fill((20, 20, 40))
            if my_board:
                my_board.draw(screen, font_small)
                
                # Si nosotros ya hemos acabado, mostramos estado de los rivales
                if my_board.is_ready:
                    ready_count = len(player_commits) + 1 # +1 por nosotros
                    total_players = len(net_manager.peers) + 1
                    
                    status_text = f"Jugadores listos: {ready_count} / {total_players}"
                    status_lbl = font_normal.render(status_text, True, (200, 200, 200))
                    screen.blit(status_lbl, (WIDTH//2 - status_lbl.get_width()//2, HEIGHT - 50))
            
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
