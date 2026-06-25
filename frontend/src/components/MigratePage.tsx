import React, { useState } from 'react'
import {
  queryDiskUsage,
  createMigrationPlan,
  executeMigration,
  commitMigration,
  MigrationPlan,
} from '../services/backend'

interface Props {
  backendOnline: boolean
}

const KNOWN_FOLDERS = ['桌面', '下载', '文档', '图片', '音乐', '视频']
const FOLDER_MAP: Record<string, string> = {
  '桌面': 'Desktop', '下载': 'Downloads', '文档': 'Documents',
  '图片': 'Pictures', '音乐': 'Music', '视频': 'Videos',
}

const FILE_TYPES = [
  { label: '全部文件', value: '' },
  { label: '文档 (.doc .pdf .txt)', value: 'doc,pdf,txt,docx,xlsx' },
  { label: '图片 (.jpg .png .gif)', value: 'jpg,png,gif,bmp,webp' },
  { label: '视频 (.mp4 .mkv .avi)', value: 'mp4,mkv,avi,mov' },
  { label: '音频 (.mp3 .flac .wav)', value: 'mp3,flac,wav,aac' },
]

const MigratePage: React.FC<Props> = ({ backendOnline }) => {
  const [source, setSource] = useState('')
  const [targetDrive, setTargetDrive] = useState('')
  const [fileFilter, setFileFilter] = useState('')
  const [disks, setDisks] = useState<{ mountpoint: string; free_gb: number }[]>([])
  const [step, setStep] = useState<'config' | 'plan' | 'executing' | 'done'>('config')
  const [plan, setPlan] = useState<MigrationPlan | null>(null)
  const [planId, setPlanId] = useState(0)
  const [error, setError] = useState('')
  const [statusText, setStatusText] = useState('')

  // 加载可用磁盘
  React.useEffect(() => {
    queryDiskUsage().then((r) => {
      setDisks(r.disks.map((d) => ({ mountpoint: d.mountpoint, free_gb: d.free_gb })))
    }).catch(() => {})
  }, [])

  const handleCreatePlan = async () => {
    setError('')
    try {
      const filters = fileFilter ? fileFilter.split(',') : undefined
      const targetPath = targetDrive + '\\ArchivisorArchive'
      const resp = await createMigrationPlan(source, targetPath, filters)
      setPlan(resp.plan)
      setPlanId(resp.plan.plan_id)
      setStep('plan')
    } catch (e: any) {
      setError(e.message || '生成计划失败')
    }
  }

  const handleExecute = async () => {
    setError('')
    setStep('executing')
    setStatusText('正在复制文件...')
    try {
      const resp = await executeMigration(planId)
      if (!resp.execute_ok) throw new Error('校验未通过')
      setStatusText('正在创建联接...')
      const commitResp = await commitMigration(planId)
      if (!commitResp.commit_ok) throw new Error('提交失败')
      setStep('done')
    } catch (e: any) {
      setError(e.message || '迁移失败')
      setStep('plan')
    }
  }

  if (!backendOnline) {
    return <div className="page-offline">引擎未连接，无法执行迁移。</div>
  }

  return (
    <div className="page">
      <h2 className="page-title">文件迁移</h2>
      <p className="page-desc">将文件从 C 盘迁移到其他磁盘，原位置创建透明联接。</p>

      {step === 'config' && (
        <>
          <div className="form-section">
            <h3>源目录</h3>
            <select className="input-select" value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">-- 选择源目录 --</option>
              {KNOWN_FOLDERS.map((f) => (
                <option key={f} value={FOLDER_MAP[f]}>{f}</option>
              ))}
            </select>
          </div>

          <div className="form-section">
            <h3>目标盘</h3>
            <select className="input-select" value={targetDrive} onChange={(e) => setTargetDrive(e.target.value)}>
              <option value="">-- 选择目标盘 --</option>
              {disks.map((d) => (
                <option key={d.mountpoint} value={d.mountpoint}>{(d.mountpoint)} (可用 {d.free_gb.toFixed(0)} GB)</option>
              ))}
            </select>
          </div>

          <div className="form-section">
            <h3>文件类型</h3>
            <select className="input-select" value={fileFilter} onChange={(e) => setFileFilter(e.target.value)}>
              {FILE_TYPES.map((ft) => (
                <option key={ft.value} value={ft.value}>{ft.label}</option>
              ))}
            </select>
          </div>

          <button className="btn-primary" onClick={handleCreatePlan} disabled={!source || !targetDrive}>
            生成迁移计划
          </button>
        </>
      )}

      {step === 'plan' && plan && (
        <>
          <div className="result-card">
            <h3>迁移计划预览</h3>
            <div className="result-grid">
              <div className="result-item">
                <span className="result-value">{plan.file_count.toLocaleString()}</span>
                <span className="result-label">文件数</span>
              </div>
              <div className="result-item">
                <span className="result-value">{formatSize(plan.total_size)}</span>
                <span className="result-label">总大小</span>
              </div>
              <div className="result-item">
                <span className="result-value">{plan.status}</span>
                <span className="result-label">状态</span>
              </div>
            </div>
            <p className="plan-path">源: {plan.source}</p>
            <p className="plan-path">目标: {plan.target}</p>
          </div>

          <button className="btn-primary" onClick={handleExecute}>
            确认执行迁移
          </button>
          <button className="btn-secondary" onClick={() => setStep('config')}>
            取消
          </button>
        </>
      )}

      {step === 'executing' && (
        <div className="progress-info">
          <div className="spinner" />
          <span>{statusText}</span>
        </div>
      )}

      {step === 'done' && (
        <div className="result-card">
          <h3>迁移完成</h3>
          <p>文件已复制到目标盘，原位置已创建透明联接。应用程序不受影响。</p>
          <button className="btn-primary" onClick={() => { setStep('config'); setPlan(null) }}>
            继续迁移
          </button>
        </div>
      )}

      {error && <div className="msg-error">{error}</div>}
    </div>
  )
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024).toFixed(0)} KB`
}

export default MigratePage
