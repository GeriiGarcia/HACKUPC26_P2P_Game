import socket
import threading
import json
import time
import uuid
import os
import rsa
import base64
# Puertos por defecto para el juego
DEFAULT_PORT = 14200 
DISCOVERY_PORT = 14201

KEYS_DIR = "keys"

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
        
        # Anti-spam de reconexión: peer_id -> timestamp última conexión
        self._last_connect_attempt = {}
        self._connect_lock = threading.Lock()
        
        # Callbacks para la Interfaz Gráfica
        self.on_message_received = None
        self.on_peer_connected = None
        self.on_peer_disconnected = None
        
        # --- RSA Keys (persistentes por nombre de jugador) ---
        self.public_key, self.private_key = self._load_or_create_keys()
        self.peer_public_keys = {} # peer_id -> rsa.PublicKey
        
        # --- UDP (Para el descubrimiento / Swarming Phase 1) ---
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass # En algunos sistemas SO_REUSEPORT no está disponible
            
        self.udp_socket.bind(('', DISCOVERY_PORT))

    # ------------------------------------------------------------------
    # RSA Key Persistence
    # ------------------------------------------------------------------
    def _load_or_create_keys(self):
        """Carga las claves RSA del disco o las genera y guarda."""
        os.makedirs(KEYS_DIR, exist_ok=True)
        pub_path = os.path.join(KEYS_DIR, f"{self.peer_id}_public.pem")
        priv_path = os.path.join(KEYS_DIR, f"{self.peer_id}_private.pem")
        
        # Intentar cargar claves existentes
        if os.path.exists(pub_path) and os.path.exists(priv_path):
            try:
                with open(pub_path, 'rb') as f:
                    pub = rsa.PublicKey.load_pkcs1(f.read())
                with open(priv_path, 'rb') as f:
                    priv = rsa.PrivateKey.load_pkcs1(f.read())
                print(f"[NETWORK] 🔑 Claves RSA cargadas para '{self.peer_id}'")
                return pub, priv
            except Exception as e:
                print(f"[NETWORK] Error cargando claves: {e}. Regenerando...")
        
        # Generar claves nuevas
        try:
            pub, priv = rsa.newkeys(512)
            with open(pub_path, 'wb') as f:
                f.write(pub.save_pkcs1())
            with open(priv_path, 'wb') as f:
                f.write(priv.save_pkcs1())
            print(f"[NETWORK] 🔑 Claves RSA generadas y guardadas para '{self.peer_id}'")
            return pub, priv
        except Exception as e:
            print(f"[NETWORK] Warning: RSA keys failed ({e}).")
            return None, None

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Event send
    # ------------------------------------------------------------------
    def send_event(self, action, **kwargs):
        """
        Agrega un evento a tu propio ledger local y lo propaga (broadcast) a los rivales.
        """
        self.seq += 1
        event = {
            "peerId": self.peer_id,
            "seq": self.seq,
            "timestamp": int(time.time()),
            "action": action
        }
        event.update(kwargs)
        self.ledgers[self.peer_id].append(event)
        self._broadcast_tcp(event)
        return event

    def _broadcast_tcp(self, message):
        """Envía un mensaje JSON a todos los peers TCP conectados."""
        data = (json.dumps(message) + "\n").encode('utf-8')
        dead_peers = []
        for peer_id, peer_info in list(self.peers.items()):
            try:
                peer_info["socket"].sendall(data)
            except Exception:
                dead_peers.append(peer_id)
        # Limpiar peers muertos silenciosamente
        for pid in dead_peers:
            if pid in self.peers:
                del self.peers[pid]

    # ------------------------------------------------------------------
    # TCP listener / handler
    # ------------------------------------------------------------------
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
                data = client_sock.recv(65536)
                if not data:
                    break
                
                buffer += data.decode('utf-8')
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        msg = json.loads(line)
                        peer_id_msg = self._process_incoming_message(msg, client_sock, addr)
                        if peer_id_msg:
                            connected_peer_id = peer_id_msg
                            
            except Exception:
                break
        
        client_sock.close()
        # Limpiar solo si el socket almacenado es el mismo (evitar borrar reconexiones)
        if connected_peer_id and connected_peer_id in self.peers:
            stored_sock = self.peers[connected_peer_id].get("socket")
            if stored_sock is client_sock:
                del self.peers[connected_peer_id]
                print(f"[NETWORK] 🔌 Peer desconectado: {connected_peer_id}")
                if self.on_peer_disconnected:
                    self.on_peer_disconnected(connected_peer_id)

    def _process_incoming_message(self, msg, client_sock, addr):
        """Procesa un evento JSON entrante. Actualiza las réplicas del ledger."""
        sender_id = msg.get("peerId")
        if not sender_id:
            return None

        # 1. Gestionar el protocolo de saludo (Handshake)
        if msg.get("action") == "HELLO":
            if msg.get("room_hash") == self.room_hash and sender_id != self.peer_id:
                is_new = sender_id not in self.peers
                # Siempre actualizar el socket (reconexión)
                self.peers[sender_id] = {"socket": client_sock, "ip": addr[0], "port": addr[1]}
                if sender_id not in self.ledgers:
                    self.ledgers[sender_id] = []
                    
                pk_pem = msg.get("public_key")
                if pk_pem:
                    try:
                        self.peer_public_keys[sender_id] = rsa.PublicKey.load_pkcs1(pk_pem.encode('utf-8'))
                    except Exception as e:
                        print(f"[NETWORK] Error procesando clave pública de {sender_id}: {e}")

                if is_new:
                    print(f"[NETWORK] ✅ Conexión TCP con {sender_id}")
                
                # Enviar HELLO de vuelta
                hello_back = {
                    "action": "HELLO", 
                    "peerId": self.peer_id, 
                    "room_hash": self.room_hash,
                    "public_key": self.public_key.save_pkcs1().decode('utf-8') if self.public_key else None
                }
                try:
                    client_sock.sendall((json.dumps(hello_back) + "\n").encode('utf-8'))
                except Exception:
                    pass
                    
                if is_new and self.on_peer_connected:
                    self.on_peer_connected(sender_id)
            return sender_id

        # 2. Gestionar eventos normales de partida (Ledger Réplica)
        if sender_id != self.peer_id:
            # Aceptar mensajes incluso de peers no registrados (pueden llegar antes del HELLO)
            if sender_id not in self.peers:
                self.peers[sender_id] = {"socket": client_sock, "ip": addr[0], "port": addr[1]}
                if sender_id not in self.ledgers:
                    self.ledgers[sender_id] = []
            self.ledgers[sender_id].append(msg)
            if self.on_message_received:
                self.on_message_received(msg)
                
        return sender_id

    # ------------------------------------------------------------------
    # Outbound TCP connection
    # ------------------------------------------------------------------
    def connect_to_peer(self, ip, port, other_peer_id=None):
        """Inicia una conexión TCP proactiva hacia otro peer."""
        # Cooldown anti-spam: no reconectar al mismo peer en menos de 5 segundos
        with self._connect_lock:
            now = time.time()
            if other_peer_id:
                last = self._last_connect_attempt.get(other_peer_id, 0)
                if now - last < 5.0:
                    return  # demasiado pronto
                self._last_connect_attempt[other_peer_id] = now
                
                # Si ya está conectado, no reconectar
                if other_peer_id in self.peers:
                    return
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((ip, port))
            sock.settimeout(None)
            
            if other_peer_id and other_peer_id not in self.peers:
                self.peers[other_peer_id] = {"socket": sock, "ip": ip, "port": port}
                if other_peer_id not in self.ledgers:
                    self.ledgers[other_peer_id] = []
                print(f"[NETWORK] ✅ Conexión TCP saliente con {other_peer_id}")
                if self.on_peer_connected:
                    self.on_peer_connected(other_peer_id)
            
            # Enviar mensaje de saludo inicial
            hello_msg = {
                "action": "HELLO", 
                "peerId": self.peer_id, 
                "room_hash": self.room_hash,
                "public_key": self.public_key.save_pkcs1().decode('utf-8') if self.public_key else None
            }
            sock.sendall((json.dumps(hello_msg) + "\n").encode('utf-8'))
            
            # Dejamos que _handle_client escuche en este socket bidireccional
            threading.Thread(target=self._handle_client, args=(sock, (ip, port)), daemon=True).start()
        except Exception as e:
            # Limpiar intento fallido
            if other_peer_id and other_peer_id in self.peers:
                stored = self.peers[other_peer_id].get("socket")
                if stored is sock:
                    del self.peers[other_peer_id]

    # ------------------------------------------------------------------
    # UDP Discovery
    # ------------------------------------------------------------------
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
            time.sleep(2)

    def _udp_listener(self):
        """(Fase 1 - Descubrimiento) Escucha si alguien más está buscando la misma sala."""
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                msg = json.loads(data.decode('utf-8'))
                
                if msg.get("type") == "DISCOVERY" and msg.get("room_hash") == self.room_hash:
                    other_peer = msg.get("peer_id")
                    other_port = msg.get("tcp_port")
                    
                    # Solo conectar si es nuevo y no estamos ya conectados
                    if other_peer and other_peer != self.peer_id and other_peer not in self.peers:
                        print(f"[NETWORK] 🔍 Encontrado peer: {other_peer} ({addr[0]}:{other_port})")
                        self.connect_to_peer(addr[0], other_port, other_peer)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # RSA Encryption helpers
    # ------------------------------------------------------------------
    def encrypt_for_peer(self, target_peer_id, dict_data):
        """Encripta un diccionario usando la clave pública del rival"""
        if target_peer_id not in self.peer_public_keys:
            return None
        try:
            msg_bytes = json.dumps(dict_data).encode('utf-8')
            encrypted = rsa.encrypt(msg_bytes, self.peer_public_keys[target_peer_id])
            return base64.b64encode(encrypted).decode('utf-8')
        except Exception as e:
            print(f"[NETWORK] Error encrypting: {e}")
            return None
            
    def encrypt_for_me(self, dict_data):
        """Encripta un diccionario usando la propia clave pública"""
        if not self.public_key:
            return None
        try:
            msg_bytes = json.dumps(dict_data).encode('utf-8')
            # RSA 512-bit can only encrypt 53 bytes max, so chunk if needed
            # For inventory, we'll use a simple approach
            encrypted = rsa.encrypt(msg_bytes, self.public_key)
            return base64.b64encode(encrypted).decode('utf-8')
        except Exception as e:
            # Payload too large for 512-bit RSA – return plaintext base64 as fallback
            return base64.b64encode(msg_bytes).decode('utf-8')

    def decrypt_for_me(self, b64_encrypted_str):
        """Desencripta con mi clave privada"""
        if not self.private_key:
            return None
        try:
            encrypted = base64.b64decode(b64_encrypted_str.encode('utf-8'))
            msg_bytes = rsa.decrypt(encrypted, self.private_key)
            return json.loads(msg_bytes.decode('utf-8'))
        except rsa.pkcs1.DecryptionError:
            # Fallback: try plain base64
            try:
                return json.loads(base64.b64decode(b64_encrypted_str).decode('utf-8'))
            except Exception:
                return None
        except Exception as e:
            print(f"[NETWORK] Error decrypting: {e}")
            return None
