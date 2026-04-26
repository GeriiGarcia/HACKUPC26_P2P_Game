# Definición del Sistema: Tamagotchi en Red P2P

Quiero crear un juego interactivo llamado "Tamagotchi en Red", utilizando la base de red P2P (sockets, ledgers) y la estructura que ya tenemos del proyecto de Minecraft, pero adaptándolo completamente a una nueva mecánica. El archivo principal debe llamarse `main_mascota.py`.

## El Juego

El juego consistirá en una mascota virtual que vive en tu ordenador. La mecánica principal no es solo cuidar de ella localmente, sino que gracias a la conexión P2P, tu mascota puede "viajar" a la IP/Sala de un amigo para interactuar con su mascota, o la mascota de tu amigo puede visitar tu PC.

### Características Principales
1. **Cuidados Básicos:** 
   - **Necesidades:** Hambre, Diversión, Energía y Limpieza (Stats que decaen con el tiempo).
   - **Acciones:** Alimentar, bañar, mandar a dormir y jugar.
   
2. **Interacción P2P ("Viajes y Visitas"):**
   - **Conexión:** Mediante el sistema P2P ya diseñado (Hash de sala o IPs), un jugador se conecta con otro. Las pantallas se sincronizan para mostrar a ambas mascotas en la misma habitación virtual.
   - **Cuidado compartido:** Puedes cuidar la mascota de tu amigo si está de visita en tu pantalla (darle de comer, limpiarla).
   - **Interacción entre mascotas:** Las mascotas pueden jugar juntas. Si ambas mascotas interactúan en la misma sesión, sus estadísticas de "Diversión" aumentan más rápido o de forma especial.

## Arquitectura y Comunicación P2P

Mantendremos la arquitectura P2P robusta basada en Sockets de Python y Ledgers (Event Sourcing) sin servidor central.

### 1. Estado y Sincronización (Ledgers)
- Cada jugador mantendrá un Ledger local con el estado y los eventos de su propia mascota.
- Cuando hay una visita, ambos clientes comparten sus Ledgers y sincronizan el estado visual. El motor del juego leerá el ledger del rival para saber dónde está su mascota en la pantalla y qué animación está reproduciendo.
- Las acciones cruzadas (ej. el Jugador A alimenta a la mascota del Jugador B) se envían como un paquete P2P: `{"action": "FEED", "target": "mascota_B", "item": "manzana"}`. El Jugador B lo recibe, valida la acción en su juego, actualiza las stats de su mascota en su ledger y difunde el nuevo estado.

### 2. Archivos y Estructura
- **`main_mascota.py`**: El nuevo punto de entrada de la aplicación. Reemplaza a `main.py` y orquestará la red y la interfaz de la mascota.
- **Motor Gráfico (UI y Renderizado):** Se adaptará el motor base para que deje de renderizar bloques procedimentales y en su lugar renderice un entorno 2D (la habitación) y las entidades (sprites de las mascotas y la interfaz de botones).
- **Persistencia Segura:** Las estadísticas vitales de la mascota y su inventario se serializarán y guardarán localmente usando el sistema de encriptación RSA que se venía utilizando.

### 3. Requisitos de Adaptación de la Base (Minecraft -> Tamagotchi)
- **Eliminar generación de mundos:** Se borran los chunks, la generación procedimental y la lógica de bloques del mundo.
- **Cambio de Input:** En lugar de "picar" y "colocar" bloques, la lógica de clicks estará orientada a la UI interactiva (botones de acciones) y drag & drop de objetos sobre las entidades de las mascotas.
- **Lógica de Entidades:** Implementación de un ciclo de vida para la mascota (temporizadores para que baje el hambre y la diversión).
- **Payload P2P adaptado:** Cambiar los payloads de sincronización de mundos de Minecraft por payloads de actualización de variables de estado (X, Y, animaciones, stats vitales).
