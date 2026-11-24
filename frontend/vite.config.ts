import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

/**
 * Every VITE_* variable is copied into the public JavaScript bundle that anyone can read. Fail the build
 * if one looks like a secret (by name or by value) so a token or database URL can never be shipped by accident.
 * The only variable this app needs is the public backend URL, VITE_API_BASE_URL.
 */
function assertNoSecretsInPublicEnv(env: Record<string, string>) {
  const secretName = /(TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE|CREDENTIAL|DATABASE|API_?KEY)/i
  const secretValue = /(ghp_|gho_|github_pat_|postgres(ql)?:\/\/[^/\s]*:[^@\s]+@)/i
  const bad = Object.entries(env)
    .filter(([key, value]) => secretName.test(key) || secretValue.test(value))
    .map(([key]) => key)
  if (bad.length > 0) {
    throw new Error(
      `Refusing to build: ${bad.join(', ')} would be embedded in the public JavaScript bundle. ` +
        'Keep secrets (GitHub token, database URL) in the backend only; the frontend needs just VITE_API_BASE_URL.',
    )
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  assertNoSecretsInPublicEnv(loadEnv(mode, process.cwd(), 'VITE_'))
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      // Development only: the browser only ever talks to the FastAPI backend (never to GitHub), via this proxy.
      // Production builds call VITE_API_BASE_URL directly.
      proxy: { '/api': 'http://localhost:8000' },
    },
    test: {
      environment: 'jsdom',
      globals: false,
      setupFiles: ['./src/test/setup.ts'],
      css: false,
    },
  }
})
