import React, { useEffect, useState } from 'react'
import type { MonitorOverview, SystemResources } from '../types'
import { useAppStore } from '../store/useAppStore'

const API = 'http://localhost:7070'

const EMPTY_OVERVIEW: MonitorOverview = {
  db_size_bytes: 0,
  capture_total_count: 0,
  token_usage: {
    total_period: 0,
    total_today: 0,
    by_model: [],
    by_caller: [],
    trend: [],
  },
  capture_flow: {
    today_count: 0,
    period_count: 0,
    eligible_count: 0,
    vectorized_count: 0,
    vectorization_rate: 0,
    knowledge_generated_count: 0,
    knowledge_generation_rate: 0,
    knowledge_linked_count: 0,
    knowledge_rate: 0,
    by_hour: [],
    by_app: [],
    recent: [],
  },
  knowledge_flow: {
    today_count: 0,
    period_count: 0,
    by_time: [],
    recent: [],
  },
  rag_sessions: {
    today_count: 0,
    period_count: 0,
    avg_latency_ms: 0,
    recent: [],
  },
  task_executions: {
    total: 0,
    success: 0,
    failed: 0,
    success_rate: 0,
    recent: [],
  },
}

const CALLER_LABELS: Record<string, string> = {
  rag: 'RAG 问答', task: '定时任务', knowledge: '知识提炼',
}
const CALLER_COLORS: Record<string, string> = {
  rag: '#007AFF', task: '#34C759', knowledge: '#AF52DE',
}
const STATUS_COLOR: Record<string, string> = {
  success: '#34C759', failed: '#FF3B30', running: '#FF9500',
}
const EVENT_COLOR: Record<string, string> = {
  load_done: '#34C759', load_start: '#FF9500', unload: '#6E6E73', load_failed: '#FF3B30',
}
const EVENT_LABEL: Record<string, string> = {
  load_done: '加载完成', load_start: '加载中', unload: '已卸载', load_failed: '加载失败',
}

