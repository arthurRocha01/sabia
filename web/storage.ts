/**
 * As chaves do armazenamento local do cliente, num lugar só.
 *
 * Quem grava e quem lê precisam concordar: enquanto as duas pontas escrevem a
 * mesma string à mão, renomear uma delas não dá erro de tipo — dá sessão que
 * não autentica mais, ou livro que nunca retoma a página.
 */
export const sessionKey = 'sabia_session'
export const tokenKey = 'sabia_token'

/** A última página lida de cada livro. */
export const readerPageKey = (bookId: string) => `sabia_reader_page:${bookId}`

/** A última consulta feita em cada livro. */
export const consultationKey = (bookId: string) => `sabia_last_consultation:${bookId}`
