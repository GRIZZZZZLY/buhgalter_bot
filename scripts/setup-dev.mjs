import { spawn, spawnSync } from 'node:child_process'
import { copyFileSync, existsSync, readFileSync, renameSync } from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const rootDir = path.resolve(__dirname, '..')
const backendDir = path.join(rootDir, 'backend')
const backendEnvExample = path.join(backendDir, '.env.example')
const backendEnv = path.join(backendDir, '.env')

const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm'
const showHelp = process.argv.includes('--help') || process.argv.includes('-h')
const DEFAULT_DATABASE_URL = 'sqlite:///./finance_bot.db'

if (showHelp) {
  console.log(`Usage:
  npm run setup:dev

What it does:
  1. Installs frontend dependencies
  2. Creates backend/.venv if missing
  3. Installs backend dependencies
  4. Copies backend/.env.example -> backend/.env if missing
  5. Runs alembic migrations
  6. Checks ffmpeg availability
  7. Warns if TELEGRAM_BOT_TOKEN is empty
  8. Backs up legacy local SQLite DB before migrations if needed
`)
  process.exit(0)
}

function readEnvValue(name) {
  if (!existsSync(backendEnv)) {
    return null
  }

  const content = readFileSync(backendEnv, 'utf-8')
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) {
      continue
    }
    if (trimmed.startsWith(`${name}=`)) {
      return trimmed.slice(name.length + 1).trim()
    }
  }

  return null
}

function resolveSystemPython() {
  const candidates = process.platform === 'win32'
    ? [
        { command: 'python', args: ['--version'] },
        { command: 'py', args: ['-3', '--version'], invokeArgs: ['-3'] },
        { command: 'py', args: ['--version'] },
      ]
    : [
        { command: 'python3', args: ['--version'] },
        { command: 'python', args: ['--version'] },
      ]

  for (const candidate of candidates) {
    const result = spawnSync(candidate.command, candidate.args, { stdio: 'ignore' })
    if (result.status === 0) {
      return {
        command: candidate.command,
        prefixArgs: candidate.invokeArgs ?? [],
      }
    }
  }

  throw new Error('Python не найден. Установи Python 3.12+ и добавь его в PATH.')
}

function resolveVenvPython() {
  const candidates = [
    path.join(backendDir, '.venv', 'Scripts', 'python.exe'),
    path.join(backendDir, '.venv', 'bin', 'python'),
  ]

  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate
    }
  }

  throw new Error('Не удалось найти Python внутри backend/.venv после создания окружения.')
}

function runCommand(name, command, args, cwd) {
  return new Promise((resolve, reject) => {
    console.log(`[step] ${name}`)
    console.log(`       ${command} ${args.join(' ')}`)

    const isWindowsCmd =
      process.platform === 'win32' && (command.endsWith('.cmd') || command.endsWith('.bat'))

    const spawnCommand = isWindowsCmd ? 'cmd.exe' : command
    const spawnArgs = isWindowsCmd ? ['/d', '/s', '/c', command, ...args] : args

    const child = spawn(spawnCommand, spawnArgs, {
      cwd,
      stdio: 'inherit',
      env: process.env,
    })

    child.on('error', (error) => reject(error))
    child.on('exit', (code) => {
      if (code === 0) {
        resolve()
        return
      }
      reject(new Error(`${name} завершился с кодом ${code ?? 'null'}`))
    })
  })
}

function isFfmpegAvailable() {
  const result = spawnSync('ffmpeg', ['-version'], { stdio: 'ignore' })
  return result.status === 0
}

function resolveDatabaseUrl() {
  return readEnvValue('DATABASE_URL') || DEFAULT_DATABASE_URL
}

function resolveSqlitePath(databaseUrl) {
  if (!databaseUrl.startsWith('sqlite:///')) {
    return null
  }

  const rawPath = databaseUrl.slice('sqlite:///'.length)
  if (!rawPath || rawPath === ':memory:') {
    return null
  }

  return path.isAbsolute(rawPath) ? rawPath : path.resolve(backendDir, rawPath)
}