function fmt(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

function fmtBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

function fmtTs(ms: number): string {
  return new Date(ms).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

function fmtAxisTs(ms: number): string {
  return new Date(ms).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

type OverviewRange = '1d' | '7d' | '30d'
type SystemRange = '1h' | '6h' | '24h'

function getOverviewBucketLabel(range: OverviewRange): string {
  if (range === '1d') return '约 1 小时'
  if (range === '7d') return '约 6 小时'
  return '约 1 天'
}

function getKnowledgeBucketLabel(range: OverviewRange): string {
  if (range === '1d') return '约 5 分钟'
  if (range === '7d') return '约 1 小时'
  return '约 1 天'
}

function getTrendTitle(title: string, bucketLabel: string): string {
  return `${title}（${bucketLabel}）`
}

function getKnowledgeTrendLabel(range: OverviewRange): string {
  return getTrendTitle('知识提炼趋势', getKnowledgeBucketLabel(range))
}

function getSystemBucketLabel(range: SystemRange): string {
  if (range === '1h') return '约 1 分钟'
  if (range === '6h') return '约 3 分钟'
  return '约 12 分钟'
}

function fmtOverviewAxisTs(ms: number, range: OverviewRange): string {
  const date = new Date(Number(ms))
  if (Number.isNaN(date.getTime())) return '—'
  if (range === '1d') {
    return date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  }
  return date.toLocaleDateString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
  })
}

function fmtSystemAxisTs(ms: number, range: SystemRange): string {
  const date = new Date(Number(ms))
  if (Number.isNaN(date.getTime())) return '—'
  if (range === '24h') {
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  }
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function fmtMs(ms: number | null): string {
  if (!ms) return '—'
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${ms}ms`
}

// ── 迷你折线图（纯 SVG）────────────────────────────────────────────────────
type LinePoint = { ts: number; value: number }
type MultiLineSeries = {
  label: string
  color: string
  data: LinePoint[]
  valueFormatter?: (value: number) => string
}

const SparkLine: React.FC<{
  data?: LinePoint[]
  series?: MultiLineSeries[]
  color?: string
  height?: number
  valueFormatter?: (value: number) => string
  axisFormatter?: (ts: number) => string
  detailFormatter?: (point: LinePoint) => string
}> = ({
  data,
  series,
  color = '#007AFF',
  height = 40,
  valueFormatter = (value) => String(value),
  axisFormatter = fmtAxisTs,
  detailFormatter,
}) => {
  const normalizedSeries = (series && series.length > 0)
    ? series.filter(item => item.data.length > 0)
    : (data && data.length > 0 ? [{ label: '当前序列', color, data, valueFormatter }] : [])
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)

  if (!normalizedSeries.length) return null

  const baseData = normalizedSeries[0].data
  const w = 200
  const h = height
  const pad = 8
  const allValues = normalizedSeries.flatMap(item => item.data.map(d => d.value))
  const max = Math.max(...allValues, 1)
  const min = Math.min(...allValues, 0)
  const range = Math.max(max - min, 1)
  const axisValueFormatter = normalizedSeries[0].valueFormatter || valueFormatter

  const seriesPoints = normalizedSeries.map(item => {
    const points = item.data.map((d, i) => {
      const x = pad + (i / Math.max(item.data.length - 1, 1)) * (w - pad * 2)
      const y = h - pad - ((d.value - min) / range) * (h - pad * 2)
      return { ...d, x, y }
    })
    return {
      ...item,
      points,
      pts: points.map(p => `${p.x},${p.y}`).join(' '),
      area: `${pad},${h - pad} ${points.map(p => `${p.x},${p.y}`).join(' ')} ${w - pad},${h - pad}`,
    }
  })

  const maxLength = Math.max(...normalizedSeries.map(item => item.data.length), 0)
  const safeHoverIndex = hoverIndex !== null ? Math.min(hoverIndex, Math.max(maxLength - 1, 0)) : null
  const hoverPoints = safeHoverIndex !== null
    ? seriesPoints.map(item => item.points[Math.min(safeHoverIndex, item.points.length - 1)]).filter(Boolean)
    : []
  const hoverAxisTs = hoverPoints[0]?.ts ?? baseData[baseData.length - 1]?.ts ?? 0

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'stretch', gap: 6 }}>
        <div style={{ width: 34, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', fontSize: 9, color: '#AEAEB2', textAlign: 'right', paddingTop: 2, paddingBottom: 22 }}>
          <span>{axisValueFormatter(max)}</span>
          <span>{axisValueFormatter((max + min) / 2)}</span>
          <span>{axisValueFormatter(min)}</span>
        </div>
        <div style={{ flex: 1 }}>
          <svg
            width="100%"
            viewBox={`0 0 ${w} ${h}`}
            preserveAspectRatio="none"
            style={{ display: 'block', overflow: 'visible' }}
            onMouseLeave={() => setHoverIndex(null)}
          >
            <defs>
              {seriesPoints.map(item => (
                <linearGradient key={item.color} id={`grad-${item.color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={item.color} stopOpacity="0.22" />
                  <stop offset="100%" stopColor={item.color} stopOpacity="0.01" />
                </linearGradient>
              ))}
            </defs>
            {seriesPoints.map((item, idx) => (
              <g key={`${item.label}-${item.color}`}>
                {idx === 0 && <polygon points={item.area} fill={`url(#grad-${item.color.replace('#', '')})`} />}
                <polyline points={item.pts} fill="none" stroke={item.color} strokeWidth="1.5" strokeLinejoin="round" />
              </g>
            ))}
            {baseData.map((_, i) => {
              const x = pad + (i / Math.max(baseData.length - 1, 1)) * (w - pad * 2)
              return (
                <rect
                  key={i}
                  x={x - 6}
                  y={0}
                  width={12}
                  height={h}
                  fill="transparent"
                  onMouseEnter={() => setHoverIndex(i)}
                />
              )
            })}
            {hoverPoints.length > 0 && (
              <line x1={hoverPoints[0].x} y1={pad} x2={hoverPoints[0].x} y2={h - pad} stroke={hoverPoints[0] ? '#AEAEB2' : color} strokeOpacity="0.35" strokeDasharray="2 2" />
            )}
            {hoverPoints.map((point, idx) => (
              <circle key={`${point.ts}-${idx}`} cx={point.x} cy={point.y} r={3} fill={seriesPoints[idx].color} />
            ))}
          </svg>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: '#AEAEB2' }}>
            <span>{axisFormatter(baseData[0].ts)}</span>
            <span>{axisFormatter(baseData[Math.floor(baseData.length / 2)].ts)}</span>
            <span>{axisFormatter(baseData[baseData.length - 1].ts)}</span>
          </div>
        </div>
      </div>
      <div style={{ fontSize: 11, color: '#6E6E73', marginTop: 6, minHeight: 16 }}>
        {normalizedSeries.length === 1
          ? (() => {
              const singleData = normalizedSeries[0].data
              const singleHoverPoint = safeHoverIndex !== null ? singleData[Math.min(safeHoverIndex, singleData.length - 1)] : null
              return singleHoverPoint
                ? (detailFormatter ? detailFormatter(singleHoverPoint) : `${fmtTs(singleHoverPoint.ts)} · ${valueFormatter(singleHoverPoint.value)}`)
                : (detailFormatter
                    ? detailFormatter(singleData[singleData.length - 1])
                    : `最近: ${fmtTs(singleData[singleData.length - 1].ts)} · ${valueFormatter(singleData[singleData.length - 1].value)}`)
            })()
          : `${safeHoverIndex !== null ? fmtTs(hoverAxisTs) : `最近: ${fmtTs(hoverAxisTs)}`} · ${normalizedSeries.map((item) => {
              const point = item.data[Math.min(safeHoverIndex ?? item.data.length - 1, item.data.length - 1)]
              const formatter = item.valueFormatter || valueFormatter
              return `${item.label} ${formatter(point.value)}`
            }).join(' · ')}`}
      </div>
    </div>
  )
}

