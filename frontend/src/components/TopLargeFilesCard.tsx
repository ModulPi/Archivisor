import React from 'react'
import { TopLargeFile } from '../services/backend'

interface Props {
  files: TopLargeFile[]
}

const formatSize = (bytes: number): string => {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

const TopLargeFilesCard: React.FC<Props> = ({ files }) => {
  if (!files || files.length === 0) {
    return (
      <div className="card">
        <h3 className="card-title">大文件排行</h3>
        <p className="card-empty">暂无数据，请先扫描目录。</p>
      </div>
    )
  }

  return (
    <div className="card">
      <h3 className="card-title">大文件 Top {files.length}</h3>
      <div className="file-list">
        <div className="file-list-header">
          <span className="col-name">文件名</span>
          <span className="col-size">大小</span>
        </div>
        {files.map((file) => (
          <div key={file.id} className="file-row" title={file.path}>
            <span className="col-name">{file.name}</span>
            <span className="col-size">{formatSize(file.size)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default TopLargeFilesCard
