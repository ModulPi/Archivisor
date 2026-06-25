import React, { useEffect, useState } from 'react'
import Dashboard from './components/Dashboard'
import { ping } from './services/backend'

const App: React.FC = () => {
  const [backendOnline, setBackendOnline] = useState<boolean>(false)
  const [backendError, setBackendError] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(true)

  useEffect(() => {
    let cancelled = false

    if (window.archivisor) {
      window.archivisor.onBackendStatus((status) => {
        if (!cancelled) {
          setBackendOnline(status.connected)
          if (status.reason) {
            setBackendError(status.reason)
          }
        }
      })
    }

    ping()
      .then((res) => {
        if (!cancelled) {
          setBackendOnline(res.pong === true)
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBackendOnline(false)
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  if (loading) {
    return (
      <div className="app-loading">
        <div className="spinner" />
        <p>正在连接 Archivisor 引擎...</p>
      </div>
    )
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">Archivisor</h1>
        <div className="app-status">
          <span className={`status-dot ${backendOnline ? 'online' : 'offline'}`} />
          <span className="status-text">
            {backendOnline ? '引擎在线' : '引擎离线'}
          </span>
        </div>
      </header>

      {backendError && (
        <div className="app-error-banner">
          <strong>诊断:</strong> {backendError}
          <br />
          <small>请确认 Python 后端已启动（终端运行 python backend/main.py），然后刷新页面。</small>
        </div>
      )}

      <main className="app-main">
        <Dashboard backendOnline={backendOnline} />
      </main>
    </div>
  )
}

export default App
