import React from 'react'

interface Props {
  info: { drives: string[] }
  backendOnline: boolean
}

const StatusBar: React.FC<Props> = ({ info, backendOnline }) => {
  return (
    <footer className="statusbar">
      <div className="statusbar-left">
        {info.drives.map((d, i) => (
          <span key={i} className="statusbar-drive">{d}</span>
        ))}
      </div>
      <div className="statusbar-right">
        <span>引擎: {backendOnline ? '在线' : '离线'}</span>
      </div>
    </footer>
  )
}

export default StatusBar
