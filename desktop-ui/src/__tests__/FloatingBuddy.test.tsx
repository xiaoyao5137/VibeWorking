/**
 * FloatingBuddy 组件测试
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import FloatingBuddy from '../components/FloatingBuddy'
import { useAppStore } from '../store/useAppStore'

beforeEach(() => {
  useAppStore.getState().reset()
})

describe('FloatingBuddy', () => {
  it('渲染搭子头像', () => {
    render(<FloatingBuddy />)
    expect(screen.getByTestId('buddy-avatar')).toBeInTheDocument()
  })

  it('渲染设置按钮', () => {
    render(<FloatingBuddy />)
    expect(screen.getByTestId('settings-btn')).toBeInTheDocument()
  })

  it('初始状态不显示状态点（buddy 模式）', () => {
    render(<FloatingBuddy />)
    expect(screen.queryByTestId('buddy-status-dot')).not.toBeInTheDocument()
  })

  it('点击主体切换到 rag 模式', () => {
    render(<FloatingBuddy />)
    fireEvent.click(screen.getByTestId('floating-buddy'))
    expect(useAppStore.getState().windowMode).toBe('rag')
  })

  it('rag 模式下点击切换回 buddy 模式', () => {
    useAppStore.getState().setWindowMode('rag')
    render(<FloatingBuddy />)
    fireEvent.click(screen.getByTestId('floating-buddy'))
    expect(useAppStore.getState().windowMode).toBe('buddy')
  })

  it('rag 模式下显示状态点', () => {
    useAppStore.getState().setWindowMode('rag')
    render(<FloatingBuddy />)
    expect(screen.getByTestId('buddy-status-dot')).toBeInTheDocument()
  })

  it('点击设置按钮切换到 settings 模式', () => {
    render(<FloatingBuddy />)
    fireEvent.click(screen.getByTestId('settings-btn'))
    expect(useAppStore.getState().windowMode).toBe('settings')
  })

  it('设置按钮点击不触发主体点击（事件冒泡阻止）', () => {
    render(<FloatingBuddy />)
    fireEvent.click(screen.getByTestId('settings-btn'))
    // 应为 settings，不是 rag
    expect(useAppStore.getState().windowMode).toBe('settings')
  })

  it('接受自定义 className', () => {
    render(<FloatingBuddy className="custom-class" />)
    expect(screen.getByTestId('floating-buddy')).toHaveClass('custom-class')
  })
})
