import { apiFetch } from './client'
import type { CardLength, Profile } from './types'

export async function getProfile(): Promise<Profile> {
  return apiFetch<Profile>('/profile')
}

/** Muda só o que foi informado: campo ausente não é tocado no motor. */
export async function updateProfile(changes: {
  current_line?: string
  card_length?: CardLength
  interpretation_profile?: string
}): Promise<Profile> {
  return apiFetch<Profile>('/profile', {
    method: 'PATCH',
    body: JSON.stringify(changes),
  })
}
