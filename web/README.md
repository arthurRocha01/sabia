# Cliente

# Sabiá — cliente web

Aplicação em React + TypeScript para leitura, consulta e gestão do acervo do Sabiá.

## Variáveis de ambiente

Crie um arquivo `.env` com:

```
VITE_SUPABASE_URL=https://<projeto>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<chave-publica>
```

## Scripts

```
npm install
npm run dev
```

A aplicação conversa com o motor em `/api/*` e usa o Vite proxy configurado para `http://localhost:8000`.
