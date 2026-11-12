import type { VaultItem, VaultItemCreate, User } from './types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error((err as { detail?: string }).detail ?? 'Request failed')
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  login: (username: string, password: string) =>
    request<User>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  logout: () => request<void>('/auth/logout', { method: 'POST' }),

  me: () => request<User>('/auth/me'),

  items: {
    list: () => request<VaultItem[]>('/vault/items'),
    create: (item: VaultItemCreate) =>
      request<VaultItem>('/vault/items', {
        method: 'POST',
        body: JSON.stringify(item),
      }),
    update: (id: string, item: VaultItemCreate) =>
      request<VaultItem>(`/vault/items/${id}`, {
        method: 'PUT',
        body: JSON.stringify(item),
      }),
    delete: (id: string) =>
      request<void>(`/vault/items/${id}`, { method: 'DELETE' }),
  },
}
