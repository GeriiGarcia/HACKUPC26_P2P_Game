# Recreacion de Minecraft P2P pero usando PyOpenGL

Quiero que recrees una especie de juego como Minecraft pero en 2D y con OpenGL.

La mecanica sera la misa que ahora hay hecha pero jugando a un juego que sea un poco mas divertido y entretenido de ver.

Lo que quiero es que cada jugador tenga una camara y pueda ver todo el mapa, pero solo pueda interactuar con los bloques que estan cerca de el.

El mapa estara limitado a 400x400 bloques y se generara proceduralmente.

Para comunicarse entre si los jugadores usaremos Sockets como se usa hasta ahora.

Tambien usaremos la red ledgers y DHT-based swarming. Lo que se implementara con esto sera el inventario y el estado del mundo. Cuando un usuario pique un bloque, este se lo enviara a sus pares y se actualizaran los ledgers de cada uno con el nuevo estado del mapa. Cada inventario, estara protegido con una llave publica de cada usuario, de forma que solo el usuario pueda desencriptar el inventario que tiene. Cuando un jugador entra a la partida, en cualquier momento puede entrar, tiene que recuperar el inventario y el mundo. Cada vez que un usuario rompe un bloque, actualiza el estado del mapa en el ledger. Le envia que ha actualizado el ledger a los otros usuarios, de esta manera, siempre habra un usuario que tenga el mapa completo en todo momento y no se perdera informacion.  



Habran varios tipos de materiales que se podran minar y usar para construir.

Los bloques que se pueden picar son:
- Tierra
- Piedra
- Madera

Los bloques que se pueden colocar son:
- Tierra
- Piedra
- Madera

Habran varios tipos de herramientas que se podran usar para picar los bloques:
- Pico: Se crea con un bloque de madera y 3 bloques de piedra
- Pala: Se crea con un bloque de madera y 1 bloque de piedra
- Hacha: Se crea con un bloque de madera y 3 bloques de madera

Habran varios tipos de alimentos que se podran comer:
- Pan: Se crea con 3 bloques de trigo
- Carne: Se crea cuando se mata a un animal
