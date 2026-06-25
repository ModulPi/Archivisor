import React from 'react'
import { DiskUsage } from '../services/backend'

interface Props {
  disks: DiskUsage[]
}

const formatGB = (gb: number): string => {
  if (gb >= 1000) return `${(gb / 1000).toFixed(2)} TB`
  return `${gb.toFixed(1)} GB`
}

const usagePercent = (used: number, total: number): number => {
  if (total === 0) return 0
  return Math.round((used / total) * 100)
}

const DiskUsageCard: React.FC<Props> = ({ disks }) => {
  if (!disks || disks.length === 0) {
    return (
      <div className="card">
        <h3 className="card-title">磁盘占用</h3>
        <p className="card-empty">暂无磁盘数据</p>
      </div>
    )
  }

  return (
    <div className="card">
      <h3 className="card-title">磁盘占用</h3>
      <div className="disk-list">
        {disks.map((disk) => {
          const pct = usagePercent(disk.used_gb, disk.total_gb)
          return (
            <div key={disk.mountpoint} className="disk-item">
              <div className="disk-info">
                <span className="disk-drive">{disk.drive}</span>
                <span className="disk-path">{disk.mountpoint}</span>
              </div>
              <div className="disk-bar-bg">
                <div
                  className="disk-bar-fill"
                  style={{ width: `${Math.min(pct, 100)}%` }}
                />
              </div>
              <div className="disk-stats">
                <span>
                  已用 {formatGB(disk.used_gb)} / {formatGB(disk.total_gb)}
                </span>
                <span className="disk-user-data">
                  用户数据 {formatGB(disk.user_data_gb)}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default DiskUsageCard