function inspectSqliteState(pythonPath, sqlitePath) {
  const result = spawnSync(
    pythonPath,
    [
      '-c',
      'import json, sqlite3, sys\n' +
        'db = sqlite3.connect(sys.argv[1])\n' +
        'tables = [r[0] for r in db.execute("select name from sqlite_master where type=\'table\' order by name")]\n' +
        'versions = []\n' +
        'if "alembic_version" in tables:\n' +
        '    versions = [r[0] for r in db.execute("select version_num from alembic_version")]\n' +
        'print(json.dumps({"tables": tables, "versions": versions}))',
      sqlitePath,
    ],
    { encoding: 'utf-8' },
  )

  if (result.status !== 0) {
    return { tables: [], versions: [] }
  }

  try {
    return JSON.parse(result.stdout)
  } catch {
    return { tables: [], versions: [] }
  }
}

function backupLegacySqliteIfNeeded(pythonPath) {
  const databaseUrl = resolveDatabaseUrl()
  const sqlitePath = resolveSqlitePath(databaseUrl)

  if (!sqlitePath || !existsSync(sqlitePath)) {
    return
  }

  const { tables, versions } = inspectSqliteState(pythonPath, sqlitePath)
  const hasAlembic = tables.includes('alembic_version')
  const hasAlembicRows = Array.isArray(versions) && versions.length > 0
  const appTables = ['transactions', 'voice_logs', 'users', 'user_category_mappings', 'category_budgets']
  const hasAppTables = appTables.some((table) => tables.includes(table))

  if (!hasAppTables) {
    return
  }

  if (hasAlembic && hasAlembicRows) {
    return
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').replace('T', '_').slice(0, 19)
  const backupPath = sqlitePath.replace(/\.db$/i, '') + `.legacy-backup-${timestamp}.db`

  renameSync(sqlitePath, backupPath)
  console.log(`[info] legacy SQLite DB detected without valid alembic history`)
  console.log(`[info] backed up old DB to: ${backupPath}`)
  console.log(`[info] a fresh migrated SQLite DB will be created`)
}

async function main() {
  console.log('[setup] preparing local development environment...')

  await runCommand('install frontend dependencies', npmCommand, ['install'], rootDir)

  const systemPython = resolveSystemPython()
  const venvPythonPath = path.join(
    backendDir,
    '.venv',
    process.platform === 'win32' ? 'Scripts' : 'bin',
    process.platform === 'win32' ? 'python.exe' : 'python',
  )

  if (!existsSync(venvPythonPath)) {
    await runCommand(
      'create backend virtualenv',
      systemPython.command,
      [...systemPython.prefixArgs, '-m', 'venv', '.venv'],
      backendDir,
    )
  } else {
    console.log('[skip] backend/.venv already exists')
  }

  const backendPython = resolveVenvPython()

  await runCommand(
    'install backend dependencies',
    backendPython,
    ['-m', 'pip', 'install', '-e', '.[dev]'],
    backendDir,
  )

  if (!existsSync(backendEnv) && existsSync(backendEnvExample)) {
    copyFileSync(backendEnvExample, backendEnv)
    console.log('[info] created backend/.env from backend/.env.example')
  } else if (existsSync(backendEnv)) {
    console.log('[skip] backend/.env already exists')
  }

  backupLegacySqliteIfNeeded(backendPython)

  await runCommand(
    'run database migrations',
    backendPython,
    ['-m', 'alembic', 'upgrade', 'head'],
    backendDir,
  )

  if (isFfmpegAvailable()) {
    console.log('[ok] ffmpeg detected')
  } else {
    console.log('[warn] ffmpeg не найден в PATH')
    console.log('[warn] текстовый режим и WebApp будут работать, но голосовой ввод — нет')
  }

  const telegramBotToken = readEnvValue('TELEGRAM_BOT_TOKEN')
  if (!telegramBotToken) {
    console.log('[warn] TELEGRAM_BOT_TOKEN не заполнен в backend/.env')
    console.log('[warn] backend API и frontend запустятся, но Telegram-бот — нет')
  } else {
    console.log('[ok] TELEGRAM_BOT_TOKEN is configured')
  }

  console.log('\n[done] environment is ready')
  if (!telegramBotToken) {
    console.log('[next] заполни backend/.env (минимум TELEGRAM_BOT_TOKEN)')
  }
  console.log('[next] затем запусти: npm run dev:all:bot')
}

main().catch((error) => {
  console.error(`\n[failed] ${error.message}`)
  process.exit(1)
})
