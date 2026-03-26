import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const rootDir = path.resolve(__dirname, '..')
const backendDir = path.join(rootDir, 'backend')

const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm'
const withBot = process.argv.includes('--with-bot')
const showHelp = process.argv.includes('--help') || process.argv.includes('-h')

if (showHelp) {
  console.log(`Usage:
  npm run dev:all       Start frontend + backend API
  npm run dev:all:bot   Start frontend + backend API + Telegram bot

Environment:
  BACKEND_PYTHON=/path/to/python   Force a specific Python interpreter

The script prefers backend/.venv if it exists.`)
  process.exit(0)
}

function resolveBackendPython() {
  const envPython = process.env.BACKEND_PYTHON
  if (envPython) {
    return envPython
  }

  const candidates = [
    path.join(backendDir, '.venv', 'Scripts', 'python.exe'),
    path.join(backendDir, '.venv', 'bin', 'python'),
  ]

  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate
    }
  }

  return process.platform === 'win32' ? 'python' : 'python3'
}

function spawnProcess(name, command, args, cwd) {
  console.log(`[start] ${name}: ${command} ${args.join(' ')}`)

  const isWindowsCmd =
    process.platform === 'win32' && (command.endsWith('.cmd') || command.endsWith('.bat'))

  const spawnCommand = isWindowsCmd ? 'cmd.exe' : command
  const spawnArgs = isWindowsCmd ? ['/d', '/s', '/c', command, ...args] : args

  const child = spawn(spawnCommand, spawnArgs, {
    cwd,
    stdio: 'inherit',
    env: process.env,
    detached: process.platform !== 'win32',
  })

  child.on('error', (error) => {
    console.error(`[error] ${name}: ${error.message}`)
  })

  return { name, child }
}

function stopProcess(entry) {
  const { child } = entry
  if (!child.pid) {
    return Promise.resolve()
  }

  if (process.platform === 'win32') {
    return new Promise((resolve) => {
      const killer = spawn('taskkill', ['/pid', String(child.pid), '/t', '/f'], {
        stdio: 'ignore',
      })
      killer.on('exit', () => resolve())
      killer.on('error', () => resolve())
    })
  }

  return new Promise((resolve) => {
    try {
      process.kill(-child.pid, 'SIGTERM')
    } catch {
      try {
        child.kill('SIGTERM')
      } catch {
        // ignore
      }
    }
    setTimeout(resolve, 200)
  })
}

const pythonCommand = resolveBackendPython()
const entries = [
  spawnProcess(
    'backend-api',
    pythonCommand,
    ['-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'],
    backendDir,
  ),
  spawnProcess('frontend', npmCommand, ['run', 'dev'], rootDir),
]

if (withBot) {
  entries.push(spawnProcess('telegram-bot', pythonCommand, ['run_bot.py'], backendDir))
}

let shuttingDown = false

async function shutdown(exitCode = 0) {
  if (shuttingDown) {
    return
  }

  shuttingDown = true
  console.log('\n[stop] shutting down dev processes...')
  await Promise.all(entries.map(stopProcess))
  process.exit(exitCode)
}

for (const entry of entries) {
  entry.child.on('exit', (code, signal) => {
    if (shuttingDown) {
      return
    }

    const exitCode = code ?? (signal ? 1 : 0)
    console.log(`[exit] ${entry.name}: code=${code ?? 'null'} signal=${signal ?? 'null'}`)
    shutdown(exitCode)
  })
}

process.on('SIGINT', () => {
  shutdown(0)
})

process.on('SIGTERM', () => {
  shutdown(0)
})

console.log('[ready] dev stack is starting...')
console.log('[info] frontend: http://127.0.0.1:4173')
console.log('[info] backend:  http://127.0.0.1:8000')
if (withBot) {
  console.log('[info] telegram bot: enabled')
}
