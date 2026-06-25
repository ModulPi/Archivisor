import React, { useEffect, useState } from 'react'
import { queryMigrationHistory, rollbackMigration } from '../services/backend'

interface Props {
  backendOnline: boolean
}

interface HistoryItem {
  id: number
  source_path: string
  target_path: string
  status: string
  file_count: number
  total_size: number
  created_at: number
  committed_at: number | null
}

const RollbackPage: React.FC<Props> = ({ backendOnline }) => {
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [rollingBack, setRollingBack] = useState<number | null>(null)
  const [confirmId, setConfirmId] = useState<number | null>(null)

  const loadHistory = async () => {
    setLoading(true)
    try {
      const resp: any = await queryMigrationHistory()
      setHistory(resp.history || [])
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (backendOnline) loadHistory()
  }, [backendOnline])

  const handleRollback = async (id: number) => {
    setRollingBack(id)
    setError('')
    try {
      await rollbackMigration(id)
      await loadHistory()
    } catch (e: any) {
      setError(e.message || '回滚失败')
    } finally {
      setRollingBack(null)
      setConfirmId(null)
    }
  }

  if (!backendOnline) {
    return <div className="page-offline">引擎未连接，无法查看迁移历史。</div>
  }

  const statusLabel = (s: string) => {
    switch (s) {
      case 'committed': return { text: '已提交', cls: 'tag-green' }
      case 'rolled_back': return { text: '已回滚', cls: 'tag-gray' }
      case 'verified': return { text: '已校验', cls: 'tag-blue' }
      default: return { text: s, cls: 'tag-gray' }
    }
  }

  return (
    <div className="page">
      <div className="dashboard-header">
        <h2 className="page-title" style={{marginBottom:0}}>迁移历史</h2>
        <button onClick={loadHistory} disabled={loading} className="btn-refresh">
          {loading ? '刷新中...' : '刷新列表'}
        </button>
      </div>
      <p className="page-desc">查看历史迁移记录，必要时可一键回滚。</p>

      {loading && <div className="progress-info"><div className="spinner" /><span>加载中...</span></div>}
      {error && <div className="msg-error">{error}</div>}

      {!loading && history.length === 0 && (
        <div className="msg-empty">暂无迁移记录。请先执行迁移操作。</div>
      )}

      {history.length > 0 && (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th className="td-path-col">源目录</th>
                <th className="td-path-col">目标</th>
                <th className="td-num">文件数</th>
                <th className="td-status">状态</th>
                <th className="td-time">时间</th>
                <th className="td-action">操作</th>
              </tr>
            </thead>
            <tbody>
              {history.map((item) => {
                const st = statusLabel(item.status)
                return (
                  <tr key={item.id}>
                    <td className="td-path td-path-col" title={item.source_path}>{item.source_path}</td>
                    <td className="td-path td-path-col" title={item.target_path}>{item.target_path}</td>
                    <td className="td-num">{item.file_count}</td>
                    <td className="td-status"><span className={`tag ${st.cls}`}>{st.text}</span></td>
                    <td className="td-time">{item.created_at ? new Date(item.created_at * 1000).toLocaleString('zh-CN') : '-'}</td>
                    <td className="td-action">
                      {item.status === 'committed' && (
                        confirmId === item.id ? (
                          <span className="confirm-group">
                            <button className="btn-danger-sm" onClick={() => handleRollback(item.id)}>确认回滚</button>
                            <button className="btn-cancel-sm" onClick={() => setConfirmId(null)}>取消</button>
                          </span>
                        ) : (
                          <button
                            className="btn-warn-sm"
                            onClick={() => setConfirmId(item.id)}
                            disabled={rollingBack === item.id}
                          >
                            {rollingBack === item.id ? '回滚中...' : '回滚'}
                          </button>
                        )
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default RollbackPage
