import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // Casa só /api/... — com '/api' o prefixo pegaria /api.ts, que é um
      // módulo deste próprio cliente, e o Vite o mandaria para o motor.
      '^/api/': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: (request) => request.url?.endsWith('.ts') ? request.url : undefined,
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
  },
  test: {
    environment: 'jsdom',
    setupFiles: './vitest.setup.ts',
    globals: true,
  },
})
