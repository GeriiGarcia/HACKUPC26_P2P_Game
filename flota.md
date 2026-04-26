# Hundir la Flota P2P — Cómo funciona

Este documento explica el funcionamiento actual del juego y, sobre todo, **cómo se sincroniza entre jugadores**.

---

## 1) Arquitectura general

El proyecto se divide en 3 piezas principales:

- `main.py`: bucle principal de Pygame, estados de pantalla, turnos, ranking y procesamiento de mensajes de red.
- `network.py`: descubrimiento de peers, conexión TCP y propagación de eventos.
- `game.py`: lógica de tablero (impactos, hundimientos, eliminación) y render de tableros de ataque/defensa.

Modelo mental: cada cliente corre su juego local y se sincroniza por eventos.

---

## 2) Descubrimiento y conexión P2P

### 2.1 Sala (room hash)

La sala se identifica con un hash SHA-256 generado desde el nombre/semilla de sala:

- función: `generate_room_hash(...)` en `main.py`

Solo peers con el mismo `room_hash` se consideran de la misma partida.

### 2.2 Descubrimiento LAN (UDP)

`NetworkManager` emite cada ~2 segundos un broadcast UDP con:

- `type: DISCOVERY`
- `room_hash`
- `peer_id`
- `tcp_port`

Los peers que escuchan (`_udp_listener`) y ven el mismo `room_hash` abren conexión TCP.

### 2.3 Canal de juego (TCP)

Tras conectar por TCP se intercambia `HELLO` para registrar al peer.

Los eventos reales de partida viajan por TCP como JSON delimitado por `\n`.

---

## 3) Sincronización de eventos

### 3.1 Envío

Cada vez que se llama a `send_event(action, **kwargs)`:

1. Se crea un evento con `peerId`, `seq`, `timestamp`, `action`.
2. Se añade al ledger local del emisor (`append-only`).
3. Se hace broadcast TCP al resto de peers.

### 3.2 Recepción

Al recibir un evento:

1. Se guarda en el ledger réplica del emisor.
2. Se entrega al callback `on_message_received`.
3. `main.py` lo consume desde `msg_queue` en cada frame y actualiza estado/UI.

---

## 4) Flujo de partida

## 4.1 Lobby

- Host envía `START_GAME`.
- Cada jugador prepara su flota (`Board`).
- Cuando está lista, envía `COMMIT_BOARD` con hash del tablero (`board + salt`).

Nota: actualmente el commit se usa para señalizar preparación y registro; no hay fase completa de verificación/reveal implementada en este código.

## 4.2 Turnos

- `all_players_sorted` define orden de turnos.
- En turno, un jugador selecciona **una coordenada por cada rival vivo**.
- Al pulsar fuego se envía `FIRE_MULTI` con lista de objetivos.

## 4.3 Resolución de disparos

Cuando llega `FIRE_MULTI`, cada defensor procesa solo los tiros cuyo `target_peer` es él:

- `my_board.receive_shot(x, y)` en `game.py` devuelve:
  - `hit` (agua/impacto)
  - `sunk` (si con ese tiro se completa un barco)
  - `sunk_cells` (coordenadas de todas las celdas del barco hundido)
  - `eliminated` (si ya no le quedan barcos)

Luego el defensor emite `RESULT` con esos datos.

---

## 5) Regla actual de visibilidad (compartida)

Regla vigente en el código:

- **Toda la mesa ve los impactos y hundimientos.**
- Cuando llega `RESULT`, todos actualizan su `AttackBoard` del jugador defensor (`sender`).
- Si `sunk=True`, se aplican `sunk_cells` y se pinta **X en todas las celdas** del barco hundido.
- El defensor también ve su propio barco hundido en su tablero inferior (defensa), con celdas en rojo y X.

Esto implementa modo de **información compartida global**.

---

## 6) Eliminación y fin de partida

- Si `receive_shot` detecta que todos los barcos del defensor están hundidos, marca `eliminated=True`.
- Se propaga por `RESULT` (`eliminated_peer`) y además por `PLAYER_ELIMINATED`.
- `announce_elimination(...)` evita duplicados con un `set` de eliminados.
- Cuando queda 1 vivo:
  - `game_over=True`
  - se calcula ranking final
  - se puede propagar `GAME_OVER` con ganador y ranking.

---

## 7) Consistencia y límites actuales

- Consistencia práctica: modelo **event-driven** con TCP (entrega fiable a conexiones activas).
- No hay consenso distribuido fuerte ni reconciliación histórica completa.
- El ledger es append-only por peer en memoria del proceso actual.
- Si un peer cae/reentra, no hay replay total de estado desde un origen autoritativo.

En resumen: sincroniza bien para partidas LAN normales, pero no es todavía un motor con tolerancia fuerte a particiones/rejoin complejo.

---

## 8) Archivos clave

- `network.py` → descubrimiento UDP, conexión TCP, envío/recepción de eventos.
- `main.py` → estados de juego, cola de mensajes, turnos, eliminación, ranking, render principal.
- `game.py` → reglas de tablero (`receive_shot`), hundimientos y dibujo de X.
