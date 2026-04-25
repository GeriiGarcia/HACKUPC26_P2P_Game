### Prompt per generar el codi:

**"Actua com un enginyer de programari expert en Python (Pygame), programació d'àudio MIDI i aplicacions P2P descentralitzades amb Pear Protocol (Hyperswarm).**

Vull desenvolupar un piano virtual P2P on dos usuaris es puguin connectar a la mateixa sala i tocar música junts en temps real. Cada vegada que un usuari prem una tecla, ha de sonar al seu ordinador, transmetre's via P2P a l'altre ordinador, sonar allà i il·luminar la tecla corresponent a la interfície.

**Restriccions i Arquitectura:**
1. **Frontend i Àudio:** Tot ha d'estar fet en Python utilitzant `pygame` per a la interfície gràfica i `pygame.midi` (o generació d'ones) per l'àudio. S'ha de mostrar un teclat de piano interactiu a la pantalla.
2. **P2P i Xarxa:** La connexió entre ordinadors s'ha de fer **exclusivament amb Pear Protocol (Hyperswarm)** per crear una xarxa descentralitzada usant el *hash* de la sala com a *topic*.
3. **Comunicació entre processos (Sense Sockets):** Com que Pear no té llibreries natives per a Python, el projecte constarà de dos fitxers: `main.py` i `pear_p2p.js`. L'script de Python utilitzarà `subprocess.Popen` per executar l'script de JavaScript en segon pla. S'han de comunicar únicament mitjançant `stdin` i `stdout` (Pipes). Està absolutament prohibit utilitzar llibreries de websockets o obrir ports locals.

**Flux de funcionament requerit:**
1. En obrir el joc, `pygame` demana un codi/nom de sala a l'usuari.
2. Python genera el hash d'aquest codi (SHA-256) i arrenca el subprocés `pear_p2p.js` passant-li el hash com a argument.
3. Quan un jugador fa clic o prem una tecla (ex: 'Do central / C4'), Python envia un JSON per `stdout` cap al procés Pear amb l'estructura `{"type": "note_on", "note": 60}` i fa sonar la nota localment.
4. L'script `pear_p2p.js` llegeix el JSON pel `stdin` i fa un *broadcast* als *peers* connectats a l'eixam d'Hyperswarm.
5. Quan l'script de Pear rep un missatge de la xarxa, l'imprimeix al `console.log()` perquè Python el llegeixi pel `stdout` del subprocés.
6. Un fil (*thread*) separat en Python llegeix constantment les dades entrants del procés Pear, processa el JSON i crida l'event per fer sonar el MIDI rebut i canviar el color de la tecla premuda per l'altre jugador durant 300ms.

**Què necessito que generis:**
* El codi sencer del fitxer `main.py` amb comentaris sobre com gestionar el fil de lectura de sortida estàndard per no bloquejar el bucle principal de Pygame.
* El codi sencer del fitxer `pear_p2p.js` amb la configuració d'Hyperswarm i la captura d'esdeveniments del `process.stdin`.
* Un petit arxiu `requirements.txt` / `package.json` o instruccions per instal·lar les dependències d'ambdós costats."