// ── 柱状图（纯 SVG）────────────────────────────────────────────────────────
const BarChart: React.FC<{
  data: { label: string; value: number; color?: string }[]
  height?: number
  valueFormatter?: (value: number) => string
}> = ({ data, height = 80, valueFormatter = (value) => String(value) }) => {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  if (!data.length) return null
  const max = Math.max(...data.map(d => d.value), 1)
  const mid = max / 2
  const hoverItem = hoverIndex !== null ? data[hoverIndex] : null
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'stretch', gap: 6, height }}>
        <div style={{ width: 34, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', fontSize: 9, color: '#AEAEB2', textAlign: 'right', paddingTop: 2, paddingBottom: 18 }}>
          <span>{valueFormatter(max)}</span>
          <span>{valueFormatter(mid)}</span>
          <span>{valueFormatter(0)}</span>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'flex-end', gap: 4, height }}>
          {data.map((d, i) => (
            <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
              <div
                style={{
                  width: '100%', borderRadius: '3px 3px 0 0',
                  height: Math.max((d.value / max) * (height - 20), 2),
                  background: d.color || '#007AFF',
                  opacity: hoverIndex === i ? 1 : 0.85,
                }}
                title={`${d.label}: ${valueFormatter(d.value)}`}
                onMouseEnter={() => setHoverIndex(i)}
                onMouseLeave={() => setHoverIndex(null)}
              />
              <span style={{ fontSize: 9, color: '#AEAEB2', textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', width: '100%' }}>
                {d.label}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div style={{ fontSize: 11, color: '#6E6E73', marginTop: 6, minHeight: 16 }}>
        {hoverItem ? `${hoverItem.label || '当前'} · ${valueFormatter(hoverItem.value)}` : '悬停柱子可查看具体值'}
      </div>
    </div>
  )
}

// ── 统计卡片 ────────────────────────────────────────────────────────────────
const StatCard: React.FC<{
  label: string; value: string; sub?: string; color: string
}> = ({ label, value, sub, color }) => (
  <div style={{
    background: `${color}10`, borderRadius: 10, padding: '10px 12px',
    border: `1px solid ${color}20`, flex: 1, minWidth: 0,
  }}>
    <div style={{ fontSize: 11, color: '#6E6E73', marginBottom: 4 }}>{label}</div>
    <div style={{ fontSize: 20, fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
    {sub && <div style={{ fontSize: 11, color: '#AEAEB2', marginTop: 3 }}>{sub}</div>}
  </div>
)

// ── 总览内容 ─────────────────────────────────────────────────────────────────
const OverviewContent: React.FC<{ data: MonitorOverview; range: OverviewRange }> = ({ data, range }) => {
  const token_usage = {
    ...EMPTY_OVERVIEW.token_usage,
    ...(data?.token_usage ?? {}),
    by_model: data?.token_usage?.by_model ?? [],
    by_caller: data?.token_usage?.by_caller ?? [],
    trend: data?.token_usage?.trend ?? [],
  }
  const capture_flow = {
    ...EMPTY_OVERVIEW.capture_flow,
    ...(data?.capture_flow ?? {}),
    by_hour: data?.capture_flow?.by_hour ?? [],
    by_app: data?.capture_flow?.by_app ?? [],
    recent: data?.capture_flow?.recent ?? [],
  }
  const rag_sessions = {
    ...EMPTY_OVERVIEW.rag_sessions,
    ...(data?.rag_sessions ?? {}),
    recent: data?.rag_sessions?.recent ?? [],
  }
  const knowledge_flow = {
    ...EMPTY_OVERVIEW.knowledge_flow,
    ...(data?.knowledge_flow ?? {}),
    by_time: data?.knowledge_flow?.by_time ?? [],
    recent: data?.knowledge_flow?.recent ?? [],
  }
  const task_executions = {
    ...EMPTY_OVERVIEW.task_executions,
    ...(data?.task_executions ?? {}),
    recent: data?.task_executions?.recent ?? [],
  }
  return (
    <>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <StatCard label="Token 用量" value={fmt(token_usage.total_period)}
          sub={`今日 ${fmt(token_usage.total_today)}`} color="#007AFF" />
        <StatCard label="采集记录" value={fmt(capture_flow.period_count)}
          sub={`可处理 ${fmt(capture_flow.eligible_count)} · 今日 ${capture_flow.today_count}`} color="#34C759" />
        <StatCard label="总采集数" value={fmt(data?.capture_total_count ?? 0)}
          sub={`数据库 ${fmtBytes(data?.db_size_bytes ?? 0)}`} color="#32ADE6" />
        <StatCard label="知识提炼" value={fmt(knowledge_flow.period_count)}
          sub={`今日 ${fmt(knowledge_flow.today_count)}`} color="#BF5AF2" />
        <StatCard label="向量化率" value={`${(capture_flow.vectorization_rate * 100).toFixed(0)}%`}
          sub={`已入索引 ${fmt(capture_flow.vectorized_count)}/${fmt(capture_flow.eligible_count)}`} color="#5E5CE6" />
        <StatCard label="知识化率" value={`${(capture_flow.knowledge_generation_rate * 100).toFixed(0)}%`}
          sub={`已生成 knowledge ${fmt(capture_flow.knowledge_generated_count)}`} color="#AF52DE" />
        <StatCard label="知识挂载率" value={`${(capture_flow.knowledge_rate * 100).toFixed(0)}%`}
          sub={`已关联 capture ${fmt(capture_flow.knowledge_linked_count)}`} color="#FF9500" />
      </div>

      <div style={cardStyle}>
        <div style={sectionTitle}>{getTrendTitle('Token 用量趋势', getOverviewBucketLabel(range))}</div>
        {token_usage.trend.length > 0 ? (
          <>
            <SparkLine
              data={token_usage.trend.map((t) => ({ ts: t.ts, value: t.tokens }))}
              color="#007AFF"
              height={50}
              valueFormatter={(value) => `${fmt(value)} tokens`}
              axisFormatter={(ts) => fmtOverviewAxisTs(ts, range)}
              detailFormatter={(point) => {
                const item = token_usage.trend.find((entry) => entry.ts === point.ts)
                return item ? `${fmtTs(item.ts)} · ${fmt(item.tokens)} tokens · ${item.calls} 次` : ''
              }}
            />
            {token_usage.trend.length === 1 && (
              <div style={{ color: '#AEAEB2', fontSize: 11, marginTop: 6 }}>当前时间范围内仅 1 个统计点，已按真实数据展示。</div>
            )}
          </>
        ) : <div style={{ color: '#AEAEB2', fontSize: 12, textAlign: 'center', padding: '12px 0' }}>暂无趋势数据</div>}
      </div>

      <div style={cardStyle}>
        <div style={sectionTitle}>{getKnowledgeTrendLabel(range)}</div>
        {knowledge_flow.by_time.length > 0 ? (
          <>
            <SparkLine
              data={knowledge_flow.by_time.map((t) => ({ ts: t.ts, value: t.count }))}
              color="#BF5AF2"
              height={50}
              valueFormatter={(value) => `${value} 条`}
              axisFormatter={(ts) => fmtOverviewAxisTs(ts, range)}
              detailFormatter={(point) => `${fmtTs(point.ts)} · ${point.value} 条知识`}
            />
            {knowledge_flow.by_time.length === 1 && (
              <div style={{ color: '#AEAEB2', fontSize: 11, marginTop: 6 }}>当前时间范围内仅 1 个统计点，已按真实数据展示。</div>
            )}
          </>
        ) : <div style={{ color: '#AEAEB2', fontSize: 12, textAlign: 'center', padding: '12px 0' }}>暂无知识趋势数据</div>}
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
        <div style={{ ...cardStyle, flex: 1 }}>
          <div style={sectionTitle}>模型用量</div>
          {token_usage.by_model.length === 0
            ? <div style={{ color: '#AEAEB2', fontSize: 12 }}>暂无数据</div>
            : token_usage.by_model.map((m, i) => {
              const pct = token_usage.total_period > 0 ? (m.total / token_usage.total_period * 100).toFixed(0) : '0'
              return (
                <div key={i} style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 3 }}>
                    <span style={{ color: '#333', fontWeight: 500 }}>{m.model}</span>
                    <span style={{ color: '#6E6E73' }}>{fmt(m.total)} ({pct}%)</span>
                  </div>
                  <div style={{ height: 4, borderRadius: 2, background: '#E5E5EA' }}>
                    <div style={{ height: '100%', borderRadius: 2, background: '#007AFF', width: `${pct}%` }} />
                  </div>
                </div>
              )
            })}
        </div>
        <div style={{ ...cardStyle, flex: 1 }}>
          <div style={sectionTitle}>按来源分布</div>
          {token_usage.by_caller.length === 0
            ? <div style={{ color: '#AEAEB2', fontSize: 12 }}>暂无数据</div>
            : token_usage.by_caller.map((c, i) => {
              const color = CALLER_COLORS[c.caller] || '#6E6E73'
              const pct = token_usage.total_period > 0 ? (c.total / token_usage.total_period * 100).toFixed(0) : '0'
              return (
                <div key={i} style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 3 }}>
                    <span style={{ color, fontWeight: 500 }}>{CALLER_LABELS[c.caller] || c.caller}</span>
                    <span style={{ color: '#6E6E73' }}>{fmt(c.total)} · {c.calls}次</span>
                  </div>
                  <div style={{ height: 4, borderRadius: 2, background: '#E5E5EA' }}>
                    <div style={{ height: '100%', borderRadius: 2, background: color, width: `${pct}%` }} />
                  </div>
                </div>
              )
            })}
        </div>
      </div>

      <div style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
          <span style={sectionTitle as any}>采集流水（今日按小时）</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'flex-end' }}>
            <span style={{ fontSize: 11, color: '#5E5CE6' }}>向量化率 {(capture_flow.vectorization_rate * 100).toFixed(0)}%</span>
            <span style={{ fontSize: 11, color: '#AF52DE' }}>知识化率 {(capture_flow.knowledge_generation_rate * 100).toFixed(0)}%</span>
            <span style={{ fontSize: 11, color: '#6E6E73' }}>知识挂载率 {(capture_flow.knowledge_rate * 100).toFixed(0)}%</span>
          </div>
        </div>
        {capture_flow.by_hour.length > 0
          ? <BarChart data={Array.from({ length: 24 }, (_, h) => ({
              label: h % 4 === 0 ? String(h) : '',
              value: capture_flow.by_hour.find(b => b.hour === h)?.count || 0,
              color: '#34C759',
            }))} height={70} valueFormatter={(value) => `${value} 条`} />
          : <div style={{ color: '#AEAEB2', fontSize: 12, textAlign: 'center', padding: '12px 0' }}>今日暂无采集数据</div>}
        {capture_flow.by_app.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 11, color: '#6E6E73', marginBottom: 6 }}>应用分布（Top 8）</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {capture_flow.by_app.map((a, i) => (
                <div key={i} style={{ fontSize: 11, padding: '2px 8px', borderRadius: 10,
                  background: 'rgba(52,199,89,0.1)', color: '#34C759' }}>{a.app} {a.count}</div>
              ))}
            </div>
          </div>
        )}
        {capture_flow.recent.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 11, color: '#6E6E73', marginBottom: 6 }}>最近采集记录</div>
            {capture_flow.recent.map((c, i) => (
              <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0',
                borderBottom: i < capture_flow.recent.length - 1 ? '1px solid rgba(0,0,0,0.05)' : 'none' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, color: '#333' }}>{c.app_name || '上下文缺失'}</div>
                  <div style={{ fontSize: 11, color: '#AEAEB2', marginTop: 2 }}>{fmtTs(c.ts)}</div>
                </div>
                <div style={{ fontSize: 11, color: '#6E6E73', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {c.win_title || '无窗口标题'}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={cardStyle}>
        <div style={sectionTitle}>最近问答记录</div>
        {rag_sessions.recent.length === 0
          ? <div style={{ color: '#AEAEB2', fontSize: 12 }}>暂无问答记录</div>
          : rag_sessions.recent.map((s, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0',
              borderBottom: i < rag_sessions.recent.length - 1 ? '1px solid rgba(0,0,0,0.05)' : 'none' }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, color: '#333', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.query}</div>
                <div style={{ fontSize: 11, color: '#AEAEB2', marginTop: 2 }}>{fmtTs(s.ts)}</div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                {s.latency_ms && <span style={{ fontSize: 11, color: '#6E6E73' }}>{fmtMs(s.latency_ms)}</span>}
                <span style={{ fontSize: 11, padding: '1px 6px', borderRadius: 4,
                  background: 'rgba(0,122,255,0.08)', color: '#007AFF' }}>{s.context_count} 条</span>
              </div>
            </div>
          ))}
      </div>

      <div style={cardStyle}>
        <div style={sectionTitle}>最近知识提炼记录</div>
        {knowledge_flow.recent.length === 0
          ? <div style={{ color: '#AEAEB2', fontSize: 12 }}>暂无知识记录</div>
          : knowledge_flow.recent.map((item, i) => (
            <div key={item.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0',
              borderBottom: i < knowledge_flow.recent.length - 1 ? '1px solid rgba(0,0,0,0.05)' : 'none' }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, color: '#333', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.summary || '无摘要'}</div>
                <div style={{ fontSize: 11, color: '#AEAEB2', marginTop: 2 }}>{fmtTs(item.ts)}</div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0, alignItems: 'center' }}>
                {!!item.app_name && <span style={{ fontSize: 11, color: '#6E6E73', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.app_name}</span>}
                <span style={{ fontSize: 11, padding: '1px 6px', borderRadius: 4, background: 'rgba(191,90,242,0.10)', color: '#BF5AF2' }}>{item.category}</span>
              </div>
            </div>
          ))}
      </div>

      <div style={{ ...cardStyle, marginBottom: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={sectionTitle as any}>定时任务执行记录</span>
          <span style={{ fontSize: 11, color: '#6E6E73' }}>成功 {task_executions.success} / 失败 {task_executions.failed}</span>
        </div>
        {task_executions.recent.length === 0
          ? <div style={{ color: '#AEAEB2', fontSize: 12 }}>暂无执行记录</div>
          : task_executions.recent.map((e, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0',
              borderBottom: i < task_executions.recent.length - 1 ? '1px solid rgba(0,0,0,0.05)' : 'none' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                background: STATUS_COLOR[e.status] || '#AEAEB2' }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, color: '#333', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.task_name}</div>
                <div style={{ fontSize: 11, color: '#AEAEB2', marginTop: 2 }}>{fmtTs(e.started_at)}</div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0, fontSize: 11, color: '#6E6E73' }}>
                {e.latency_ms && <span>{fmtMs(e.latency_ms)}</span>}
                {e.knowledge_count && <span>{e.knowledge_count} 条知识</span>}
              </div>
            </div>
          ))}
      </div>
    </>
  )
}

