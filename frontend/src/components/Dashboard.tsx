import React, { useEffect, useState } from 'react'
import { DashboardData, queryDashboard } from '../services/backend'
import { NavigateTarget, PageKey } from '../App'
import DiskUsageCard from './DiskUsageCard'
import TopLargeFilesCard from './TopLargeFilesCard'
import UnmigratedCard from './UnmigratedCard'

interface Props {
  backendOnline: boolean
  navigateTo: (t: PageKey | NavigateTarget) => void
}

const Dashboard: React.FC<Props> = ({ backendOnline, navigateTo }) => {
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const fetchData = async () => {
    if (!backendOnline) return
    setRefreshing(true); setError(null)
    try { setData(await queryDashboard()) }
    catch (err: any) { setError(err.message || '加载失败') }
    finally { setRefreshing(false) }
  }

  useEffect(() => { if (backendOnline) fetchData() }, [backendOnline])

  if (!backendOnline) return <div className="dashboard-offline"><p>引擎未连接，无法加载数据。请确认 Python 后端已启动。</p></div>

  if (error) return (
    <div className="dashboard-error">
      <p>加载失败: {error}</p>
      <button onClick={fetchData} className="btn-retry">重试</button>
    </div>
  )

  if (!data) return <div className="dashboard-loading"><div className="spinner" /><p>正在加载看板数据...</p></div>

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h2>数据看板</h2>
        <button onClick={fetchData} disabled={refreshing} className="btn-refresh">
          {refreshing ? '刷新中...' : '刷新数据'}
        </button>
      </div>
      <div className="dashboard-cards">
        <DiskUsageCard disks={data.disks} />
        <TopLargeFilesCard files={data.top_large_files} navigateTo={navigateTo} />
        <UnmigratedCard data={data.unmigrated} />
      </div>
    </div>
  )
}

export default Dashboard
