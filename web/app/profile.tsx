import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { formatError } from '../api/client'
import { getProfile, updateProfile } from '../api/profile'
import type { CardLength, Profile } from '../api/types'
import { useSession } from './session'

type ProfileContextValue = {
  profile: Profile | null
  loading: boolean
  error: string
  refreshProfile: () => Promise<Profile>
  saveProfile: (changes: {
    current_line?: string
    card_length?: CardLength
    interpretation_profile?: string
  }) => Promise<Profile>
  clearError: () => void
}

const ProfileContext = createContext<ProfileContextValue | null>(null)

export function ProfileProvider({ children }: { children: ReactNode }) {
  const { hasSession } = useSession()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refreshProfile = async () => {
    setLoading(true)
    try {
      const next = await getProfile()
      setProfile(next)
      setError('')
      return next
    } catch (caught) {
      const message = formatError(caught)
      setError(message)
      throw caught
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!hasSession) {
      setProfile(null)
      setLoading(false)
      return
    }
    void refreshProfile()
  }, [hasSession])

  const value = useMemo<ProfileContextValue>(() => ({
    profile,
    loading,
    error,
    refreshProfile,
    saveProfile: async (changes) => {
      try {
        const next = await updateProfile(changes)
        setProfile(next)
        setError('')
        return next
      } catch (caught) {
        setError(formatError(caught))
        throw caught
      }
    },
    clearError: () => setError(''),
  }), [error, loading, profile])

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>
}

export function useProfile() {
  const context = useContext(ProfileContext)
  if (!context) throw new Error('useProfile deve ser usado dentro de ProfileProvider.')
  return context
}