// ── 系统资源内容 ──────────────────────────────────────────────────────────────
const formatCoverageText = (note?: string | null, status?: string | null) => {
  if (note && note.trim()) return note
  if (status === 'exact') return '覆盖完整'
  if (status === 'partial') return '部分识别'
  if (status === 'unavailable') return '未识别到进程'
  return '状态未知'
}

const SystemContent: React.FC<{ data: SystemResources | null; range: SystemRange }> = ({ data, range }) => {
  if (!data) return <div style={{ color: '#AEAEB2', fontSize: 12, textAlign: 'center', padding: '24px 0' }}>暂无数据</div>
  const { latest, disk_trend, model_events, trends } = data
  const knowledgeEvents = data.knowledge_events ?? []
  const gpuTrend = data.gpu_trend ?? []
  const modelGpuTrend = data.model_gpu_trend ?? []
  const system = latest.system
  const suite = latest.suite
  const model = latest.model
  const systemMemSub = system ? `${Math.round(system.mem_percent)}% · ${system.mem_used_mb.toLocaleString()} / ${system.mem_total_mb.toLocaleString()} MB` : ''
  const eventPageSize = 10
  const [eventPage, setEventPage] = useState(1)
  const totalEventPages = Math.max(1, Math.ceil(model_events.length / eventPageSize))
  const pagedModelEvents = model_events.slice((eventPage - 1) * eventPageSize, eventPage * eventPageSize)

  useEffect(() => {
    setEventPage(1)
  }, [range, model_events.length])

  const renderTrendCard = (
    title: string,
    series: { ts: number; value: number }[],
    color: string,
    formatter: (value: number) => string,
    emptyText = '暂无数据',
  ) => (
    <div style={cardStyle}>
      <div style={sectionTitle}>{getTrendTitle(title, getSystemBucketLabel(range))}</div>
      {series.length > 0
        ? <>
            <SparkLine
              data={series}
              color={color}
              height={50}
              valueFormatter={formatter}
              axisFormatter={(ts) => fmtSystemAxisTs(ts, range)}
            />
            {series.length === 1 && <div style={{ color: '#AEAEB2', fontSize: 11, marginTop: 6 }}>当前范围仅 1 个采样点。</div>}
          </>
        : <div style={{ color: '#AEAEB2', fontSize: 12, textAlign: 'center', padding: '12px 0' }}>{emptyText}</div>}
    </div>
  )

  const renderDualTrendCard = (
    title: string,
    lines: Array<{ label: string; color: string; data: { ts: number; value: number }[]; formatter: (value: number) => string }>,
    emptyText = '暂无数据',
  ) => {
    const available = lines.filter(line => line.data.length > 0)
    if (available.length === 0) {
      return (
        <div style={cardStyle}>
          <div style={sectionTitle}>{getTrendTitle(title, getSystemBucketLabel(range))}</div>
          <div style={{ color: '#AEAEB2', fontSize: 12, textAlign: 'center', padding: '12px 0' }}>{emptyText}</div>
        </div>
      )
    }

    return (
      <div style={cardStyle}>
        <div style={sectionTitle}>{getTrendTitle(title, getSystemBucketLabel(range))}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
          {available.map((line) => (
            <span key={line.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#6E6E73' }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: line.color, display: 'inline-block' }} />
              {line.label}
            </span>
          ))}
        </div>
        <SparkLine
          series={available.map((line) => ({
            label: line.label,
            color: line.color,
            data: line.data,
            valueFormatter: line.formatter,
          }))}
          height={54}
          axisFormatter={(ts) => fmtSystemAxisTs(ts, range)}
        />
        {available.every((line) => line.data.length === 1) && (
          <div style={{ color: '#AEAEB2', fontSize: 11, marginTop: 6 }}>当前范围仅 1 个采样点。</div>
        )}
      </div>
    )
  }

  return (
    <>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        {system && (
          <>
            <StatCard label="系统 CPU" value={`${system.cpu_total.toFixed(1)}%`} color="#FF9500" />
            <StatCard label="系统内存" value={`${system.mem_percent.toFixed(1)}%`}
              sub={systemMemSub} color="#007AFF" />
            {(system.gpu_percent != null || system.gpu_name) && (
              <StatCard
                label="系统 GPU"
                value={system.gpu_percent != null ? `${system.gpu_percent.toFixed(1)}%` : '已检测'}
                sub={system.gpu_total_label || system.gpu_name || 'GPU'}
                color="#34C759"
              />
            )}
          </>
        )}
        {suite && (
          <>
            <StatCard label="整套 CPU" value={`${suite.cpu_percent.toFixed(1)}%`}
              sub={`${suite.process_count} 个进程`} color="#AF52DE" />
            <StatCard label="整套内存" value={`${suite.mem_process_mb} MB`}
              sub={formatCoverageText(suite.coverage_note, suite.coverage_status)} color="#BF5AF2" />
          </>
        )}
        {model && (
          <>
            <StatCard label="模型 CPU" value={`${model.cpu_percent.toFixed(1)}%`}
              sub={`${model.process_count} 个进程`} color="#FF3B30" />
            <StatCard label="模型内存" value={`${model.mem_process_mb} MB`}
              sub={formatCoverageText(model.coverage_note, model.coverage_status)} color="#FF2D55" />
          </>
        )}
        <StatCard label="数据库大小" value={fmtBytes(data.db_size_bytes)} color="#32ADE6" />
      </div>

      {renderDualTrendCard('CPU 趋势（系统 vs 整套软件 vs 模型）', [
        { label: '系统', color: '#FF9500', data: trends.system_cpu, formatter: (value) => `${value.toFixed(1)}%` },
        { label: '整套软件', color: '#AF52DE', data: trends.suite_cpu, formatter: (value) => `${value.toFixed(1)}%` },
        { label: '模型', color: '#FF3B30', data: trends.model_cpu, formatter: (value) => `${value.toFixed(1)}%` },
      ], '暂无 CPU 趋势数据')}
      {renderDualTrendCard('内存趋势（系统 vs 整套软件 vs 模型）', [
        { label: '系统', color: '#007AFF', data: trends.system_mem, formatter: (value) => `${value.toFixed(1)}%` },
        { label: '整套软件', color: '#BF5AF2', data: trends.suite_mem, formatter: (value) => `${value.toFixed(0)} MB` },
        { label: '模型', color: '#FF2D55', data: trends.model_mem, formatter: (value) => `${value.toFixed(0)} MB` },
      ], '暂无内存趋势数据')}

      <div style={cardStyle}>
        <div style={sectionTitle}>{getTrendTitle('GPU 趋势（系统 vs 模型）', getSystemBucketLabel(range))}</div>
        {(gpuTrend.length > 0 || modelGpuTrend.length > 0) ? (
          <>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
              {gpuTrend.length > 0 && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#6E6E73' }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#34C759', display: 'inline-block' }} />
                  系统
                </span>
              )}
              {modelGpuTrend.length > 0 && (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#6E6E73' }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#FF2D55', display: 'inline-block' }} />
                  模型
                </span>
              )}
            </div>
            <SparkLine
              series={[
                ...(gpuTrend.length > 0 ? [{ label: '系统', color: '#34C759', data: gpuTrend, valueFormatter: (value: number) => `${value.toFixed(1)}%` }] : []),
                ...(modelGpuTrend.length > 0 ? [{ label: '模型', color: '#FF2D55', data: modelGpuTrend, valueFormatter: (value: number) => `${value.toFixed(1)}%` }] : []),
              ]}
              height={50}
              axisFormatter={(ts) => fmtSystemAxisTs(ts, range)}
            />
            <div style={{ marginTop: 8, fontSize: 11, color: '#6E6E73' }}>
              GPU 总体：{system?.gpu_total_label || system?.gpu_name || '未检测'}
            </div>
            {gpuTrend.length <= 1 && modelGpuTrend.length <= 1 && (
              <div style={{ color: '#AEAEB2', fontSize: 11, marginTop: 6 }}>当前范围仅 1 个 GPU 采样点。</div>
            )}
          </>
        ) : (
          <div style={{ color: '#AEAEB2', fontSize: 12, textAlign: 'center', padding: '12px 0' }}>
            {system?.gpu_name ? `已检测到 ${system.gpu_name}，但当前范围内暂无 GPU 利用率采样。` : '当前设备未返回 GPU 利用率数据'}
          </div>
        )}
      </div>

      {knowledgeEvents.length > 0 && (
        <div style={cardStyle}>
          <div style={sectionTitle}>知识提炼触发与资源时间轴</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
            {knowledgeEvents.map((item, index) => (
              <span key={`${item.ts}-${index}`} style={{ fontSize: 11, padding: '2px 8px', borderRadius: 10, background: 'rgba(191,90,242,0.10)', color: '#BF5AF2' }}>
                {fmtAxisTs(item.ts)} · {item.count} 条
              </span>
            ))}
          </div>
          <div style={{ fontSize: 11, color: '#AEAEB2' }}>结合系统 / 整套软件 / 模型趋势，可观察知识提炼触发时段与资源波动关系。</div>
        </div>
      )}

      <div style={cardStyle}>
        <div style={sectionTitle}>磁盘 IO（MB）</div>
        {disk_trend.length > 1 ? (
          <>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: '#34C759', marginBottom: 4 }}>读取</div>
                <SparkLine
                  data={disk_trend.map(p => ({ ts: p.ts, value: p.read_mb }))}
                  color="#34C759"
                  height={40}
                  valueFormatter={(value) => `${value.toFixed(2)} MB`}
                  axisFormatter={(ts) => fmtSystemAxisTs(ts, range)}
                />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: '#FF3B30', marginBottom: 4 }}>写入</div>
                <SparkLine
                  data={disk_trend.map(p => ({ ts: p.ts, value: p.write_mb }))}
                  color="#FF3B30"
                  height={40}
                  valueFormatter={(value) => `${value.toFixed(2)} MB`}
                  axisFormatter={(ts) => fmtSystemAxisTs(ts, range)}
                />
              </div>
            </div>
          </>
        ) : <div style={{ color: '#AEAEB2', fontSize: 12, textAlign: 'center', padding: '12px 0' }}>暂无数据</div>}
      </div>

      <div style={{ ...cardStyle, marginBottom: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
          <span style={sectionTitle as any}>模型加载/卸载事件</span>
          {model_events.length > eventPageSize && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button
                onClick={() => setEventPage((page) => Math.max(1, page - 1))}
                disabled={eventPage === 1}
                style={{ fontSize: 11, padding: '3px 8px', borderRadius: 6, border: '1px solid rgba(0,0,0,0.1)', background: eventPage === 1 ? '#F2F2F7' : 'white', color: '#6E6E73', cursor: eventPage === 1 ? 'default' : 'pointer' }}
              >上一页</button>
              <span style={{ fontSize: 11, color: '#6E6E73' }}>{eventPage} / {totalEventPages}</span>
              <button
                onClick={() => setEventPage((page) => Math.min(totalEventPages, page + 1))}
                disabled={eventPage === totalEventPages}
                style={{ fontSize: 11, padding: '3px 8px', borderRadius: 6, border: '1px solid rgba(0,0,0,0.1)', background: eventPage === totalEventPages ? '#F2F2F7' : 'white', color: '#6E6E73', cursor: eventPage === totalEventPages ? 'default' : 'pointer' }}
              >下一页</button>
            </div>
          )}
        </div>
        {model_events.length === 0
          ? <div style={{ color: '#AEAEB2', fontSize: 12 }}>暂无事件</div>
          : pagedModelEvents.map((e, i) => (
            <div key={`${e.ts}-${e.model_name}-${i}`} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0',
              borderBottom: i < pagedModelEvents.length - 1 ? '1px solid rgba(0,0,0,0.05)' : 'none' }}>
              <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, flexShrink: 0,
                background: `${EVENT_COLOR[e.event_type] || '#6E6E73'}18`,
                color: EVENT_COLOR[e.event_type] || '#6E6E73' }}>
                {EVENT_LABEL[e.event_type] || e.event_type}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <span style={{ fontSize: 12, color: '#333' }}>{e.model_name}</span>
                <span style={{ fontSize: 11, color: '#AEAEB2', marginLeft: 6 }}>{e.model_type}</span>
              </div>
              <div style={{ flexShrink: 0, fontSize: 11, color: '#6E6E73', textAlign: 'right' }}>
                {e.duration_ms && <span>{fmtMs(e.duration_ms)} · </span>}
                {e.memory_mb && <span>{e.memory_mb} MB · </span>}
                <span>{fmtTs(e.ts)}</span>
              </div>
            </div>
          ))}
      </div>
    </>
  )
}

