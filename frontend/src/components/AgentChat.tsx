import React, { useState, useRef, useEffect } from 'react'
import { NavigateTarget } from '../App'
import {
  agentProcess,
  agentUsage,
  createMigrationPlan,
  searchFiles,
} from '../services/backend'
import type { AgentResponse, AgentPlan } from '../services/backend'

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------

interface Message {
  role: 'user' | 'assistant'
  content: string
  plan?: AgentPlan
  clarification?: string
  fallbackUsed?: boolean
  error?: string
}

// ---------------------------------------------------------------------------
// 组件
// ---------------------------------------------------------------------------

interface Props {
  backendOnline: boolean
  navigateTo: (target: string | NavigateTarget) => void
}

const AgentChat: React.FC<Props> = ({ backendOnline, navigateTo }) => {
  const [messages, setMessages] = useState<Message[]>(() => {
    // 初始欢迎消息
    return [{
      role: 'assistant',
      content: '你好！我是 Archivisor AI 助手。你可以用自然语言告诉我你想做什么，例如：\n\n• "把下载文件夹里上个月的PDF移到D盘"\n• "找找桌面上大于100MB的文件"\n• "清理临时文件释放C盘空间"\n• "查看磁盘占用情况"',
    }]
  })
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [usage, setUsage] = useState<{ daily_count: number; daily_limit: number; remaining: number } | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 查询 API 用量
  useEffect(() => {
    if (!backendOnline) return
    agentUsage().then(setUsage).catch(() => {})
  }, [backendOnline, messages.length])

  // 发送消息
  const handleSend = async () => {
    const query = input.trim()
    if (!query || loading || !backendOnline) return

    setInput('')
    setLoading(true)

    // 添加用户消息
    const userMsg: Message = { role: 'user', content: query }
    setMessages(prev => [...prev, userMsg])

    try {
      const result: AgentResponse = await agentProcess(query)

      if (result.error) {
        const errMsg: Message = {
          role: 'assistant',
          content: `❌ ${result.error}`,
          error: result.error,
        }
        setMessages(prev => [...prev, errMsg])
      } else if (result.clarification) {
        // 需要澄清
        const clarifyMsg: Message = {
          role: 'assistant',
          content: result.clarification,
          clarification: result.clarification,
          fallbackUsed: result.fallback_used,
        }
        setMessages(prev => [...prev, clarifyMsg])
      } else if (result.plan) {
        // 有 Plan
        const plan = result.plan
        const intentLabels: Record<string, string> = {
          move: '📦 文件迁移',
          search: '🔍 文件搜索',
          cleanup: '🧹 空间清理',
          analyze: '📊 数据分析',
        }
        const intentLabel = intentLabels[plan.intent] || plan.intent

        let content = `**${intentLabel}** (置信度: ${((result.confidence || 0) * 100).toFixed(0)}%)\n\n${plan.explanation}`
        if (result.fallback_used) {
          content += '\n\n⚠️ *离线模式 — 基于关键词规则匹配*'
        }

        const planMsg: Message = {
          role: 'assistant',
          content,
          plan,
          fallbackUsed: result.fallback_used,
        }
        setMessages(prev => [...prev, planMsg])
      } else {
        // 未知响应
        const unknownMsg: Message = {
          role: 'assistant',
          content: '收到了你的指令，但我不太确定如何处理。能换个方式描述一下吗？',
        }
        setMessages(prev => [...prev, unknownMsg])
      }

      // 刷新用量
      agentUsage().then(setUsage).catch(() => {})
    } catch (err: any) {
      const errMsg: Message = {
        role: 'assistant',
        content: `❌ 处理失败: ${err.message || '未知错误'}`,
        error: err.message,
      }
      setMessages(prev => [...prev, errMsg])
    } finally {
      setLoading(false)
    }
  }

  // 确认执行 Plan
  const handleConfirmPlan = async (plan: AgentPlan) => {
    if (plan.intent === 'move') {
      // 提取迁移参数并跳转
      const source = plan.source_path || ''
      const target = plan.target_path || ''
      const extOp = plan.operations.find(o => o.type === 'filter')
      const filters = extOp?.extensions || undefined

      try {
        const result = await createMigrationPlan(source, target, filters)
        const confirmMsg: Message = {
          role: 'assistant',
          content: `✅ 迁移计划已创建！\n\n源目录: ${source}\n目标: ${target}\n\n点击下方按钮前往执行迁移。`,
          plan: { ...plan, plan_id: String(result.plan?.plan_id || '') },
        }
        setMessages(prev => [...prev, confirmMsg])

        // 跳转到迁移页面
        navigateTo({
          page: 'migrate',
          params: {
            planId: result.plan?.plan_id,
            source,
            target,
          },
        })
      } catch (err: any) {
        const errMsg: Message = {
          role: 'assistant',
          content: `❌ 创建迁移计划失败: ${err.message}`,
          error: err.message,
        }
        setMessages(prev => [...prev, errMsg])
      }
    } else if (plan.intent === 'search') {
      // 执行搜索并跳转看板
      const filterOp = plan.operations.find(o => o.type === 'search')
      const keyword = filterOp?.extensions?.[0] || ''
      try {
        const results = await searchFiles(keyword)
        const confirmMsg: Message = {
          role: 'assistant',
          content: `✅ 搜索完成，找到 ${results.results?.length || 0} 个文件。`,
        }
        setMessages(prev => [...prev, confirmMsg])
      } catch (err: any) {
        const errMsg: Message = {
          role: 'assistant',
          content: `❌ 搜索失败: ${err.message}`,
        }
        setMessages(prev => [...prev, errMsg])
      }
    } else if (plan.intent === 'cleanup') {
      navigateTo({ page: 'cleanup' })
      const confirmMsg: Message = {
        role: 'assistant',
        content: '✅ 已跳转到清理页面，你可以查看重复文件和临时文件并手动清理。',
      }
      setMessages(prev => [...prev, confirmMsg])
    } else if (plan.intent === 'analyze') {
      navigateTo({ page: 'dashboard' })
      const confirmMsg: Message = {
        role: 'assistant',
        content: '✅ 已跳转到看板页面。',
      }
      setMessages(prev => [...prev, confirmMsg])
    }
  }

  // 键盘事件
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // 渲染单条消息
  const renderMessage = (msg: Message, idx: number) => {
    const isUser = msg.role === 'user'

    return (
      <div key={idx} className={`chat-msg ${isUser ? 'chat-msg-user' : 'chat-msg-bot'}`}>
        <div className="chat-msg-avatar">{isUser ? '👤' : '🤖'}</div>
        <div className="chat-msg-body">
          {/* 文本内容（支持简单换行） */}
          <div className="chat-msg-text">
            {msg.content.split('\n').map((line, i) => (
              <span key={i}>
                {line.startsWith('**') ? (
                  <strong>{line.replace(/\*\*/g, '')}</strong>
                ) : (
                  line
                )}
                {i < msg.content.split('\n').length - 1 && <br />}
              </span>
            ))}
          </div>

          {/* Plan 预览卡片 */}
          {msg.plan && (
            <div className="chat-plan-card">
              <div className="chat-plan-header">
                <span className="chat-plan-intent">
                  {msg.plan.intent === 'move' && '📦'}
                  {msg.plan.intent === 'search' && '🔍'}
                  {msg.plan.intent === 'cleanup' && '🧹'}
                  {msg.plan.intent === 'analyze' && '📊'}
                  {' '}Plan 预览
                </span>
                {msg.fallbackUsed && (
                  <span className="chat-plan-badge" title="DeepSeek API 不可用，使用本地规则引擎">⚡离线模式</span>
                )}
              </div>

              <div className="chat-plan-details">
                {msg.plan.source_path && (
                  <div className="chat-plan-row">
                    <span className="chat-plan-label">源路径</span>
                    <code>{msg.plan.source_path}</code>
                  </div>
                )}
                {msg.plan.target_path && (
                  <div className="chat-plan-row">
                    <span className="chat-plan-label">目标路径</span>
                    <code>{msg.plan.target_path}</code>
                  </div>
                )}
                <div className="chat-plan-row">
                  <span className="chat-plan-label">操作步骤</span>
                  <span className="chat-plan-steps">
                    {msg.plan.operations.map((op, i) => (
                      <span key={i} className="chat-plan-step-tag">
                        {op.type === 'scan' && '① 扫描'}
                        {op.type === 'filter' && '② 筛选'}
                        {op.type === 'copy' && '③ 复制'}
                        {op.type === 'verify' && '④ 校验'}
                        {op.type === 'commit_soft_delete' && '⑤ 提交'}
                        {op.type === 'search' && '🔍 搜索'}
                        {op.type === 'find_duplicates' && '🔎 查重复'}
                        {op.type === 'find_temp_files' && '🗑 找临时文件'}
                        {op.type === 'dashboard' && '📊 看板'}
                      </span>
                    ))}
                  </span>
                </div>
              </div>

              {msg.plan.requires_confirmation && (
                <button
                  className="chat-plan-confirm-btn"
                  onClick={() => handleConfirmPlan(msg.plan!)}
                >
                  ✅ 确认执行
                </button>
              )}
            </div>
          )}

          {/* 澄清选项 */}
          {msg.clarification && (
            <div className="chat-clarification">
              <p>请选择一个选项：</p>
              <div className="chat-clarification-options">
                {['A', 'B', 'C', 'D'].map(opt => {
                  const match = msg.clarification!.match(new RegExp(`${opt}\\.\\s*(.+?)(?:\\n|$)`))
                  if (!match) return null
                  return (
                    <button
                      key={opt}
                      className="chat-clarify-btn"
                      onClick={() => {
                        setInput(match[1])
                        // 不自动发送，让用户确认
                      }}
                    >
                      <strong>{opt}.</strong> {match[1]}
                    </button>
                  )
                })}
                {!msg.clarification.match(/[A-D]\./) && (
                  <button
                    className="chat-clarify-btn"
                    onClick={() => setInput(msg.clarification || '')}
                  >
                    使用此建议
                  </button>
                )}
              </div>
            </div>
          )}

          {/* 错误 */}
          {msg.error && (
            <div className="chat-msg-error">
              ⚠️ {msg.error}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="agent-chat-container">
      {/* 用量指示器 */}
      {usage && (
        <div className="agent-usage-bar">
          <span>DeepSeek API: </span>
          <span className={`agent-usage-count ${usage.remaining < 5 ? 'low' : ''}`}>
            {usage.daily_count}/{usage.daily_limit}
          </span>
          <span className="agent-usage-hint">
            {usage.remaining > 0 ? ` (今日剩余 ${usage.remaining} 次)` : ' (今日已用完，使用离线模式)'}
          </span>
        </div>
      )}

      {/* 消息列表 */}
      <div className="chat-messages">
        {messages.map((msg, idx) => renderMessage(msg, idx))}
        {loading && (
          <div className="chat-msg chat-msg-bot">
            <div className="chat-msg-avatar">🤖</div>
            <div className="chat-msg-body">
              <div className="chat-typing">
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 输入区域 */}
      <div className="chat-input-area">
        <textarea
          className="chat-input"
          placeholder={backendOnline ? '输入指令，如"把下载的PDF移到D盘"...' : 'AI 助手离线 — 请等待后端连接...'}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={!backendOnline || loading}
          rows={2}
        />
        <button
          className="chat-send-btn"
          onClick={handleSend}
          disabled={!backendOnline || loading || !input.trim()}
        >
          {loading ? '⏳' : '发送'}
        </button>
      </div>

      {/* 快捷指令 */}
      <div className="chat-quick-commands">
        <span className="chat-quick-label">快捷指令: </span>
        {[
          '把桌面文件移到D盘',
          '找找大于100MB的文件',
          '清理临时文件',
          '查看磁盘占用',
        ].map(cmd => (
          <button
            key={cmd}
            className="chat-quick-btn"
            onClick={() => setInput(cmd)}
            disabled={loading}
          >
            {cmd}
          </button>
        ))}
      </div>
    </div>
  )
}

export default AgentChat
