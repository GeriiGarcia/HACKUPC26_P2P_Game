# Definición del Sistema: Hundir la Flota P2P

Quiero hacer el juego de hundir la flota en PyGame para 2 o más jugadores, aplicando una conexión P2P para guardar los datos y realizar las comunicaciones.

## El Juego

### La Sala
Al iniciar el juego, aparecerá una sala de espera con dos botones: "Unirse a la sala" y "Crear una nueva sala".

- **Crear una nueva sala:** Al presionar "Crear una nueva sala", aparecerá una entrada de texto para poner el nombre a la sala y dos botones: uno para volver al menú principal y otro para "Crear sala". Al crear la sala, se iniciará el juego y se nos dará la opción de copiar el hash de la sala al portapapeles (véase el apartado "Fase 1: Conexión y Generación de la Sala").
- **Unirse a una sala:** Al presionar "Unirse a una sala", nos aparecerá una entrada de texto donde pondremos el código/semilla de la sala que nos habrá enviado nuestro compañero. Al presionar el botón de "Unirse", nos uniremos directamente (véase el apartado "Fase 1: Conexión y Generación de la Sala").

### Datos y Organización
Cada jugador, al inicio de la partida, debe introducir las IPs de los otros jugadores. El juego tiene que estar pensado para varios modos de juego, pero empezaremos con el modo normal que se define más abajo.

Primero, cada jugador organiza su tablero y los barcos. Para esto usaremos un tablero de 12x12, donde cada jugador dispone de:
- 3 barcos de tamaño 2
- 2 barcos de tamaño 3
- 1 barco de tamaño 4

El juego se desarrolla en turnos.

### Modo Normal
En el modo normal, los jugadores tendrán los 2 tableros de cada oponente vacíos. En cada turno, deberá tirar a una casilla de cada usuario y darle al botón "Tirar". El turno pasará al siguiente jugador.

El jugador pierde cuando los 2 jugadores le han hundido todos los barcos.

En la pantalla habrá:
- Los tableros de cada jugador rival.
- Otros 2 tableros idénticos a la disposición del jugador (con los barcos que ha colocado) donde se verán los tiros de cada jugador rival.

## Arquitectura y Comunicación P2P

La transmisión de paquetes se implementará mediante Sockets de Python. Para mantener el estado de la partida en caso de que alguien salga, se hará mediante distributed ledgers y DHT-based swarming.

Aquí se presenta la arquitectura rigurosa, segura y viable para ejecutar este "Hundir la Flota" de 3 jugadores bajo los requisitos del reto, sin servidor central.

### Fase 1: Conexión y Generación de la Sala
La solución óptima para P2P es utilizar una Semilla de Sala (Room Code) compartida fuera de la aplicación (de palabra, por Telegram, etc.).

1. **El Topic del DHT:** El jugador que "crea" la sala inventa una palabra clave (ej: HackathonPear2026).
2. **El Hash:** El código pasa esta palabra por una función hash (SHA-256). El resultado (32 bytes) será el Topic al que se unirán.
3. **La Conexión:** Los otros 2 jugadores introducen *HackathonPear2026*, la aplicación calcula el mismo hash y, por lo tanto, el DHT de Pear los conecta directamente al enjambre (swarm) correcto.
4. **Generación del Ledger:** Una vez conectados, los 3 jugadores intercambian sus claves públicas (peerId). Todos comienzan a escuchar los registros (append-only logs) de los otros dos.

### Fase 2: El Esquema de Compromiso (Inicio de la Partida)
Aquí se demuestra la gestión real de "datos sensibles" sin un servidor central que valide las reglas. Cada jugador coloca sus barcos en su pantalla. ¿Cómo evitamos que muevan los barcos durante la partida si nadie más ve su tablero?

1. **La Matriz Local:** Cada jugador tiene su representación del tablero localmente (ej: un JSON o un string de coordenadas).
2. **El Peligro de la Fuerza Bruta:** Si solo se hace el hash del tablero (`Hash(tablero)`), los rivales podrían generar todos los tableros posibles en segundos, hacer su hash y compararlos hasta adivinar dónde están los barcos.
3. **El "Salt" (La clave):** Cada jugador debe generar una cadena de texto aleatoria secreta (Salt). Se combina el tablero y el Salt, y se calcula el hash: `Hash(tablero + Salt)`.
4. **El Envío:** Se envía este hash final al ledger.

```json
{
  "action": "COMMIT_BOARD",
  "peerId": "jugador_A",
  "board_hash": "a1b2c3d4..." 
}
```

Ahora todos están comprometidos. Nadie puede cambiar el tablero sin que cambie el hash original, pero nadie sabe dónde están los barcos del otro.

### Fase 3: El Bucle de Juego (Multijugador a 3)
Al ser 3 jugadores, el sistema de turnos debe ser estricto (A ataca a B y C, después B ataca a A y C, etc.).

1. **El Ataque:** El Jugador A decide atacar al Jugador C en la coordenada D4. Añade esto a su ledger:
```json
{
  "action": "FIRE",
  "target_peer": "jugador_C",
  "coord": "D4"
}
```

2. **La Resolución:** El DHT propaga esta acción. El Jugador C la lee en cuestión de milisegundos, comprueba su tablero local oculto y responde en su propio ledger:
```json
{
  "action": "RESULT",
  "target_peer": "jugador_A",
  "coord": "D4",
  "hit": true,
  "sunk": false
}
```

