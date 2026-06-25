import React from 'react'
import { TopLargeFile } from '../services/backend'
import { NavigateTarget, PageKey } from '../App'

interface Props {
  files: Record<string, TopLargeFile[]>
  navigateTo: (t: PageKey | NavigateTarget) => void
}

const formatSize = (bytes: number): string => {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024).toFixed(0)} KB`
}

const TopLargeFilesCard: React.FC<Props> = ({ files, navigateTo }) => {
  const drives = Object.keys(files)
  const hasAny = drives.some((d) => files[d].length > 0)

  if (!hasAny) {
    return (
      <div className="card">
        <h3 className="card-title">大文件排行</h3>
        <p className="card-empty">暂无数据，请先扫描目录。</p>
      </div>
    )
  }

  return (
    <div className="card">
      <h3 className="card-title">大文件排行</h3>
      {drives.map((drive) => {
        const list = files[drive]
        if (list.length === 0) return null
        return (
          <div key={drive} className="drive-section">
            <h4 className="drive-section-title">{drive} 盘</h4>
            <div className="file-list">
              <div className="file-list-header">
                <span className="col-name">文件名</span>
                <span className="col-size">大小</span>
                <span className="col-action"></span>
              </div>
              {list.map((file) => (
                <div key={file.id} className="file-row" title={file.path}>
                  <span className="col-name">{file.name}</span>
                  <span className="col-size">{formatSize(file.size)}</span>
                  <span className="col-action">
                    <button
                      className="btn-mini"
                      onClick={() => navigateTo({ page: 'migrate', params: { sourcePath: file.path } })}
                    >
                      迁移
                    </button>
                  </span>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default TopLargeFilesCard
