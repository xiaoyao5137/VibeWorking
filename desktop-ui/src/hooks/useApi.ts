/**
 * useApi — REST API 调用 Hooks
 *
 * 封装对 core-engine localhost:7070 的 HTTP 请求。
 * 测试时 fetch 可通过 vi.stubGlobal('fetch', ...) 注入 Mock。
 */

import { useCallback } from 'react'
import { useAppStore }  from '../store/useAppStore'
import type { CaptureRecord, PreferenceRecord, RagQueryResponse, ActionResult } from '../types'

// ── 健康检查 ──────────────────────────────────────────────────────────────────

export function useHealthCheck() {
  const apiBaseUrl = useAppStore((s) => s.apiBaseUrl)

  return useCallback(async (): Promise<{ status: string; version: string }> => {
    const resp = await fetch(`${apiBaseUrl}/health`)
    if (!resp.ok) throw new Error(`health check failed: ${resp.status}`)
    return resp.json()
  }, [apiBaseUrl])
}

// ── 采集记录 ──────────────────────────────────────────────────────────────────

export interface FetchCapturesParams {
  from?:  number
  to?:    number
  app?:   string
  q?:     string
  limit?: number
}

export function useFetchCaptures() {
  const apiBaseUrl = useAppStore((s) => s.apiBaseUrl)

  return useCallback(async (params: FetchCapturesParams = {}): Promise<{
    total: number
    captures: CaptureRecord[]
  }> => {
    const url   = new URL(`${apiBaseUrl}/captures`)
    if (params.from  != null) url.searchParams.set('from',  String(params.from))
    if (params.to    != null) url.searchParams.set('to',    String(params.to))
    if (params.app)            url.searchParams.set('app',   params.app)
    if (params.q)              url.searchParams.set('q',     params.q)
    if (params.limit != null)  url.searchParams.set('limit', String(params.limit))

    const resp = await fetch(url.toString())
    if (!resp.ok) throw new Error(`captures fetch failed: ${resp.status}`)
    return resp.json()
  }, [apiBaseUrl])
}

// ── RAG 查询 ──────────────────────────────────────────────────────────────────

export function useRagQuery() {
  const apiBaseUrl   = useAppStore((s) => s.apiBaseUrl)
  const setLoading   = useAppStore((s) => s.setRagLoading)
  const setResult    = useAppStore((s) => s.setRagResult)
  const setError     = useAppStore((s) => s.setRagError)

  return useCallback(async (query: string, topK = 5): Promise<RagQueryResponse> => {
    setLoading(true)
    try {
      const resp = await fetch(`${apiBaseUrl}/query`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ query, top_k: topK }),
      })
      if (!resp.ok) {
        const err = await resp.text()
        throw new Error(`query failed: ${resp.status} ${err}`)
      }
      const data: RagQueryResponse = await resp.json()
      setResult(data.answer, data.contexts ?? [])
      return data
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      throw err
    }
  }, [apiBaseUrl, setLoading, setResult, setError])
}

// ── 偏好设置 ──────────────────────────────────────────────────────────────────

export function useFetchPreferences() {
  const apiBaseUrl = useAppStore((s) => s.apiBaseUrl)

  return useCallback(async (): Promise<PreferenceRecord[]> => {
    const resp = await fetch(`${apiBaseUrl}/preferences`)
    if (!resp.ok) throw new Error(`preferences fetch failed: ${resp.status}`)
    const data = await resp.json()
    return data.preferences
  }, [apiBaseUrl])
}

export function useUpdatePreference() {
  const apiBaseUrl = useAppStore((s) => s.apiBaseUrl)

  return useCallback(async (key: string, value: string): Promise<PreferenceRecord> => {
    const resp = await fetch(`${apiBaseUrl}/preferences/${encodeURIComponent(key)}`, {
      method:  'PUT',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ value }),
    })
    if (!resp.ok) throw new Error(`update preference failed: ${resp.status}`)
    return resp.json()
  }, [apiBaseUrl])
}

// ── 执行动作 ──────────────────────────────────────────────────────────────────

export function useExecuteAction() {
  const apiBaseUrl = useAppStore((s) => s.apiBaseUrl)

  return useCallback(async (action: Record<string, unknown>): Promise<ActionResult> => {
    const resp = await fetch(`${apiBaseUrl}/action/execute`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(action),
    })
    if (!resp.ok) throw new Error(`execute action failed: ${resp.status}`)
    return resp.json()
  }, [apiBaseUrl])
}
