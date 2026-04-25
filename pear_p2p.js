const Hyperswarm = require('hyperswarm')
const readline = require('readline')

const topicHex = process.argv[2]

if (!topicHex || !/^[0-9a-fA-F]{64}$/.test(topicHex)) {
  console.error('Usage: node pear_p2p.js <64-char-sha256-hex-topic>')
  process.exit(1)
}

const topic = Buffer.from(topicHex, 'hex')
const swarm = new Hyperswarm()
const peers = new Set()

function safeJsonParse(line) {
  try {
    return JSON.parse(line)
  } catch {
    return null
  }
}

function broadcastJson(obj) {
  const line = JSON.stringify(obj) + '\n'
  for (const socket of peers) {
    try {
      socket.write(line)
    } catch (err) {
      console.error('Failed writing to peer:', err.message)
    }
  }
}

swarm.on('connection', (socket, info) => {
  peers.add(socket)
  console.error(`Peer connected (${info.client ? 'client' : 'server'}). Total: ${peers.size}`)

  let buffer = ''

  // Handle chunked data robustly: collect chunks, split by newline, keep remainder.
  socket.on('data', (chunk) => {
    buffer += chunk.toString('utf8')

    while (true) {
      const idx = buffer.indexOf('\n')
      if (idx === -1) break

      const line = buffer.slice(0, idx).trim()
      buffer = buffer.slice(idx + 1)

      if (!line) continue

      const msg = safeJsonParse(line)
      if (!msg) continue

      if ((msg.type === 'note_on' || msg.type === 'note_off') && Number.isInteger(msg.note)) {
        // IMPORTANT: stdout is JSON-only for Python parser compatibility.
        process.stdout.write(JSON.stringify(msg) + '\n')
      }
    }
  })

  socket.on('error', (err) => {
    console.error('Peer socket error:', err.message)
  })

  socket.on('close', () => {
    peers.delete(socket)
    console.error(`Peer disconnected. Total: ${peers.size}`)
  })
})

swarm.on('error', (err) => {
  console.error('Swarm error:', err.message)
})

swarm.join(topic, { client: true, server: true })
console.error(`Joined topic ${topicHex}`)

// Read local stdin as JSON lines robustly (handles chunking/newlines internally).
const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
})

rl.on('line', (line) => {
  const trimmed = line.trim()
  if (!trimmed) return

  const msg = safeJsonParse(trimmed)
  if (!msg) {
    console.error('Ignoring invalid stdin JSON line')
    return
  }

  if ((msg.type === 'note_on' || msg.type === 'note_off') && Number.isInteger(msg.note)) {
    broadcastJson(msg)
  }
})

function shutdown() {
  rl.close()
  for (const socket of peers) {
    try {
      socket.end()
      socket.destroy()
    } catch {
      // ignore
    }
  }

  swarm.destroy().finally(() => process.exit(0))
}

process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)
process.stdin.on('end', shutdown)
