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

/** 执行迁移（异步，需轮询 status 获取进度） */
export function executeMigration(planId: number): Promise<{ plan_id: number; started: boolean; message?: string }> {
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

/** 查询迁移历史 */
export function queryMigrationHistory(): Promise<{ history: any[] }> {
  return rpc('query', { type: 'migration_history' })
}

/** 搜索文件 (FTS5) */
export function searchFiles(keyword: string): Promise<{ results: Array<{ id: number; name: string; path: string; size: number }> }> {
  return rpc('query', { type: 'search', keyword })
}

/** 重复文件检测 */
export function queryDuplicates(drive?: string): Promise<{ duplicates: Array<{ size: number; count: number; files: Array<{ id: number; name: string; path: string; size: number }> }> }> {
  return rpc('query', { type: 'duplicates', drive: drive || '' })
}

/** 临时文件 */
export function queryTempFiles(drive?: string): Promise<{ temp_files: Array<{ id: number; name: string; path: string; size: number }> }> {
  return rpc('query', { type: 'temp_files', drive: drive || '' })
}

// ---------------------------------------------------------------------------
// Agent 相关（MVP2）
// ---------------------------------------------------------------------------

export interface AgentOperation {
  type: string
  path?: string | null
  extensions?: string[] | null
  time_range?: string[] | null
  target_root?: string | null
}

export interface AgentPlan {
  plan_id: string
  intent: string
  operations: AgentOperation[]
  source_path: string | null
  target_path: string | null
  estimated_file_count: number | null
  estimated_size: number | null
  requires_confirmation: boolean
  explanation: string
}

export interface AgentResponse {
  success: boolean
  intent: string | null
  confidence: number | null
  plan: AgentPlan | null
  clarification: string | null
  fallback_used: boolean
  error: string | null
}

export interface AgentUsage {
  daily_count: number
  daily_limit: number
  remaining: number
}

/** Agent: 自然语言处理 */
export function agentProcess(query: string): Promise<AgentResponse> {
  return rpc<AgentResponse>('agent.process', { query })
}

/** Agent: 查询/清空对话上下文 */
export function agentContext(action: 'get' | 'clear' = 'get'): Promise<{ context?: Array<{ query: string; intent: string; slots: Record<string, any> }>; ok?: boolean }> {
  return rpc('agent.context', { action })
}

/** Agent: 查询 API 用量 */
export function agentUsage(): Promise<AgentUsage> {
  return rpc<AgentUsage>('agent.usage')
}

/** Agent: 混合语义搜索 */
export function agentSearch(query: string, limit: number = 10): Promise<{
  results: Array<{
    id: number; name: string; path: string; size: number
    extension: string; match_source: string; rrf_score: number
  }>
  method: string
  bm25_hits: number
  semantic_hits: number
}> {
  return rpc('agent.search', { query, limit })
}

export interface Suggestion {
  type: string
  title: string
  detail: string
  severity: 'warning' | 'info'
  action: string
  action_label: string
}

/** Agent: 主动建议检查 */
export function agentSuggest(): Promise<{
  suggestions: Suggestion[]
  has_suggestions: boolean
  checked_at: number
}> {
  return rpc('agent.suggest')
}

export interface CleanupCandidate {
  id: number
  name: string
  path: string
  size: number
  size_mb: number
  extension: string
  reason: string
  safe_to_delete: boolean
}

/** Agent: 智能清理分析 */
export function agentCleanupAnalysis(limit: number = 20): Promise<{
  candidates: CleanupCandidate[]
  total_waste_gb: number
  candidate_count: number
  analysis: string
  fallback_used: boolean
}> {
  return rpc('agent.cleanup_analysis', { limit })
}
