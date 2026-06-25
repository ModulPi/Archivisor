import React, { useState, useEffect, useRef } from 'react'
import { queryDiskUsage, createMigrationPlan, executeMigration, commitMigration, getMigrationStatus, MigrationPlan } from '../services/backend'

interface Props {
  backendOnline: boolean
  initialParams: Record<string, any>
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

const MigratePage: React.FC<Props> = ({ backendOnline, initialParams }) => {
  const [source, setSource] = useState(initialParams?.source || '')
  const [sourcePath, setSourcePath] = useState(initialParams?.sourcePath || '')
  const [targetDrive, setTargetDrive] = useState('')
  const [fileFilter, setFileFilter] = useState('')
  const [disks, setDisks] = useState<{ mountpoint: string; free_gb: number }[]>([])
  const [step, setStep] = useState<'config' | 'plan' | 'executing' | 'reviewing' | 'done'>('config')
  const [plan, setPlan] = useState<MigrationPlan | null>(null)
  const [planId, setPlanId] = useState(0)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState({ copied: 0, total: 0 })
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    queryDiskUsage().then((r) => {
      setDisks(r.disks.map((d) => ({ mountpoint: d.mountpoint, free_gb: d.free_gb })))
    }).catch(() => {})
  }, [])

  // 从看板传入的源文件路径，提取源目录
  useEffect(() => {
    if (sourcePath && !source) {
      const parts = sourcePath.replace(/\\/g, '/').split('/')
      // 尝试匹配已知目录
      for (const [eng, chn] of Object.entries(FOLDER_MAP)) {
        if (sourcePath.toLowerCase().includes(eng.toLowerCase())) {
          setSource(eng)
          return
        }
      }
      // 默认用父目录
      if (parts.length >= 2) {
        setSource(parts.slice(0, -1).join('\\'))
      }
    }
  }, [sourcePath])

  const startPolling = (id: number) => {
    pollRef.current = setInterval(async () => {
      try {
        const resp: any = await getMigrationStatus(id)
        const p = resp.plan
        setProgress({ copied: p.files_copied || 0, total: p.file_count || 0 })
        if (p.status === 'verified' || p.status === 'pending') {
          if (pollRef.current) clearInterval(pollRef.current)
          if (p.status === 'verified') setStep('reviewing')
          if (p.status === 'pending') setError('迁移失败，请查看日志')
        }
      } catch {}
    }, 800)
  }

  const handleCreatePlan = async () => {
    setError('')
    try {
      const filters = fileFilter ? fileFilter.split(',') : undefined
      const targetPath = targetDrive + '\\ArchivisorArchive'
      const resp = await createMigrationPlan(source, targetPath, filters)
      setPlan(resp.plan); setPlanId(resp.plan.plan_id); setStep('plan')
    } catch (e: any) { setError(e.message || '生成计划失败') }
  }

  const handleExecute = async () => {
    setError('')
    setStep('executing')
    try {
      const resp = await executeMigration(planId)
      if (!resp.started) throw new Error('启动失败')
      startPolling(planId)
    } catch (e: any) { setError(e.message || '执行失败'); setStep('plan') }
  }

  const handleCommit = async () => {
    setError('')
    try {
      const { commitMigration } = await import('../services/backend')
      const resp = await commitMigration(planId)
      if (!resp.commit_ok) throw new Error('提交失败')
      setStep('done')
    } catch (e: any) { setError(e.message || '提交失败') }
  }

  // cleanup polling on unmount
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  if (!backendOnline) return <div className="page-offline">引擎未连接，无法执行迁移。</div>

  if (step === 'done') return (
    <div className="page">
      <h2 className="page-title">文件迁移</h2>
      <div className="result-card">
        <h3>迁移完成</h3>
        <p>文件已复制到目标盘，原位置已创建透明联接。</p>
        {plan && (
          <p style={{marginTop:8, color:'var(--accent-green)', fontSize:18, fontWeight:700}}>
            释放空间: {formatSize(plan.total_size)}
          </p>
        )}
        <button className="btn-primary" style={{marginTop:16}} onClick={() => { setStep('config'); setPlan(null); setSource('') }}>
          继续迁移
        </button>
      </div>
    </div>
  )

  return (
    <div className="page">
      <h2 className="page-title">文件迁移</h2>
      <p className="page-desc">将文件从 C 盘迁移到其他磁盘，原位置创建透明联接。</p>

      {sourcePath && step === 'config' && (
        <div className="result-card" style={{marginBottom:16}}>
          <strong>来源:</strong> 看板大文件
          <br /><small style={{color:'var(--text-secondary)'}}>{sourcePath}</small>
        </div>
      )}

      {step === 'config' && (
        <>
          <div className="form-section">
            <h3>源目录</h3>
            <select className="input-select" value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">-- 选择源目录 --</option>
              {KNOWN_FOLDERS.map((f) => <option key={f} value={FOLDER_MAP[f]}>{f}</option>)}
            </select>
          </div>
          <div className="form-section">
            <h3>目标盘</h3>
            <select className="input-select" value={targetDrive} onChange={(e) => setTargetDrive(e.target.value)}>
              <option value="">-- 选择目标盘 --</option>
              {disks.map((d) => <option key={d.mountpoint} value={d.mountpoint}>{d.mountpoint} (可用 {d.free_gb.toFixed(0)} GB)</option>)}
            </select>
          </div>
          <div className="form-section">
            <h3>文件类型</h3>
            <select className="input-select" value={fileFilter} onChange={(e) => setFileFilter(e.target.value)}>
              {FILE_TYPES.map((ft) => <option key={ft.value} value={ft.value}>{ft.label}</option>)}
            </select>
          </div>
          <button className="btn-primary" onClick={handleCreatePlan} disabled={!source || !targetDrive}>生成迁移计划</button>
        </>
      )}

      {step === 'plan' && plan && (
        <>
          <div className="result-card">
            <h3>迁移计划预览</h3>
            <div className="result-grid">
              <div className="result-item"><span className="result-value">{plan.file_count.toLocaleString()}</span><span className="result-label">文件数</span></div>
              <div className="result-item"><span className="result-value">{formatSize(plan.total_size)}</span><span className="result-label">总大小</span></div>
              <div className="result-item"><span className="result-value">{plan.status}</span><span className="result-label">状态</span></div>
            </div>
            <p className="plan-path">源: {plan.source}</p>
            <p className="plan-path">目标: {plan.target}</p>
          </div>
          <button className="btn-primary" onClick={handleExecute}>确认执行迁移</button>
          <button className="btn-secondary" onClick={() => setStep('config')}>取消</button>
        </>
      )}

      {step === 'executing' && (
        <div style={{marginTop:24}}>
          <div className="progress-info">
            <div className="spinner" />
            <span>正在复制文件... {progress.copied > 0 ? `${progress.copied} / ${progress.total}` : ''}</span>
          </div>
          {progress.total > 0 && (
            <div className="disk-bar-bg" style={{maxWidth:480, marginTop:8}}>
              <div className="disk-bar-fill" style={{width: `${Math.round((progress.copied / progress.total) * 100)}%`, background: 'var(--accent)'}} />
            </div>
          )}
        </div>
      )}

      {step === 'reviewing' && (
        <div className="result-card">
          <h3>文件校验通过</h3>
          <p>所有文件已成功复制并校验。点击"提交"创建联接。</p>
          <button className="btn-primary" style={{marginTop:16}} onClick={handleCommit}>提交（创建联接）</button>
          <button className="btn-secondary" onClick={() => setStep('config')}>取消</button>
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
