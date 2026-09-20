import { Link } from 'react-router-dom'
import type { Book } from '../api/types'
import Indicador from './Indicador'

type CabecalhoProps = {
  books: Book[]
  loading?: boolean
  mode?: 'profile'
}

export default function Cabecalho({ books, loading = false, mode }: CabecalhoProps) {
  const chunks = books.reduce((total, book) => total + (book.n_chunks ?? 0), 0)

  return (
    <header className="tool-header">
      <div className="brand-block">
        <p className="brand-name">Sabiá</p>
        <p className="brand-tagline">Conexões entre livros</p>
      </div>

      {loading ? (
        <Indicador label="Carregando acervo" compact />
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
