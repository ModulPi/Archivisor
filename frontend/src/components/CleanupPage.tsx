import React, { useEffect, useState } from 'react'
import { queryDuplicates, queryTempFiles } from '../services/backend'
import { NavigateTarget, PageKey } from '../App'

interface Props { backendOnline: boolean; navigateTo: (t: PageKey | NavigateTarget) => void }

const formatSize = (bytes: number): string => {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024).toFixed(0)} KB`
}

const CleanupPage: React.FC<Props> = ({ backendOnline, navigateTo }) => {
  const [duplicates, setDuplicates] = useState<any[]>([])
  const [tempFiles, setTempFiles] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'duplicates' | 'temp'>('duplicates')

  useEffect(() => {
    if (!backendOnline) return
    setLoading(true)
    Promise.all([queryDuplicates(), queryTempFiles()])
      .then(([d, t]) => {
        setDuplicates(d.duplicates || [])
        setTempFiles(t.temp_files || [])
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [backendOnline])

  if (!backendOnline) return <div className="page-offline">引擎未连接。</div>

  const dupWaste = duplicates.reduce((sum, d) => sum + d.size * (d.count - 1), 0)
  const tempWaste = tempFiles.reduce((sum: number, f: any) => sum + f.size, 0)

  return (
    <div className="page">
      <h2 className="page-title">空间清理</h2>
      <p className="page-desc">发现可释放的空间。请手动确认后删除。</p>

      <div className="tab-bar">
        <button className={`tab-btn ${tab === 'duplicates' ? 'active' : ''}`} onClick={() => setTab('duplicates')}>
          重复文件 ({duplicates.length} 组, 可释放 {formatSize(dupWaste)})
        </button>
        <button className={`tab-btn ${tab === 'temp' ? 'active' : ''}`} onClick={() => setTab('temp')}>
          临时文件 ({tempFiles.length} 个, {formatSize(tempWaste)})
        </button>
      </div>

      {loading && <div className="progress-info"><div className="spinner" /><span>分析中...</span></div>}

      {!loading && tab === 'duplicates' && (
        duplicates.length === 0 ? (
          <div className="msg-empty-action">
            <p>未发现重复文件，请先扫描目录建立索引。</p>
            <button className="btn-primary" onClick={() => navigateTo('scan')}>去扫描</button>
          </div>
        ) : (
          <div className="dup-list">
            {duplicates.map((group, gi) => (
              <div key={gi} className="dup-group">
                <div className="dup-group-header">
                  <span>{group.count} 个相同文件</span>
                  <span>每个 {formatSize(group.size)}，可释放 {formatSize(group.size * (group.count - 1))}</span>
                </div>
                {group.files.map((f: any) => (
                  <div key={f.id} className="dup-file" title={f.path}>
                    <span>{f.name}</span>
                    <span className="dup-path">{f.path}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )
      )}

      {!loading && tab === 'temp' && (
        tempFiles.length === 0 ? (
          <div className="msg-empty-action">
            <p>未发现临时文件，请先扫描目录建立索引。</p>
            <button className="btn-primary" onClick={() => navigateTo('scan')}>去扫描</button>
          </div>
        ) : (
          <div className="file-list">
            {tempFiles.map((f: any) => (
              <div key={f.id} className="file-row" title={f.path}>
                <span className="col-name">{f.name}</span>
                <span className="col-size">{formatSize(f.size)}</span>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  )
}

export default CleanupPage
