import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listBooks } from './api'
import type { Book } from './types'
import LoadingIndicator from './LoadingIndicator'

type ToolHeaderProps = {
  mode?: 'profile'
}

export default function ToolHeader({ mode }: ToolHeaderProps) {
  const [books, setBooks] = useState<Book[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void listBooks()
      .then(setBooks)
      .catch(() => setBooks([]))
      .finally(() => setLoading(false))
  }, [])

  const chunks = books.reduce((total, book) => total + (book.n_chunks ?? 0), 0)

  return (
    <header className="tool-header">
      <div className="brand-block">
        <p className="brand-name">Sabiá</p>
        <p className="brand-tagline">Conexões entre livros</p>
      </div>

      {loading ? (
        <LoadingIndicator label="Carregando acervo" compact />
      ) : (
        <p className="library-summary">
          {books.length} {books.length === 1 ? 'livro' : 'livros'} · {chunks} trechos
        </p>
      )}

      <Link to="/perfil" className={mode === 'profile' ? 'profile-link active' : 'profile-link'} aria-label="Abrir perfil" title="Perfil">
        ◌
      </Link>
    </header>
  )
}
