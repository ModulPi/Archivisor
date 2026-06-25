import React, { useEffect, useState } from 'react'
import { DashboardData, queryDashboard } from '../services/backend'
import DiskUsageCard from './DiskUsageCard'
import TopLargeFilesCard from './TopLargeFilesCard'
import UnmigratedCard from './UnmigratedCard'

interface Props {
  backendOnline: boolean
}

const Dashboard: React.FC<Props> = ({ backendOnline }) => {
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const fetchData = async () => {
    if (!backendOnline) return
    setRefreshing(true)
    setError(null)
    try {
      const result = await queryDashboard()
      setData(result)
    } catch (err: any) {
      setError(err.message || 'Failed to load dashboard')
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    if (backendOnline) {
      fetchData()
    }
  }, [backendOnline])

  if (!backendOnline) {
    return (
      <div className="dashboard-offline">
        <p>引擎未连接，无法加载数据。请确认 Python backend 已启动。</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="dashboard-error">
        <p>加载失败: {error}</p>
        <button onClick={fetchData} className="btn-retry">
          重试
        </button>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="dashboard-loading">
        <div className="spinner" />
        <p>正在加载看板数据...</p>
      </div>
    )
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h2>数据看板</h2>
        <button
          onClick={fetchData}
          disabled={refreshing}
          className="btn-refresh"
        >
          {refreshing ? '刷新中...' : '刷新'}
        </button>
      </div>

      <div className="dashboard-cards">
        <DiskUsageCard disks={data.disks} />
        <TopLargeFilesCard files={data.top_large_files} />
        <UnmigratedCard data={data.unmigrated} />
      </div>
    </div>
  )
}

export default Dashboard
