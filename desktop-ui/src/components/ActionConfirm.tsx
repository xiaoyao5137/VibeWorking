/**
 * ActionConfirm — 接管确认弹窗
 *
 * AI 即将执行键鼠操作时，弹出此对话框要求用户确认。
 * 提供「确认执行」和「取消」两个选项。
 * 支持倒计时自动取消（防止误触）。
 */

import React, { useCallback, useEffect, useState } from 'react'
import { useAppStore } from '../store/useAppStore'
import type { ActionCommand } from '../types'

interface ActionConfirmProps {
  /** 用户确认后的回调（执行动作） */
  onConfirm?: (action: ActionCommand) => Promise<void>
  /** 倒计时秒数，0 表示不自动取消（默认 10s） */
  autoCancel?: number
  className?: string
}

const ActionConfirm: React.FC<ActionConfirmProps> = ({
  onConfirm,
  autoCancel = 10,
  className = '',
}) => {
  const {
    pendingAction,
    confirmAction,
    cancelAction,
  } = useAppStore()

  const [countdown, setCountdown] = useState(autoCancel)
  const [isExecuting, setIsExecuting] = useState(false)

  // 倒计时逻辑
  useEffect(() => {
    if (!pendingAction || autoCancel === 0) return
    setCountdown(autoCancel)

    const timer = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          clearInterval(timer)
          cancelAction()
          return 0
        }
        return c - 1
      })
    }, 1000)

    return () => clearInterval(timer)
  }, [pendingAction, autoCancel, cancelAction])

  const handleConfirm = useCallback(async () => {
    if (!pendingAction) return
    confirmAction()
    if (onConfirm) {
      setIsExecuting(true)
      try {
        await onConfirm(pendingAction)
      } finally {
        setIsExecuting(false)
      }
    }
  }, [pendingAction, confirmAction, onConfirm])

  const handleCancel = useCallback(() => {
    cancelAction()
  }, [cancelAction])

  if (!pendingAction) return null

  return (
    <div
      className={`action-confirm-overlay ${className}`}
      data-testid="action-confirm-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="动作确认对话框"
    >
      <div className="action-confirm-dialog" data-testid="action-confirm-dialog">
        {/* 标题 */}
        <h2 className="action-confirm__title" data-testid="action-confirm-title">
          🤖 工作搭子需要接管操控
        </h2>

        {/* 动作描述 */}
        <div className="action-confirm__action" data-testid="action-confirm-action">
          <strong>即将执行：</strong>
          <span>{pendingAction.description ?? pendingAction.type}</span>
        </div>

        {/* 详细信息 */}
        <div className="action-confirm__details" data-testid="action-confirm-details">
          <pre>{JSON.stringify(pendingAction, null, 2)}</pre>
        </div>

        {/* 警告 */}
        <div className="action-confirm__warning" data-testid="action-confirm-warning" role="alert">
          ⚠️ 确认后 AI 将直接操控键盘/鼠标，请确认目标应用已准备好。
        </div>

        {/* 操作按钮 */}
        <div className="action-confirm__buttons">
          <button
            className="action-confirm__btn action-confirm__btn--cancel"
            data-testid="action-cancel-btn"
            onClick={handleCancel}
            type="button"
            disabled={isExecuting}
          >
            取消
            {autoCancel > 0 && ` (${countdown}s)`}
          </button>
          <button
            className="action-confirm__btn action-confirm__btn--confirm"
            data-testid="action-confirm-btn"
            onClick={handleConfirm}
            type="button"
            disabled={isExecuting}
            aria-busy={isExecuting}
          >
            {isExecuting ? '执行中…' : '确认执行'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default ActionConfirm
