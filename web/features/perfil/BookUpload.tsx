import type { FormEvent } from 'react'

/** O envio de um PDF: arquivo, título e autor. O estado e a chamada são da página. */
export default function BookUpload({
  busy,
  onSubmit,
}: {
  busy: boolean
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
  return (
    <form className="upload-form" onSubmit={onSubmit}>
      <label className="field-group">
        <span>Arquivo PDF</span>
        <input type="file" name="file" accept="application/pdf" required />
      </label>
      <label className="field-group">
        <span>Título</span>
        <input type="text" name="title" placeholder="Título do livro" required />
      </label>
      <label className="field-group">
        <span>Autor</span>
        <input type="text" name="author" placeholder="Autor" required />
      </label>
      <button type="submit" className="primary-button" disabled={busy}>
        {busy ? 'Enviando…' : 'Enviar PDF'}
      </button>
    </form>
  )
}
