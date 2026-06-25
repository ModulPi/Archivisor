import React from 'react'
import { DiskUsage, TopLargeFile } from '../services/backend'
import { NavigateTarget, PageKey } from '../App'

interface Props {
  disk: DiskUsage
  largeFiles: TopLargeFile[]
  navigateTo: (t: PageKey | NavigateTarget) => void
}

const formatGB = (gb: number): string => {
  if (gb >= 1000) return `${(gb / 1000).toFixed(2)} TB`
  return `${gb.toFixed(1)} GB`
}

const formatSize = (bytes: number): string => {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024).toFixed(0)} KB`
}

const DiskUsageCard: React.FC<Props> = ({ disk, largeFiles, navigateTo }) => {
  const pct = disk.total_gb > 0 ? Math.round((disk.used_gb / disk.total_gb) * 100) : 0

  return (
    <div className="card disk-card">
      <h3 className="card-title">{disk.drive} {disk.mountpoint}</h3>

      <div className="disk-bar-bg" style={{ marginBottom: 10 }}>
        <div className="disk-bar-fill" style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>

      <div className="disk-detail-grid">
        <div className="disk-detail-item">
          <span className="disk-detail-value">{formatGB(disk.total_gb)}</span>
          <span className="disk-detail-label">总容量</span>
        </div>
        <div className="disk-detail-item">
          <span className="disk-detail-value" style={{ color: 'var(--accent)' }}>{formatGB(disk.used_gb)}</span>
          <span className="disk-detail-label">已使用</span>
        </div>
        <div className="disk-detail-item">
          <span className="disk-detail-value" style={{ color: 'var(--accent-green)' }}>{formatGB(disk.free_gb)}</span>
          <span className="disk-detail-label">可用</span>
        </div>
        <div className="disk-detail-item">
          <span className="disk-detail-value" style={{ color: 'var(--accent-yellow)' }}>{formatGB(disk.indexed_gb)}</span>
          <span className="disk-detail-label">已索引</span>
        </div>
      </div>

      {/* 该盘的大文件列表 */}
      {largeFiles.length > 0 && (
        <div className="inline-file-list">
          <h4 className="inline-file-title">大文件 Top 10</h4>
          {largeFiles.slice(0, 10).map((file) => (
            <div key={file.id} className="file-row" title={file.path}>
              <span className="col-name">{file.name}</span>
              <span className="col-size">{formatSize(file.size)}</span>
              <span className="col-action">
                <button className="btn-mini" onClick={() => navigateTo({ page: 'migrate', params: { sourcePath: file.path } })}>
                  迁移
                </button>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default DiskUsageCard
