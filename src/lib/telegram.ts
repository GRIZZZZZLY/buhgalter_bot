/**
 * Telegram Mini App SDK helpers.
 * Uses @tma.js/sdk-react v3 — signal-based, no SDKProvider.
 *
 * Call initTelegramApp() once before React renders (in main.tsx).
 */
import {
  init,
  backButton,
  mainButton,
  themeParams,
  viewport,
  miniApp,
  retrieveLaunchParams,
} from '@tma.js/sdk-react'

let initialized = false

export function initTelegramApp(): void {
  if (initialized) return
  initialized = true

  try {
    init()
    miniApp.mount()
    themeParams.mount()
    viewport.mount()
    backButton.mount()
    mainButton.mount()
  } catch (err) {
    // Running outside Telegram (browser dev) — gracefully ignore
    console.warn('[TMA] Running outside Telegram WebApp:', err)
  }
}

export function getInitData(): string {
  try {
    const params = retrieveLaunchParams()
    return String(params.initDataRaw ?? '')
  } catch {
    return ''
  }
}

export function isTelegramEnv(): boolean {
  try {
    retrieveLaunchParams()
    return true
  } catch {
    return false
  }
}

export { backButton, mainButton, themeParams, viewport, miniApp }
