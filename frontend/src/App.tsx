import React, { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import ScanPage from './components/ScanPage'
import MigratePage from './components/MigratePage'
import RollbackPage from './components/RollbackPage'
import CleanupPage from './components/CleanupPage'
import { ping, queryDiskUsage, searchFiles } from './services/backend'

export type PageKey = 'dashboard' | 'scan' | 'migrate' | 'rollback' | 'cleanup'

export interface NavigateTarget {
  page: PageKey
  params?: Record<string, any>
}

const App: React.FC = () => {
  const [page, setPage] = useState<PageKey>('dashboard')
  const [pageParams, setPageParams] = useState<Record<string, any>>({})
  const [backendOnline, setBackendOnline] = useState(false)
  const [backendError, setBackendError] = useState('')
  const [loading, setLoading] = useState(true)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [showSearch, setShowSearch] = useState(false)
  const [spaceWarning, setSpaceWarning] = useState('')

  const navigateTo = (target: PageKey | NavigateTarget) => {
    if (typeof target === 'string') {
      setPage(target); setPageParams({})
    } else {
      setPage(target.page); setPageParams(target.params || {})
    }
  }

  // 启动
  useEffect(() => {
    let cancelled = false
    if (window.archivisor) {
      window.archivisor.onBackendStatus((status) => {
        if (!cancelled) { setBackendOnline(status.connected); if (status.reason) setBackendError(status.reason) }
      })
    }
    ping().then((res) => { if (!cancelled) { setBackendOnline(res.pong === true); setLoading(false) } })
         .catch(() => { if (!cancelled) { setBackendOnline(false); setLoading(false) } })
    return () => { cancelled = true }
  }, [])

  // C 盘空间轮询
  useEffect(() => {
    if (!backendOnline) return
    const check = async () => {
      try {
        const r = await queryDiskUsage()
        const cdisk = r.disks.find((d: any) => d.mountpoint === 'C:')
        if (cdisk && cdisk.free_gb < 10) {
          setSpaceWarning(`C盘仅剩 ${cdisk.free_gb.toFixed(1)} GB，建议迁移文件释放空间`)
        } else {
          setSpaceWarning('')
        }
      } catch {}
    }
    check()
    const timer = setInterval(check, 30000)
    return () => clearInterval(timer)
  }, [backendOnline])

  // 搜索
  const handleSearch = async (kw: string) => {
    setSearchKeyword(kw)
    if (kw.trim().length < 1) { setSearchResults([]); setShowSearch(false); return }
    try {
      const r = await searchFiles(kw)
      setSearchResults(r.results || [])
      setShowSearch(true)
    } catch { setSearchResults([]) }
  }

  // 右键打开文件夹
  const handleContextMenu = (filePath: string) => {
    if (window.archivisor) {
      window.archivisor.rpc('ping', {}).then(() => {}) // ensure connected
      // Electron shell via IPC
      try {
        const { shell } = require('electron')
        shell.showItemInFolder(filePath)
      } catch {
        // Fallback: send to main process
        window.archivisor.rpc('open_folder', { path: filePath }).catch(() => {})
      }
    }
  }

  if (loading) {
    return (
      <div className="app-loading">
        <div className="spinner" />
        <p>正在连接 Archivisor 引擎...</p>
      </div>
    )
  }

  const renderPage = () => {
    switch (page) {
      case 'dashboard': return <Dashboard backendOnline={backendOnline} navigateTo={navigateTo} />
      case 'scan':      return <ScanPage backendOnline={backendOnline} navigateTo={navigateTo} />
      case 'migrate':   return <MigratePage backendOnline={backendOnline} initialParams={pageParams} />
      case 'rollback':  return <RollbackPage backendOnline={backendOnline} />
      case 'cleanup':   return <CleanupPage backendOnline={backendOnline} />
    }
  }

  return (
    <div className="app-layout">
      <Sidebar current={page} onNavigate={(p) => navigateTo(p)} backendOnline={backendOnline} />

      <div className="app-body">
        <header className="app-header">
          <h1 className="app-title">Archivisor</h1>

          {/* 搜索框 */}
          <div className="header-search">
            <input
              type="text"
              className="search-input"
              placeholder="搜索文件名..."
              value={searchKeyword}
              onChange={(e) => handleSearch(e.target.value)}
            />
            {showSearch && searchResults.length > 0 && (
              <div className="search-dropdown">
                {searchResults.slice(0, 8).map((f: any) => (
                  <div key={f.id} className="search-item" title={f.path}>
                    <span>{f.name}</span>
                    <span className="search-item-size">{formatSize(f.size)}</span>
                  </div>
                ))}
                {searchResults.length > 8 && (
                  <div className="search-more">还有 {searchResults.length - 8} 条结果...</div>
                )}
              </div>
            )}
          </div>

          <div className="app-status">
            <span className={`status-dot ${backendOnline ? 'online' : 'offline'}`} />
            <span className="status-text">{backendOnline ? '在线' : '离线'}</span>
          </div>
        </header>

        {/* 空间预警 */}
        {spaceWarning && (
          <div className="space-warning">
            <span>{spaceWarning}</span>
            <button className="btn-mini" onClick={() => navigateTo('migrate')}>去迁移</button>
          </div>
        )}

        {backendError && (
          <div className="app-error-banner">
            <strong>诊断:</strong> {backendError}
            <br /><small>请确认 Python 后端已启动（终端运行 python backend/main.py），然后刷新页面。</small>
          </div>
        )}

        <main className="app-main">{renderPage()}</main>
      </div>
    </div>
  )
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024).toFixed(0)} KB`
}

export default App