const ErrorNotice: React.FC<{ message: string }> = ({ message }) => (
  <div style={{
    background: 'rgba(255,59,48,0.08)',
    border: '1px solid rgba(255,59,48,0.16)',
    color: '#C62828',
    borderRadius: 10,
    padding: '10px 12px',
    marginBottom: 10,
    fontSize: 12,
    lineHeight: 1.5,
  }}>
    监控数据加载失败：{message}
  </div>
)

// ── 主组件 ──────────────────────────────────────────────────────────────────
const MonitorPanel: React.FC = () => {
  const { apiBaseUrl } = useAppStore()
  const base = apiBaseUrl || API

  const [tab, setTab] = useState<'overview' | 'system'>('overview')
  const [data, setData] = useState<MonitorOverview | null>(null)
  const [sysData, setSysData] = useState<SystemResources | null>(null)
  const [range, setRange] = useState<OverviewRange>('7d')
  const [sysRange, setSysRange] = useState<SystemRange>('6h')
  const [loading, setLoading] = useState(false)
  const [overviewError, setOverviewError] = useState<string | null>(null)
  const [systemError, setSystemError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setOverviewError(null)
    try {
      const res = await fetch(`${base}/api/monitor/overview?range=${range}`)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }
      const json = await res.json()
      setData(json)
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      setData(null)
      setOverviewError(message)
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const loadSys = async () => {
    setLoading(true)
    setSystemError(null)
    try {
      const res = await fetch(`${base}/api/monitor/system?range=${sysRange}`)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }
      const json = await res.json()
      setSysData(json)
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      setSysData(null)
      setSystemError(message)
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (tab === 'overview') load() }, [base, range, tab])
  useEffect(() => { if (tab === 'system') loadSys() }, [base, sysRange, tab])

  if (loading && !data && !sysData && !overviewError && !systemError) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100%', color: '#AEAEB2', fontSize: 13 }}>加载中...</div>
  )

  return (
    <div style={{ height: '100%', overflow: 'auto', background: '#F5F5F7', padding: '16px 20px' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 10 }}>
        <div style={{ display: 'flex', gap: 4 }}>
          {(['overview', 'system'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              fontSize: 12, padding: '4px 10px', borderRadius: 7, border: 'none', cursor: 'pointer',
              background: tab === t ? '#007AFF' : 'white',
              color: tab === t ? 'white' : '#6E6E73',
              fontWeight: tab === t ? 600 : 400,
            }}>{t === 'overview' ? '总览' : '系统资源'}</button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {tab === 'overview' && (['1d', '7d', '30d'] as const).map(r => (
            <button key={r} onClick={() => setRange(r)} style={{
              fontSize: 11, padding: '3px 8px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: range === r ? '#007AFF' : 'white',
              color: range === r ? 'white' : '#6E6E73',
            }}>{r === '1d' ? '今天' : r === '7d' ? '7天' : '30天'}</button>
          ))}
          {tab === 'system' && (['1h', '6h', '24h'] as const).map(r => (
            <button key={r} onClick={() => setSysRange(r)} style={{
              fontSize: 11, padding: '3px 8px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: sysRange === r ? '#007AFF' : 'white',
              color: sysRange === r ? 'white' : '#6E6E73',
            }}>{r}</button>
          ))}
          <button onClick={tab === 'overview' ? load : loadSys} style={{
            fontSize: 11, padding: '3px 8px', borderRadius: 6, border: '1px solid rgba(0,0,0,0.1)',
            background: 'white', color: '#6E6E73', cursor: 'pointer',
          }}>刷新</button>
        </div>
      </div>

      {tab === 'overview' && overviewError && <ErrorNotice message={`${overviewError}，请检查 API 地址或确认 Core Engine 已启动`} />}
      {tab === 'system' && systemError && <ErrorNotice message={`${systemError}，请检查 API 地址或确认 Core Engine 已启动`} />}

      {tab === 'overview' && data && <OverviewContent data={data} range={range} />}
      {tab === 'overview' && !data && !overviewError && !loading && (
        <div style={{ color: '#AEAEB2', fontSize: 12, textAlign: 'center', padding: '24px 0' }}>暂无监控数据</div>
      )}
      {tab === 'system' && <SystemContent data={sysData} range={sysRange} />}

    </div>
  )
}

const cardStyle: React.CSSProperties = {
  background: 'white', borderRadius: 12, padding: '12px 14px',
  border: '1px solid rgba(0,0,0,0.07)', marginBottom: 10,
}

const sectionTitle: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, color: '#333', marginBottom: 10, display: 'block',
}

export default MonitorPanel
