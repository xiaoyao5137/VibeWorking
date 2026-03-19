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

  // ── 首次引导 ─────────────────────────────────────────────────────────────────
  hasCompletedSetup: boolean
  setupSkipped:      boolean

  // ── 操作方法 ─────────────────────────────────────────────────────────────────
  setWindowMode:         (mode: WindowMode) => void
  setRagQuery:           (q: string) => void
  setRagResult:          (answer: string, contexts: RagContext[]) => void
  setRagLoading:         (loading: boolean) => void
  setRagError:           (err: string | null) => void
  setPendingAction:      (action: ActionCommand | null) => void
  confirmAction:         () => void
  cancelAction:          () => void
  setApiBaseUrl:         (url: string) => void
  setSidecarVersion:     (v: string) => void
  setHasCompletedSetup:  (v: boolean) => void
  setSetupSkipped:       (v: boolean) => void
  reset:                 () => void
}

const SETUP_KEY = 'workbuddy_setup_done'
const SKIP_KEY  = 'workbuddy_setup_skipped'

const initialState = {
  windowMode:          'rag' as WindowMode,
  ragQuery:            '',
  ragAnswer:           '',
  ragContexts:         [] as RagContext[],
  ragLoading:          false,
  ragError:            null,
  pendingAction:       null,
  actionConfirmed:     false,
  apiBaseUrl:          'http://localhost:7070',
  sidecarVersion:      '0.1.0',
  hasCompletedSetup:   localStorage.getItem(SETUP_KEY) === 'true',
  setupSkipped:        localStorage.getItem(SKIP_KEY)  === 'true',
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

  setHasCompletedSetup: (v) => {
    localStorage.setItem(SETUP_KEY, String(v))
    set({ hasCompletedSetup: v })
  },

  setSetupSkipped: (v) => {
    localStorage.setItem(SKIP_KEY, String(v))
    set({ setupSkipped: v })
  },

  reset: () => set(initialState),
}))
