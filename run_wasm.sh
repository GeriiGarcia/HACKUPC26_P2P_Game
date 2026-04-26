#!/bin/bash

# Script para lanzar el LOBBY completo en WASM
set -e

PORT=8003

echo "🧹 Limpiando procesos previos en el puerto $PORT..."
lsof -t -i:$PORT | xargs kill -9 2>/dev/null || true

echo "📦 Preparando archivos del LOBBY para WASM..."
rm -rf wasm_build && mkdir -p wasm_build

# Copiar el lobby como main.py
cp main.py wasm_build/main.py

# Copiar todos los módulos de juegos y utilidades
cp *.py wasm_build/
# Evitar que main.py se pise a sí mismo de forma circular (aunque cp ya lo hace)
cp wasm_bridge.js wasm_build/

# Copiar assets si existen
if [ -d "assets" ]; then
    cp -r assets wasm_build/
fi

# Eliminar el index.html de la raíz si se coló en wasm_build
rm -f wasm_build/index.html
touch wasm_build/favicon.png

echo "🔨 Compilando LOBBY con Pygbag..."
./venv/bin/python3 -m pygbag --build ./wasm_build

echo "💉 Inyectando Bridge P2P en index.html..."
sed -i 's|</head>|    <script src="https://cdnjs.cloudflare.com/ajax/libs/simple-peer/9.11.1/simplepeer.min.js"></script>\n    <script src="wasm_bridge.js"></script>\n    <script>console.log("!!! LOBBY CARGADO - PORT 8003 !!!");</script>\n</head>|' wasm_build/build/web/index.html
sed -i 's|//browserfs.min.js|/browserfs.min.js|g' wasm_build/build/web/index.html

cp wasm_bridge.js wasm_build/build/web/

echo "🚀 Lanzando servidor en puerto $PORT..."
echo "🔗 Accede via IP local: http://$(hostname -I | awk '{print $1}'):$PORT"
npx http-server ./wasm_build/build/web --cors -p $PORT -c-1
