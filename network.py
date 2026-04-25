import socket
import threading
import json
import time
import uuid

# Puertos por defecto para el juego
DEFAULT_PORT = 14200 
DISCOVERY_PORT = 14201

class NetworkManager:
    def __init__(self, room_hash, peer_id=None):
        """
        Gestiona la red P2P del juego.
        Utiliza UDP Broadcast para descubrir peers en la red local (simulando un DHT)
        y Sockets TCP para sincronizar los ledgers de manera segura.
        """
        self.room_hash = room_hash
        self.peer_id = peer_id or f"jugador_{str(uuid.uuid4())[:6]}"
        self.running = False
        
        # --- TCP (Para eventos del juego y el Ledger) ---
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.port = DEFAULT_PORT
        
        # Si el puerto por defecto está ocupado (ej. jugamos en el mismo PC), busca uno libre
        while True:
            try:
                self.tcp_socket.bind(('0.0.0.0', self.port))
                break
            except OSError:
                self.port += 1
                
        self.tcp_socket.listen(5)
        
        # --- Estructura de Datos (Ledger y Peers) ---
        self.peers = {}  # peer_id -> {"socket": socket_obj, "ip": ip, "port": port}
        # Cada peer tiene su propio ledger (append-only)
        self.ledgers = {self.peer_id: []} 
        self.seq = 0
        
        # Callbacks para la Interfaz Gráfica
        self.on_message_received = None
        self.on_peer_connected = None
        
        # --- UDP (Para el descubrimiento / Swarming Phase 1) ---
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass # En algunos sistemas SO_REUSEPORT no está disponible
            
        self.udp_socket.bind(('', DISCOVERY_PORT))

    def start(self):
        """Inicia los hilos de red."""
        self.running = True
        threading.Thread(target=self._tcp_listener, daemon=True).start()
        threading.Thread(target=self._udp_listener, daemon=True).start()
        threading.Thread(target=self._udp_broadcaster, daemon=True).start()
        print(f"[NETWORK] Iniciado Peer '{self.peer_id}' en puerto TCP {self.port}")

    def stop(self):
        """Detiene la red de forma segura."""
        self.running = False
        try:
            self.tcp_socket.close()
            self.udp_socket.close()
        except:
            pass
        for peer in self.peers.values():
            try:
                peer['socket'].close()
            except:
                pass

    def send_event(self, action, **kwargs):
        """
        Agrega un evento a tu propio ledger local y lo propaga (broadcast) a los rivales.
        Ejemplo de uso: net.send_event("FIRE", target_peer="jugador_B", coord="D4")
        """
        self.seq += 1
        event = {
            "peerId": self.peer_id,
            "seq": self.seq,
            "timestamp": int(time.time()),
            "action": action
        }
        # Añadir el resto de datos al evento
        event.update(kwargs)
        
        # Guardar en nuestro ledger local (Write)
        self.ledgers[self.peer_id].append(event)
        
        # Propagar por la red TCP
        self._broadcast_tcp(event)
        return event

    def _broadcast_tcp(self, message):
        """Envía un mensaje JSON a todos los peers TCP conectados."""
        data = (json.dumps(message) + "\n").encode('utf-8')
        for peer_id, peer_info in list(self.peers.items()):
            try:
                peer_info["socket"].sendall(data)
            except Exception as e:
                print(f"[NETWORK] Error enviando a {peer_id}: {e}")
                
    def _tcp_listener(self):
        """Escucha conexiones TCP entrantes."""
        while self.running:
            try:
                client_sock, addr = self.tcp_socket.accept()
                threading.Thread(target=self._handle_client, args=(client_sock, addr), daemon=True).start()
            except Exception:
                if self.running:
                    time.sleep(0.5)

    def _handle_client(self, client_sock, addr):
        """Mantiene abierta la conexión TCP y lee el flujo de datos usando \\n como separador."""
        buffer = ""
        connected_peer_id = None
        
        while self.running:
            try:
                data = client_sock.recv(4096)
                if not data:
                    break # Se ha cerrado la conexión
                
                buffer += data.decode('utf-8')
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        msg = json.loads(line)
                        peer_id_msg = self._process_incoming_message(msg, client_sock, addr)
                        if peer_id_msg:
                            connected_peer_id = peer_id_msg
                            
            except Exception as e:
                print(f"[NETWORK] Desconexión o error con {addr}: {e}")
                break
        
        client_sock.close()
        # Si se desconectó, podríamos intentar reconectar o marcarlo como caído
        if connected_peer_id and connected_peer_id in self.peers:
            # del self.peers[connected_peer_id] # Dejamos la info para reconexiones (opcional)
            pass

    def _process_incoming_message(self, msg, client_sock, addr):
        """Procesa un evento JSON entrante. Actualiza las réplicas del ledger."""
        sender_id = msg.get("peerId")
        if not sender_id:
            return None

        # 1. Gestionar el protocolo de saludo (Handshake)
        if msg.get("action") == "HELLO":
            if msg.get("room_hash") == self.room_hash and sender_id != self.peer_id:
                if sender_id not in self.peers:
                    self.peers[sender_id] = {"socket": client_sock, "ip": addr[0], "port": addr[1]}
                    self.ledgers[sender_id] = []
                    print(f"[NETWORK] ✅ Conexión TCP establecida con {sender_id}")
                    if self.on_peer_connected:
                        self.on_peer_connected(sender_id)
            return sender_id

        # 2. Gestionar eventos normales de partida (Ledger Réplica)
        if sender_id != self.peer_id and sender_id in self.peers:
            self.ledgers[sender_id].append(msg)
            if self.on_message_received:
                self.on_message_received(msg)
                
        return sender_id

    def connect_to_peer(self, ip, port):
        """Inicia una conexión TCP proactiva hacia otro peer."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((ip, port))
            
            # Enviar mensaje de saludo inicial
            hello_msg = {
                "action": "HELLO", 
                "peerId": self.peer_id, 
                "room_hash": self.room_hash
            }
            sock.sendall((json.dumps(hello_msg) + "\n").encode('utf-8'))
            
            # Dejamos que _handle_client escuche en este socket bidireccional
            threading.Thread(target=self._handle_client, args=(sock, (ip, port)), daemon=True).start()
        except Exception as e:
            print(f"[NETWORK] ❌ Error conectando a {ip}:{port} -> {e}")

    def _udp_broadcaster(self):
        """(Fase 1 - Descubrimiento) Envía señales indicando 'Estoy en esta sala'."""
        while self.running:
            msg = json.dumps({
                "type": "DISCOVERY",
                "room_hash": self.room_hash,
                "peer_id": self.peer_id,
                "tcp_port": self.port
            }).encode('utf-8')
            try:
                self.udp_socket.sendto(msg, ('<broadcast>', DISCOVERY_PORT))
            except Exception:
                pass
            time.sleep(2) # Enviar señal cada 2 segundos

    def _udp_listener(self):
        """(Fase 1 - Descubrimiento) Escucha si alguien más está buscando la misma sala."""
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                msg = json.loads(data.decode('utf-8'))
                
                if msg.get("type") == "DISCOVERY" and msg.get("room_hash") == self.room_hash:
                    other_peer = msg.get("peer_id")
                    other_port = msg.get("tcp_port")
                    
                    # Si es alguien nuevo de mi misma sala, nos conectamos por TCP
                    if other_peer != self.peer_id and other_peer not in self.peers:
                        print(f"[NETWORK] 🔍 Encontrado peer de mi sala en LAN: {other_peer} ({addr[0]}:{other_port})")
                        self.connect_to_peer(addr[0], other_port)
            except Exception:
                pass
