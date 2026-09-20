import { apiFetch } from './client'
import type { ConnectRequest, ConnectResponse } from './types'

export async function connect(payload: ConnectRequest): Promise<ConnectResponse> {
  return apiFetch<ConnectResponse>('/connect', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
