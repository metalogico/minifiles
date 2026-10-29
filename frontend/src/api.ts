export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: any,
  ) {
    super(typeof detail === 'string' ? detail : detail?.message || 'The operation failed.')
  }
}

export async function api<T = any>(
  path: string,
  method = 'GET',
  data?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch('/api' + path, {
    method,
    signal,
    headers: {
      'X-MiniFiles': '1',
      ...(data === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }),
  })
  const result = await response.json()
  if (!response.ok) throw new ApiError(response.status, result.detail)
  return result
}

export const bytes = (amount: number | null | undefined) => {
  if (amount === null || amount === undefined) return '—'
  if (!amount) return '0 B'
  const unitIndex = Math.min(Math.floor(Math.log(amount) / Math.log(1024)), 4)
  const formatted = new Intl.NumberFormat('en-GB', {
    maximumFractionDigits: unitIndex ? 1 : 0,
  }).format(amount / 1024 ** unitIndex)
  const unit = ['B', 'KB', 'MB', 'GB', 'TB'][unitIndex]
  return `${formatted} ${unit}`
}
export const destination = (path: string) =>
  'Drive' + (path ? ' / ' + path.split('/').join(' / ') : '')
export interface Section {
  id: string
  name: string
  path: string
  color: string
}
export interface Entry {
  name: string
  kind: 'directory' | 'file' | 'blocked'
  size: number | null
  modified: number
}
export interface Stats {
  disk: { total: number; used: number; free: number; percent: number }
  sections: Record<string, { path: string; bytes: number; partial: boolean }>
  updated_at: number | null
  scanning: boolean
}