3. **El Estado Compartido:** Como los 3 jugadores están leyendo los ledgers de los 3 jugadores de manera asíncrona, todos verán que el Jugador A ha tocado un barco del Jugador C, y actualizarán las interfaces gráficas en consecuencia.

### Fase 4: La Verificación Final (El "Zero-Trust")
¿Qué pasa si el Jugador C miente y dice "Agua" cuando en realidad le habían tocado un barco? Aquí cierra el círculo la mecánica de los datos sensibles.

1. Cuando la partida acaba, todos los jugadores están obligados a publicar en el ledger su tablero en bruto y su Salt secreta.
2. La aplicación del resto de jugadores toma estos datos, calcula el hash, y comprueba que sea idéntico al `board_hash` de la Fase 2.
3. A continuación, la aplicación repasa automáticamente todo el historial de ataques de la Fase 3. Si detecta que en el turno 4 el Jugador C respondió "Agua" a una coordenada donde realmente (según el tablero recién revelado) había un barco, el juego declara al Jugador C como tramposo.

## Comunicación entre Peers y Ledgers

El núcleo de la sincronización del juego se basa en el concepto de *Event Sourcing* a través de la red P2P. No existe una "base de datos central" con el estado actual de la partida; en su lugar, el estado del juego se calcula dinámicamente leyendo el historial de eventos (el ledger) de todos los jugadores.

### 1. Topología de Red y Sockets
- Una vez que el DHT resuelve las IPs y puertos usando el Hash de la sala (Fase 1), se establece una red Mesh (Malla) completa.
- Al ser 3 jugadores (A, B y C), se establecen conexiones de Sockets TCP bidireccionales entre todos: A conecta con B y C; B conecta con A y C.
- Se utiliza TCP en lugar de UDP porque garantiza que los paquetes del ledger lleguen en orden y sin pérdidas, algo crítico para mantener la consistencia de los datos en un sistema append-only.

### 2. Estructura del Ledger Local
Cada jugador mantiene en la memoria de su programa tres ledgers separados:
- **Su propio ledger (Local):** Es el único en el que tiene permisos de escritura (Append-only).
- **El ledger del Rival 1 (Réplica):** Solo lectura. Se actualiza con los mensajes que llegan por el socket.
- **El ledger del Rival 2 (Réplica):** Solo lectura. Se actualiza con los mensajes que llegan por el socket.

### 3. El Protocolo de Mensajería
Para evitar desincronizaciones o trampas, cada mensaje que viaja por los Sockets de Python para ser añadido a un ledger debe contener un Número de Secuencia (`seq`) y un Timestamp.
Cuando el Jugador A realiza su turno (disparando a B y C, según el Modo Normal), empaqueta el evento, lo añade a su ledger local y lo envía (broadcast) por los sockets a B y C.

El payload JSON (codificado en bytes para el socket) tendrá esta estructura:
```json
{
  "peerId": "jugador_A",
  "seq": 14, 
  "timestamp": 1713532456,
  "action": "FIRE_MULTI",
  "targets": [
    {"target_peer": "jugador_B", "coord": "F7"},
    {"target_peer": "jugador_C", "coord": "A2"}
  ],
  "signature": "opcional_hash_de_verificacion"
}
```

### 4. Flujo de Sincronización P2P
1. **Emisión:** El Jugador A pulsa "Tirar" en PyGame. Python genera el JSON, lo guarda en `ledger_A`, y hace `socket_B.sendall()` y `socket_C.sendall()`.
2. **Recepción:** El Jugador B recibe el paquete. Primero, verifica que el `seq` sea el correcto (si el último mensaje de A fue el 13, este debe ser el 14).
3. **Validación y Escritura:** Si es válido, B añade este evento a su réplica local de `ledger_A`.
4. **Reacción:** El motor del juego de B detecta que hay un nuevo evento `FIRE_MULTI` dirigido a él en la coordenada F7. B comprueba su matriz secreta, genera el resultado (Tocado/Agua) y crea un nuevo evento en su propio `ledger_B`, propagándolo de vuelta a A y C.

### 5. Renderizado del Estado en PyGame
PyGame funciona a unos 60 frames por segundo (FPS). En cada frame, o cada vez que hay una actualización de red, el motor lógico del juego no lee variables sueltas, sino que reconstruye el estado leyendo todos los ledgers desde el `seq: 0` hasta el final.
- **Pintar tus tableros de defensa:** El juego lee `ledger_B` y `ledger_C`. Filtra todas las acciones `FIRE` o `FIRE_MULTI` donde el `target_peer` seas tú. Dibuja chinchetas rojas/blancas en tus propios barcos.
- **Pintar tus tableros de ataque:** El juego lee tu `ledger_A` para saber dónde has disparado, y luego cruza esa información con `ledger_B` y `ledger_C` buscando las acciones `RESULT` que respondan a tus disparos para pintar las casillas de los rivales.

### 6. Resolución de Caídas (Swarming fallback)
Si un jugador sufre una desconexión momentánea de 5 segundos, al reconectarse enviará un mensaje de sincronización:
```json
{
  "action": "SYNC", 
  "last_seq_known": 12
}
```
Los otros peers responderán enviándole por el socket todos los bloques de su ledger desde el 13 en adelante, permitiendo que el jugador caído reconstruya el estado de la partida inmediatamente y actualice la pantalla de PyGame.
