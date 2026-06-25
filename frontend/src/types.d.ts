/** 类型声明：window.archivisor API */

interface RpcResult {
  ok: boolean
  data?: any
  error?: string
}

interface BackendStatus {
  connected: boolean
  reason?: string
}

interface ArchivisorAPI {
  rpc(method: string, params?: Record<string, any>): Promise<RpcResult>
  restartBackend(): Promise<RpcResult>
  getBackendStatus(): Promise<{ running: boolean; pid: number | null }>
  onBackendStatus(callback: (status: BackendStatus) => void): void
}

interface Window {
  archivisor: ArchivisorAPI
}
