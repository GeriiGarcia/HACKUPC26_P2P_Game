import json
import time
import uuid
import os
import base64
import sys

# Conditionally import for native environments
if sys.platform != 'emscripten':
    import socket
    import threading
    import rsa
    try:
        from Cryptodome.Cipher import AES
        from Cryptodome.Random import get_random_bytes
        from Cryptodome.Util.Padding import pad, unpad
    except ImportError:
        pass # Fallback handled in code
else:
    # WASM dummies
    rsa = None
    threading = None
    socket = None

KEYS_DIR = "keys"
DEFAULT_PORT = 14200 
DISCOVERY_PORT = 14201

class NetworkDriver:
    def __init__(self, manager):
        self.manager = manager
    def start(self): pass
    def stop(self): pass
    def send_to_peer(self, peer_id, message): pass
    def broadcast(self, message): pass

class WasmDriver(NetworkDriver):
    def __init__(self, manager):
        super().__init__(manager)
        try:
            from platform import window
            self.bridge = window.p2pBridge
            self.bridge.onMessage(self._on_js_message)
            self.bridge.onConnection(self._on_js_connection)
        except Exception as e:
            print(f"[WASM-DRIVER] Error initializing bridge: {e}")
            self.bridge = None

    def _on_js_message(self, remote_id, msg):
        self.manager._process_incoming_message(msg, None, (remote_id, 0))

    def _on_js_connection(self, remote_id):
        if remote_id not in self.manager.peers:
            self.manager.peers[remote_id] = {"socket": None, "ip": "wasm", "port": 0}
            if self.manager.on_peer_connected:
                self.manager.on_peer_connected(remote_id)

    def start(self):
        if self.bridge:
            print(f"[WASM-DRIVER] Iniciado driver WebRTC. Peer ID: {self.bridge.myPeerId}")

    def send_to_peer(self, peer_id, message):
        if self.bridge: self.bridge.send(peer_id, message)

    def broadcast(self, message):
        if self.bridge: self.bridge.broadcast(message)

class NativeDriver(NetworkDriver):
    def __init__(self, manager):
        super().__init__(manager)
        import socket
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.port = DEFAULT_PORT
        while True:
            try:
                self.tcp_socket.bind(('0.0.0.0', self.port))
                break
            except OSError:
                self.port += 1
        self.tcp_socket.listen(5)
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except: pass
        self.udp_socket.bind(('', DISCOVERY_PORT))

    def start(self):
        import threading
        threading.Thread(target=self._tcp_listener, daemon=True).start()
        threading.Thread(target=self._udp_listener, daemon=True).start()
        threading.Thread(target=self._udp_broadcaster, daemon=True).start()
        print(f"[NATIVE-DRIVER] Iniciado en puerto TCP {self.port}")

    def stop(self):
        try:
            self.tcp_socket.close()
            self.udp_socket.close()
        except: pass

    def send_to_peer(self, peer_id, message):
        peer_info = self.manager.peers.get(peer_id)
        if peer_info and peer_info["socket"]:
            try:
                data = (json.dumps(message) + "\n").encode('utf-8')
                peer_info["socket"].sendall(data)
            except: self.manager._remove_peer(peer_id)

    def broadcast(self, message):
        data = (json.dumps(message) + "\n").encode('utf-8')
        for pid, pinfo in list(self.manager.peers.items()):
            if pinfo["socket"]:
                try: pinfo["socket"].sendall(data)
                except: self.manager._remove_peer(pid)

    def _tcp_listener(self):
        import threading
        while self.manager.running:
            try:
                client_sock, addr = self.tcp_socket.accept()
                threading.Thread(target=self._handle_client, args=(client_sock, addr), daemon=True).start()
            except:
                if self.manager.running: time.sleep(0.5)

    def _handle_client(self, client_sock, addr):
        buffer = ""
        connected_peer_id = None
        while self.manager.running:
            try:
                data = client_sock.recv(65536)
                if not data: break
                buffer += data.decode('utf-8')
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        msg = json.loads(line)
                        peer_id_msg = self.manager._process_incoming_message(msg, client_sock, addr)
                        if peer_id_msg: connected_peer_id = peer_id_msg
            except: break
        client_sock.close()
        if connected_peer_id: self.manager._remove_peer(connected_peer_id, client_sock)

    def _udp_broadcaster(self):
        while self.manager.running:
            msg = json.dumps({
                "type": "DISCOVERY",
                "room_hash": self.manager.room_hash,
                "peer_id": self.manager.peer_id,
                "tcp_port": self.port
            }).encode('utf-8')
            try: self.udp_socket.sendto(msg, ('<broadcast>', DISCOVERY_PORT))
            except: pass
            time.sleep(2)

    def _udp_listener(self):
        while self.manager.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                msg = json.loads(data.decode('utf-8'))
                if msg.get("type") == "DISCOVERY" and msg.get("room_hash") == self.manager.room_hash:
                    other_peer = msg.get("peer_id")
                    other_port = msg.get("tcp_port")
                    if other_peer and other_peer != self.manager.peer_id and other_peer not in self.manager.peers:
                        self.connect_to_peer(addr[0], other_port, other_peer)
            except: pass

    def connect_to_peer(self, ip, port, other_peer_id=None):
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((ip, port))
            sock.settimeout(None)
            if other_peer_id:
                self.manager.peers[other_peer_id] = {"socket": sock, "ip": ip, "port": port}
                if self.manager.on_peer_connected: self.manager.on_peer_connected(other_peer_id)
            hello_msg = {"action": "HELLO", "peerId": self.peer_id, "room_hash": self.manager.room_hash}
            sock.sendall((json.dumps(hello_msg) + "\n").encode('utf-8'))
            import threading
            threading.Thread(target=self._handle_client, args=(sock, (ip, port)), daemon=True).start()
        except:
            if other_peer_id: self.manager._remove_peer(other_peer_id)

