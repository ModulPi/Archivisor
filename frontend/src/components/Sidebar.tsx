import React from 'react'
import { PageKey } from '../App'

interface Props {
  current: PageKey
  onNavigate: (p: PageKey) => void
  backendOnline: boolean
}

const ITEMS: { key: PageKey; label: string; icon: string }[] = [
  { key: 'dashboard', label: '看板', icon: '📊' },
  { key: 'scan',      label: '扫描', icon: '🔍' },
  { key: 'migrate',   label: '迁移', icon: '📦' },
  { key: 'rollback',  label: '回滚', icon: '↩️ ' },
]

const Sidebar: React.FC<Props> = ({ current, onNavigate, backendOnline }) => {
  return (
    <nav className="sidebar">
      <div className="sidebar-brand">Archivisor</div>
      <ul className="sidebar-nav">
        {ITEMS.map((item) => (
          <li
            key={item.key}
            className={`sidebar-item ${current === item.key ? 'active' : ''}`}
            onClick={() => onNavigate(item.key)}
          >
            <span className="sidebar-icon">{item.icon}</span>
            <span className="sidebar-label">{item.label}</span>
          </li>
        ))}
      </ul>
      <div className="sidebar-footer">
        <span className={`status-dot ${backendOnline ? 'online' : 'offline'}`} />
        <span>{backendOnline ? '已连接' : '未连接'}</span>
      </div>
    </nav>
  )
}

export default Sidebar
