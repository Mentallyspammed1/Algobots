import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    // By default, Vite exposes env variables on `import.meta.env`.
    // This defines `process.env` so the Gemini SDK can access the API key.
    'process.env.API_KEY': JSON.stringify(process.env.VITE_API_KEY),
  }
})