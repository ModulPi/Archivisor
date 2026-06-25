import React from 'react'
import { UnmigratedSummary } from '../services/backend'

interface Props {
  data: UnmigratedSummary
}

const formatSize = (bytes: number): string => {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

const UnmigratedCard: React.FC<Props> = ({ data }) => {
  if (!data) {
    return (
      <div className="card">
        <h3 className="card-title">未迁移文件</h3>
        <p className="card-empty">暂无数据</p>
      </div>
    )
  }

  return (
    <div className="card">
      <h3 className="card-title">未迁移文件</h3>
      <div className="unmigrated-summary">
        <div className="summary-row">
          <span className="summary-label">文件总数</span>
          <span className="summary-value">{data.file_count.toLocaleString()}</span>
        </div>
        <div className="summary-row">
          <span className="summary-label">总大小</span>
          <span className="summary-value">{formatSize(data.total_size)}</span>
        </div>
      </div>

      {data.by_extension && data.by_extension.length > 0 && (
        <div className="ext-breakdown">
          <h4>按类型分布</h4>
          {data.by_extension.map((ext) => (
            <div key={ext.extension} className="ext-row">
              <span className="ext-name">.{ext.extension}</span>
              <span className="ext-count">{ext.count.toLocaleString()} 个</span>
              <span className="ext-size">{formatSize(ext.total_size)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default UnmigratedCard
