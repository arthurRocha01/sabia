import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { createClient, type Session } from '@supabase/supabase-js'
import { sessionKey, tokenKey } from '../storage'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || ''
const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || ''
export const supabase = supabaseUrl && supabaseKey ? createClient(supabaseUrl, supabaseKey) : null

type SessionContextValue = {
  hasSession: boolean
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => void
}

const SessionContext = createContext<SessionContextValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [hasSession, setHasSession] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return localStorage.getItem(sessionKey) === 'active'
  })

  const signOut = () => {
    localStorage.removeItem(sessionKey)
    localStorage.removeItem(tokenKey)
    setHasSession(false)
  }

  useEffect(() => {
    if (!supabase) return

    void supabase.auth.getSession().then(({ data }) => {
      if (data.session?.access_token) {
        localStorage.setItem(tokenKey, data.session.access_token)
      }
    })

    const { data: assinatura } = supabase.auth.onAuthStateChange((_evento, sessao: Session | null) => {
      if (sessao?.access_token) {
        localStorage.setItem(tokenKey, sessao.access_token)
      } else {
        signOut()
      }
    })

    return () => assinatura.subscription.unsubscribe()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const sair = () => signOut()
    window.addEventListener('sabia:session-expired', sair)
    return () => window.removeEventListener('sabia:session-expired', sair)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const value = useMemo<SessionContextValue>(() => ({
    hasSession,
    signIn: async (email, password) => {
      if (!supabase) {
        throw new Error('Configure VITE_SUPABASE_URL e VITE_SUPABASE_PUBLISHABLE_KEY antes de entrar.')
      }

      const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      if (error || !data.session) {
        throw error ?? new Error('Sessão não criada.')
      }

      localStorage.setItem(sessionKey, 'active')
      localStorage.setItem(tokenKey, data.session.access_token)
      setHasSession(true)
    },
    signOut,
  }), [hasSession])

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession() {
  const context = useContext(SessionContext)
  if (!context) throw new Error('useSession deve ser usado dentro de SessionProvider.')
  return context
}
