/**
 * useAppStore — 全局应用状态（Zustand）
 *
 * 管理：
 * - 当前显示的窗口模式（buddy / rag / settings）
 * - RAG Panel 查询与响应状态
 * - 待执行动作（Action Confirm 弹窗）
 * - 应用配置
 */

import { create } from 'zustand'
import type { ActionCommand, RagContext, WindowMode } from '../types'

export interface AppState {
  // ── 窗口模式 ────────────────────────────────────────────────────────────────
  windowMode: WindowMode

  // ── RAG Panel ───────────────────────────────────────────────────────────────
  ragQuery:     string
  ragAnswer:    string
  ragContexts:  RagContext[]
  ragLoading:   boolean
  ragError:     string | null

  // ── Action Confirm ──────────────────────────────────────────────────────────
  pendingAction:    ActionCommand | null
  actionConfirmed:  boolean

  // ── 全局配置 ─────────────────────────────────────────────────────────────────
  apiBaseUrl:     string
  sidecarVersion: string

  // ── 操作方法 ─────────────────────────────────────────────────────────────────
  setWindowMode:    (mode: WindowMode) => void
  setRagQuery:      (q: string) => void
  setRagResult:     (answer: string, contexts: RagContext[]) => void
  setRagLoading:    (loading: boolean) => void
  setRagError:      (err: string | null) => void
  setPendingAction: (action: ActionCommand | null) => void
  confirmAction:    () => void
  cancelAction:     () => void
  setApiBaseUrl:    (url: string) => void
  setSidecarVersion:(v: string) => void
  reset:            () => void
}

const initialState = {
  windowMode:       'rag'  as WindowMode,  // 默认打开 RAG 问答页面
  ragQuery:         '',
  ragAnswer:        '',
  ragContexts:      [] as RagContext[],
  ragLoading:       false,
  ragError:         null,
  pendingAction:    null,
  actionConfirmed:  false,
  apiBaseUrl:       'http://localhost:7070',
  sidecarVersion:   '0.1.0',
}

export const useAppStore = create<AppState>((set) => ({
  ...initialState,

  setWindowMode: (mode) => set({ windowMode: mode }),

  setRagQuery:   (q) => set({ ragQuery: q }),

  setRagResult:  (answer, contexts) => set({
    ragAnswer:  answer,
    ragContexts: contexts,
    ragLoading:  false,
    ragError:    null,
  }),

  setRagLoading: (loading) => set({ ragLoading: loading }),

  setRagError:   (err) => set({ ragError: err, ragLoading: false }),

  setPendingAction: (action) => set({
    pendingAction:   action,
    actionConfirmed: false,
  }),

  confirmAction: () => set({ actionConfirmed: true }),

  cancelAction:  () => set({
    pendingAction:   null,
    actionConfirmed: false,
  }),

  setApiBaseUrl:     (url) => set({ apiBaseUrl: url }),

  setSidecarVersion: (v) => set({ sidecarVersion: v }),

  reset: () => set(initialState),
}))
