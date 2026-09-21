import { describe, expect, it } from 'vitest'
import { formatError } from './client'
import { consultationKey, readerPageKey, sessionKey, tokenKey } from '../storage'

describe('formatError', () => {
  it('usa a mensagem do contrato quando ela vem', () => {
    expect(formatError({ code: 'quota_exceeded', message: 'A cota do dia acabou.' })).toBe(
      'A cota do dia acabou.',
    )
  })

  it('cai no texto padrão quando não há mensagem', () => {
    const padrao = 'Não foi possível concluir a operação.'
    expect(formatError(undefined)).toBe(padrao)
    expect(formatError('falhou')).toBe(padrao)
    expect(formatError(new Error(''))).toBe(padrao)
  })

  it('deixa passar a mensagem de um erro comum, que não é do contrato', () => {
    expect(formatError(new Error('Sessão não criada.'))).toBe('Sessão não criada.')
  })
})

describe('chaves do armazenamento', () => {
  it('são uma por livro, e não se confundem com as da sessão', () => {
    expect(readerPageKey('a')).not.toBe(consultationKey('a'))
    expect(consultationKey('a')).not.toBe(consultationKey('b'))
    expect([readerPageKey('a'), consultationKey('a')]).not.toContain(tokenKey)
    expect(sessionKey).not.toBe(tokenKey)
  })
})
