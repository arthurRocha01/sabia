import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useProfile } from './profile'

type Precision = {
  /** A precisão escolhida; nula enquanto o floor da instalação não chegou. */
  minScore: number | null
  setMinScore: (valor: number | null) => void
  /**
   * O piso da instalação: o menor valor permitido. Nulo enquanto o perfil não
   * chega — e não zero, que seria um piso que a instalação não tem.
   */
  floor: number | null
}

const PrecisionContext = createContext<Precision | null>(null)

/**
 * A precisão da consulta vive aqui para ser a mesma em toda a ferramenta: quem
 * consulta pelo rail e quem consulta selecionando no livro usam o mesmo ajuste.
 */
export function PrecisionProvider({ children }: { children: ReactNode }) {
  const { profile } = useProfile()
  const floor = profile?.min_score_floor ?? null
  const [minScore, setMinScore] = useState<number | null>(null)

  useEffect(() => {
    if (floor === null) return
    setMinScore((escolhido) => escolhido ?? floor)
  }, [floor])

  return (
    <PrecisionContext.Provider value={{ minScore, setMinScore, floor }}>
      {children}
    </PrecisionContext.Provider>
  )
}

export function usePrecision(): Precision {
  const contexto = useContext(PrecisionContext)
  if (!contexto) throw new Error('usePrecision precisa do PrecisionProvider.')
  return contexto
}