class NetworkManager:
    def __init__(self, room_hash, peer_id=None):
        self.room_hash = room_hash
        self.peer_id = peer_id or f"jugador_{str(uuid.uuid4())[:6]}"
        self.running = False
        self.peers = {}
        self.ledgers = {self.peer_id: []} 
        self.seq = 0
        self.on_message_received = None
        self.on_peer_connected = None
        self.on_peer_disconnected = None
        self.public_key, self.private_key = self._load_or_create_keys()
        self.peer_public_keys = {} 
        if sys.platform == 'emscripten':
            self.driver = WasmDriver(self)
        else:
            self.driver = NativeDriver(self)

    def _load_or_create_keys(self):
        if sys.platform == 'emscripten':
            return None, None
        try:
            import rsa
            os.makedirs(KEYS_DIR, exist_ok=True)
            pub_path = os.path.join(KEYS_DIR, f"{self.peer_id}_public.pem")
            priv_path = os.path.join(KEYS_DIR, f"{self.peer_id}_private.pem")
            if os.path.exists(pub_path) and os.path.exists(priv_path):
                with open(pub_path, 'rb') as f: pub = rsa.PublicKey.load_pkcs1(f.read())
                with open(priv_path, 'rb') as f: priv = rsa.PrivateKey.load_pkcs1(f.read())
                return pub, priv
            pub, priv = rsa.newkeys(512)
            with open(pub_path, 'wb') as f: f.write(pub.save_pkcs1())
            with open(priv_path, 'wb') as f: f.write(priv.save_pkcs1())
            return pub, priv
        except: return None, None

    def start(self):
        self.running = True
        self.driver.start()

    def stop(self):
        self.running = False
        self.driver.stop()

    def send_event(self, action, **kwargs):
        self.seq += 1
        event = {"peerId": self.peer_id, "seq": self.seq, "timestamp": int(time.time()), "action": action}
        event.update(kwargs)
        self.ledgers[self.peer_id].append(event)
        self.driver.broadcast(event)
        return event

    def _remove_peer(self, peer_id, sock=None):
        if peer_id in self.peers:
            del self.peers[peer_id]
            if self.on_peer_disconnected: self.on_peer_disconnected(peer_id)

    def _process_incoming_message(self, msg, client_sock, addr):
        sender_id = msg.get("peerId")
        if not sender_id: return None
        if msg.get("action") == "HELLO":
            if msg.get("room_hash") == self.room_hash and sender_id != self.peer_id:
                is_new = sender_id not in self.peers
                self.peers[sender_id] = {"socket": client_sock, "ip": addr[0], "port": addr[1]}
                if is_new and self.on_peer_connected: self.on_peer_connected(sender_id)
            return sender_id
        if sender_id != self.peer_id:
            if self.on_message_received: self.on_message_received(msg)
        return sender_id

    def encrypt_for_me(self, dict_data):
        return base64.b64encode(json.dumps(dict_data).encode('utf-8')).decode('utf-8')
    def decrypt_for_me(self, b64):
        try: return json.loads(base64.b64decode(b64).decode('utf-8'))
        except: return None
    def encrypt_chest(self, d): return self.encrypt_for_me(d)
    def decrypt_chest(self, b): return self.decrypt_for_me(b)
