/**
 * Backend JSON-RPC 调用封装。
 * 所有与 Python 引擎的通信都通过此模块。
 */

// ---------------------------------------------------------------------------
// 类型定义（与 Python schemas.py 对应）
// ---------------------------------------------------------------------------

export interface ScanResult {
  type: string
  total_files: number
  total_size: number
  duration_sec: number
}

export interface DiskUsage {
  drive: string
  mountpoint: string
  total_gb: number
  used_gb: number
  free_gb: number
  indexed_gb: number
}

export interface TopLargeFile {
  id: number
  name: string
  path: string
  size: number
}

export interface UnmigratedSummary {
  file_count: number
  total_size: number
  by_extension: Array<{ extension: string; count: number; total_size: number }>
}

export interface DashboardData {
  disks: DiskUsage[]
  top_large_files: Record<string, TopLargeFile[]>  // { "C:": [...], "D:": [...] }
  unmigrated: UnmigratedSummary
}

export interface MigrationPlan {
  plan_id: number
  source: string
  target: string
  file_count: number
  total_size: number
  status: string
}

// ---------------------------------------------------------------------------
// API 调用函数
// ---------------------------------------------------------------------------

function rpc<T = any>(method: string, params: Record<string, any> = {}): Promise<T> {
  if (!window.archivisor) {
    return Promise.reject(new Error('Archivisor API not available (not running in Electron?)'))
  }
  return window.archivisor.rpc(method, params).then((result) => {
    if (!result.ok) {
      throw new Error(result.error || 'Unknown RPC error')
    }
    return result.data as T
  })
}

/** 扫描指定目录 */
export function scanDirectory(rootPath: string): Promise<ScanResult> {
  return rpc<ScanResult>('scan', { root_path: rootPath })
}

/** 查询看板数据 */
export function queryDashboard(): Promise<DashboardData> {
  return rpc<DashboardData>('query', { type: 'dashboard' })
}

/** 查询磁盘占用 */
export function queryDiskUsage(): Promise<{ disks: DiskUsage[] }> {
  return rpc('query', { type: 'disk_usage' })
}

/** 查询大文件 Top N */
export function queryTopLarge(limit: number = 20): Promise<{ files: Record<string, TopLargeFile[]> }> {
  return rpc('query', { type: 'top_large', limit })
}

/** 查询未迁移文件 */
export function queryUnmigrated(): Promise<{ unmigrated: UnmigratedSummary }> {
  return rpc('query', { type: 'unmigrated' })
}

/** 心跳探测 */
export function ping(): Promise<{ pong: boolean; time: number }> {
  return rpc('ping')
}

// ---------------------------------------------------------------------------
// 迁移相关
// ---------------------------------------------------------------------------

/** 创建迁移计划 */
export function createMigrationPlan(
  source: string,
  target: string,
  filters?: string[],
): Promise<{ plan: MigrationPlan }> {
  return rpc('migrate', { action: 'create_plan', source, target, filters })
}

/** 执行迁移 */
export function executeMigration(planId: number): Promise<{ plan_id: number; execute_ok: boolean }> {
  return rpc('migrate', { action: 'execute', plan_id: planId })
}

/** 提交迁移 */
export function commitMigration(planId: number): Promise<{ plan_id: number; commit_ok: boolean }> {
  return rpc('migrate', { action: 'commit', plan_id: planId })
}

/** 查询迁移状态 */
export function getMigrationStatus(planId: number): Promise<{ plan: any }> {
  return rpc('migrate', { action: 'status', plan_id: planId })
}

/** 回滚迁移 */
export function rollbackMigration(planId: number): Promise<any> {
  return rpc('rollback', { plan_id: planId })
}
