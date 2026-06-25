import React from 'react'
import { DiskUsage } from '../services/backend'

interface Props {
  disk: DiskUsage
}

const formatGB = (gb: number): string => {
  if (gb >= 1000) return `${(gb / 1000).toFixed(2)} TB`
  return `${gb.toFixed(1)} GB`
}

const DiskUsageCard: React.FC<Props> = ({ disk }) => {
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
    </div>
  )
}

export default DiskUsageCard
