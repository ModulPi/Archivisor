/**
 * Electron 主进程 —— spawn Python backend，管理 stdio JSON-RPC 通道。
 */
import { app, BrowserWindow, ipcMain } from 'electron'
import { ChildProcess, spawn } from 'child_process'
import path from 'path'
import fs from 'fs'

// ---------------------------------------------------------------------------
// Python Backend 管理
// ---------------------------------------------------------------------------

let backendProcess: ChildProcess | null = null
let pendingRequests = new Map<number, { resolve: Function; reject: Function }>()
let requestId = 0
let heartbeatTimer: NodeJS.Timeout | null = null

/** 启动 Python backend 进程 */
function startBackend(): void {
  // 开发模式：直接用 python 运行；生产模式：用 PyInstaller 打包的 exe
  const isDev = !app.isPackaged
  const backendDir = isDev
    ? path.join(__dirname, '..', '..', 'backend')
    : path.join(process.resourcesPath, 'backend')

  const pythonCmd = isDev ? 'python' : path.join(backendDir, 'backend.exe')
  const mainScript = isDev ? path.join(backendDir, 'main.py') : undefined

  const args = mainScript ? ['-u', mainScript] : []
  const cwd = isDev ? path.join(__dirname, '..', '..') : backendDir

  console.log(`[Archivisor] Starting backend: ${pythonCmd} ${args.join(' ')}`)
  console.log(`[Archivisor] CWD: ${cwd}`)

  backendProcess = spawn(pythonCmd, args, {
    cwd,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  })

  // stdout 缓冲区：可能包含多个 JSON 对象或半截数据
  let stdoutBuffer = ''

  backendProcess.stdout!.on('data', (chunk: Buffer) => {
    stdoutBuffer += chunk.toString('utf-8')
    // 按行拆分，每行一个完整 JSON
    const lines = stdoutBuffer.split('\n')
    // 最后一个可能不完整，保留在缓冲区
    stdoutBuffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      try {
        const msg = JSON.parse(trimmed)
        handleBackendMessage(msg)
      } catch {
        // 非 JSON 输出，忽略（调试日志等）
      }
    }
  })

  backendProcess.stderr!.on('data', (chunk: Buffer) => {
    const text = chunk.toString('utf-8').trim()
    if (text) {
      console.error(`[Python stderr] ${text}`)
    }
  })

  backendProcess.on('exit', (code, signal) => {
    console.log(`[Archivisor] Backend exited: code=${code} signal=${signal}`)
    backendProcess = null
    stopHeartbeatMonitor()

    // 通知所有 pending 请求失败
    for (const [id, { reject }] of pendingRequests) {
      reject(new Error(`Backend process exited (code=${code})`))
    }
    pendingRequests.clear()
  })
}

/** 处理来自 Python 的消息（响应或心跳） */
function handleBackendMessage(msg: any): void {
  if (msg.type === 'heartbeat') {
    // 心跳，仅在通信层面记录时间，不发送到渲染进程
    return
  }

  if (msg.id !== undefined && pendingRequests.has(msg.id)) {
    const { resolve, reject } = pendingRequests.get(msg.id)!
    pendingRequests.delete(msg.id)
    if (msg.error) {
      reject(new Error(`[${msg.error.code}] ${msg.error.message}`))
    } else {
      resolve(msg.result || {})
    }
  }
}

/** 心跳超时监控：若 15 秒无心跳，通知渲染进程 */
let lastHeartbeat = Date.now()

function startHeartbeatMonitor(win: BrowserWindow): void {
  lastHeartbeat = Date.now()
  heartbeatTimer = setInterval(() => {
    const elapsed = Date.now() - lastHeartbeat
    if (elapsed > 15000) {
      win.webContents.send('backend:status', {
        connected: false,
        reason: `Heartbeat timeout (${Math.round(elapsed / 1000)}s)`,
      })
    } else {
      win.webContents.send('backend:status', { connected: true })
    }
  }, 3000)
}

function stopHeartbeatMonitor(): void {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

/** 向 Python backend 发送 JSON-RPC 请求 */
function sendRpc(method: string, params: Record<string, any> = {}): Promise<any> {
  return new Promise((resolve, reject) => {
    if (!backendProcess || !backendProcess.stdin) {
      reject(new Error('Backend not running'))
      return
    }

    const id = ++requestId
    const payload = JSON.stringify({ id, method, params }) + '\n'

    pendingRequests.set(id, { resolve, reject })

    // 30s 超时
    const timeout = setTimeout(() => {
      if (pendingRequests.has(id)) {
        pendingRequests.delete(id)
        reject(new Error(`Request timeout: ${method}`))
      }
    }, 30000)

    // 包装 resolve/reject 以清除超时
    const originalResolve = resolve
    const originalReject = reject
    pendingRequests.set(id, {
      resolve: (result: any) => {
        clearTimeout(timeout)
        originalResolve(result)
      },
      reject: (err: any) => {
        clearTimeout(timeout)
        originalReject(err)
      },
    })

    backendProcess.stdin.write(payload)
  })
}

// ---------------------------------------------------------------------------
// IPC Handlers（渲染进程通过 ipcRenderer.invoke 调用）
// ---------------------------------------------------------------------------

function registerIpcHandlers(): void {
  ipcMain.handle('rpc:call', async (_event, method: string, params: Record<string, any>) => {
    try {
      const result = await sendRpc(method, params)
      return { ok: true, data: result }
    } catch (err: any) {
      return { ok: false, error: err.message }
    }
  })

  ipcMain.handle('backend:restart', async () => {
    stopBackend()
    startBackend()
    return { ok: true }
  })

  ipcMain.handle('backend:status', async () => {
    return {
      running: backendProcess !== null && backendProcess.exitCode === null,
      pid: backendProcess?.pid ?? null,
    }
  })
}

// ---------------------------------------------------------------------------
// 窗口管理
// ---------------------------------------------------------------------------

let mainWindow: BrowserWindow | null = null

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: 'Archivisor',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // 开发模式加载 Vite dev server，生产模式加载构建产物
  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL)
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// ---------------------------------------------------------------------------
// 生命周期
// ---------------------------------------------------------------------------

function stopBackend(): void {
  if (backendProcess) {
    backendProcess.kill()
    backendProcess = null
  }
  stopHeartbeatMonitor()
}

app.whenReady().then(() => {
  registerIpcHandlers()
  startBackend()
  createWindow()

  if (mainWindow) {
    startHeartbeatMonitor(mainWindow)
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  stopBackend()
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  stopBackend()
})
