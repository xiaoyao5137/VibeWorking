// ─────────────────────────────────────────────────────────────────────────────
// 共享类型定义（与 core-engine REST API 对齐）
// ─────────────────────────────────────────────────────────────────────────────

export interface CaptureRecord {
  id:             number
  ts:             number
  app_name:       string | null
  app_bundle_id:  string | null
  win_title:      string | null
  event_type:     string
  ax_text:        string | null
  ocr_text:       string | null
  input_text:     string | null
  audio_text:     string | null
  is_sensitive:   boolean
  pii_scrubbed:   boolean
  screenshot_path:string | null
  knowledge?:     {
    id:               number
    summary:          string
    overview?:        string  // 概述
    details?:         string  // 明细
    entities:         string[]
    category:         string
    importance:       number
    occurrence_count?: number  // 出现次数
  } | null
}

export interface PreferenceRecord {
  id:         number
  key:        string
  value:      string
  source:     string
  confidence: number
  updated_at: number
}

export interface RagQueryResponse {
  answer:   string
  contexts: RagContext[]
  model:    string
}

export interface RagContext {
  capture_id: number
  text:       string
  score:      number
  source:     'fts5' | 'vector' | 'merged'
}

export interface ActionCommand {
  type:        'click' | 'right_click' | 'double_click' | 'move_to' | 'type_text' | 'hotkey' | 'key_press' | 'scroll' | 'wait' | 'sequence'
  x?:          number
  y?:          number
  text?:       string
  keys?:       string[]
  key?:        string
  delta_y?:    number
  ms?:         number
  steps?:      ActionCommand[]
  description?:string
}

export interface ActionResult {
  success:     boolean
  message:     string
  action_id:   string
}

export type WindowMode = 'buddy' | 'rag' | 'knowledge' | 'models' | 'settings' | 'debug' | 'tasks'

// ─────────────────────────────────────────────────────────────────────────────
// 定时任务
// ─────────────────────────────────────────────────────────────────────────────

export interface ScheduledTask {
  id:               number
  name:             string
  user_instruction: string
  cron_expression:  string
  enabled:          boolean
  template_id:      string | null
  run_count:        number
  last_run_at:      number | null
  last_run_status:  string | null
  next_run_at:      number | null
  created_at:       number
  updated_at:       number
}

export interface TaskExecution {
  id:              number
  task_id:         number
  started_at:      number
  completed_at:    number | null
  status:          'running' | 'success' | 'failed'
  knowledge_count: number | null
  token_used:      number | null
  result_text:     string | null
  error_message:   string | null
  latency_ms:      number | null
}

export interface TaskTemplate {
  id:               string
  name:             string
  cron:             string
  category:         string
  user_instruction: string
}
