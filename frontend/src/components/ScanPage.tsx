import React, { useState } from 'react'
import { scanDirectory, ScanResult } from '../services/backend'

interface Props { backendOnline: boolean }

const KNOWN_FOLDERS = ['桌面', '下载', '文档', '图片', '音乐', '视频']
const FOLDER_MAP: Record<string, string> = {
  '桌面': 'Desktop', '下载': 'Downloads', '文档': 'Documents',
  '图片': 'Pictures', '音乐': 'Music', '视频': 'Videos',
}

const ScanPage: React.FC<Props> = ({ backendOnline }) => {
  const [selected, setSelected] = useState<string[]>(KNOWN_FOLDERS)
  const [customPath, setCustomPath] = useState('')
  const [scanning, setScanning] = useState(false)
  const [result, setResult] = useState<ScanResult | null>(null)
  const [error, setError] = useState('')

  const toggleFolder = (name: string) => {
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((f) => f !== name) : [...prev, name]
    )
  }

  const handleScan = async () => {
    setScanning(true); setError(''); setResult(null)
    try {
      const results: ScanResult[] = []
      for (const name of selected) {
        const r = await scanDirectory(FOLDER_MAP[name])
        results.push(r)
      }
      if (customPath.trim()) {
        const r = await scanDirectory(customPath.trim())
        results.push(r)
      }
      const total: ScanResult = {
        type: 'done',
        total_files: results.reduce((a, r) => a + r.total_files, 0),
        total_size: results.reduce((a, r) => a + r.total_size, 0),
        duration_sec: results.reduce((a, r) => a + r.duration_sec, 0),
      }
      setResult(total)
    } catch (e: any) {
      setError(e.message || '扫描失败')
    } finally {
      setScanning(false)
    }
  }

  if (!backendOnline) return <div className="page-offline">引擎未连接，无法执行扫描。</div>

  return (
    <div className="page">
      <h2 className="page-title">扫描目录</h2>
      <p className="page-desc">选择要扫描的文件夹，建立文件索引。</p>

      <div className="form-section">
        <h3>已知目录</h3>
        <div className="checkbox-group">
          {KNOWN_FOLDERS.map((name) => (
            <label key={name} className="checkbox-label">
              <input type="checkbox" checked={selected.includes(name)} onChange={() => toggleFolder(name)} disabled={scanning} />
              {name}
            </label>
          ))}
        </div>
      </div>

      <div className="form-section">
        <h3>自定义路径</h3>
        <input type="text" className="input-text" placeholder="例如: D:\我的资料" value={customPath} onChange={(e) => setCustomPath(e.target.value)} disabled={scanning} />
      </div>

      <button className="btn-primary" onClick={handleScan} disabled={scanning || (selected.length === 0 && !customPath.trim())}>
        {scanning ? '扫描中...' : '开始扫描'}
      </button>

      {scanning && <div className="progress-info"><div className="spinner" /><span>正在扫描，请稍候...</span></div>}
      {error && <div className="msg-error">{error}</div>}

      {result && (
        <div className="result-card">
          <h3>扫描完成</h3>
          <div className="result-grid">
            <div className="result-item"><span className="result-value">{result.total_files.toLocaleString()}</span><span className="result-label">文件数</span></div>
            <div className="result-item"><span className="result-value">{formatSize(result.total_size)}</span><span className="result-label">总大小</span></div>
            <div className="result-item"><span className="result-value">{result.duration_sec.toFixed(2)}s</span><span className="result-label">耗时</span></div>
          </div>
        </div>
      )}
    </div>
  )
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024).toFixed(0)} KB`
}

export default ScanPage
