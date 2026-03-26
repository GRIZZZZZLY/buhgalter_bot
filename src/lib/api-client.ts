import { getInitData } from './telegram'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api-proxy'

function buildHeaders(): Record<string, string> {
  const initData = getInitData()
  if (initData) {
    return {
      'Content-Type': 'application/json',
      'X-Telegram-Init-Data': initData,
    }
  }
  // Dev fallback: backend accepts X-Telegram-User-Id when TELEGRAM_BOT_TOKEN is empty
  return {
    'Content-Type': 'application/json',
    'X-Telegram-User-Id': import.meta.env.VITE_DEV_USER_ID ?? '0',
  }
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...buildHeaders(),
      ...(init?.headers ?? {}),
    },
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // ignore parse error
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
