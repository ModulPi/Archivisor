import React, { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import StatusBar from './components/StatusBar'
import Dashboard from './components/Dashboard'
import ScanPage from './components/ScanPage'
import MigratePage from './components/MigratePage'
import RollbackPage from './components/RollbackPage'
import { ping, queryDiskUsage } from './services/backend'

export type PageKey = 'dashboard' | 'scan' | 'migrate' | 'rollback'

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
  const [statusInfo, setStatusInfo] = useState<{ drives: string[] }>({ drives: [] })

  const navigateTo = (target: PageKey | NavigateTarget) => {
    if (typeof target === 'string') {
      setPage(target)
      setPageParams({})
    } else {
      setPage(target.page)
      setPageParams(target.params || {})
    }
  }

  useEffect(() => {
    let cancelled = false
    if (window.archivisor) {
      window.archivisor.onBackendStatus((status) => {
        if (!cancelled) {
          setBackendOnline(status.connected)
          if (status.reason) setBackendError(status.reason)
        }
      })
    }
    ping().then((res) => { if (!cancelled) { setBackendOnline(res.pong === true); setLoading(false) } })
         .catch(() => { if (!cancelled) { setBackendOnline(false); setLoading(false) } })
    queryDiskUsage().then((r) => {
      if (!cancelled) setStatusInfo({ drives: r.disks.map((d) => `${d.drive} ${d.free_gb.toFixed(0)}GB 可用`) })
    }).catch(() => {})
    return () => { cancelled = true }
  }, [])

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
    }
  }

  return (
    <div className="app-layout">
      <Sidebar current={page} onNavigate={(p) => navigateTo(p)} backendOnline={backendOnline} />
      <div className="app-body">
        <header className="app-header">
          <h1 className="app-title">Archivisor</h1>
          <div className="app-status">
            <span className={`status-dot ${backendOnline ? 'online' : 'offline'}`} />
            <span className="status-text">{backendOnline ? '引擎在线' : '引擎离线'}</span>
          </div>
        </header>
        {backendError && (
          <div className="app-error-banner">
            <strong>诊断:</strong> {backendError}
            <br /><small>请确认 Python 后端已启动（终端运行 python backend/main.py），然后刷新页面。</small>
          </div>
        )}
        <main className="app-main">{renderPage()}</main>
      </div>
      <StatusBar info={statusInfo} backendOnline={backendOnline} />
    </div>
  )
}

export default App
