/**
 * wasm_bridge.js
 * Bridge entre Python (WASM) y el Navegador para P2P WebRTC.
 * Utiliza SimplePeer para simplificar la gestión de DataChannels.
 */

window.p2pBridge = {
    peers: {}, // peerId -> SimplePeer instance
    onMessageCallback: null,
    onConnectionCallback: null,
    myPeerId: "browser_" + Math.random().toString(36).substr(2, 6),

    init: function() {
        console.log("[BRIDGE] Initialized with PeerID:", this.myPeerId);
        // Aquí podríamos iniciar la señalización automática si tuviéramos un server
    },

    // Llamado desde Python
    send: function(peerId, message) {
        const peer = this.peers[peerId];
        if (peer && peer.connected) {
            peer.send(JSON.stringify(message));
            return true;
        }
        console.warn("[BRIDGE] Peer not connected or not found:", peerId);
        return false;
    },

    broadcast: function(message) {
        let count = 0;
        const data = JSON.stringify(message);
        for (let pid in this.peers) {
            if (this.peers[pid].connected) {
                this.peers[pid].send(data);
                count++;
            }
        }
        return count;
    },

    // Configuración de callbacks desde Python
    onMessage: function(callback) {
        this.onMessageCallback = callback;
    },

    onConnection: function(callback) {
        this.onConnectionCallback = callback;
    },

    // Lógica interna de WebRTC (SimplePeer)
    connectTo: function(remotePeerId, isInitiator, signalingData = null) {
        console.log("[BRIDGE] Connecting to:", remotePeerId, "Initiator:", isInitiator);
        
        const peer = new SimplePeer({
            initiator: isInitiator,
            trickle: false // Simplificamos para el handshake inicial
        });

        peer.on('signal', data => {
            console.log("[BRIDGE] SIGNAL generated for", remotePeerId, ":", JSON.stringify(data));
            // En una versión real, esto se enviaría al signaling server
            // Para el MVP, el usuario puede tener que copiar/pegar este JSON o usar un relay
            if (window.onBridgeSignal) {
                window.onBridgeSignal(remotePeerId, data);
            }
        });

        peer.on('connect', () => {
            console.log("[BRIDGE] Connected to", remotePeerId);
            this.peers[remotePeerId] = peer;
            if (this.onConnectionCallback) {
                // Notificar a Python
                this.onConnectionCallback(remotePeerId);
            }
        });

        peer.on('data', data => {
            const msg = JSON.parse(data.toString());
            if (this.onMessageCallback) {
                this.onMessageCallback(remotePeerId, msg);
            }
        });

        peer.on('error', err => console.error("[BRIDGE] Peer error:", err));

        if (signalingData) {
            peer.signal(signalingData);
        }

        this.peers[remotePeerId] = peer;
    }
};

window.p2pBridge.init();
