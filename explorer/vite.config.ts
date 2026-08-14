import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const apiTarget = process.env.VITE_EXPLORER_API_TARGET ?? 'http://127.0.0.1:8000'
const wsTarget = process.env.VITE_EXPLORER_WS_TARGET ?? apiTarget.replace(/^http/, 'ws')

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: ['babel-plugin-react-compiler'],
      },
    }),
  ],
 
  base: '/',
  build: {
    outDir: path.resolve(__dirname, '../semantica/static'),
    emptyOutDir: true,
    chunkSizeWarningLimit: 650,
    // Explicit target avoids esbuild attempting to lower syntax that all
    // modern browsers already support natively, which breaks with the
    // esbuild >=0.28 override when running under Vite 6 on Linux CI.
    target: 'esnext',
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = id.replaceAll('\\', '/')

          if (!normalizedId.includes('node_modules')) {
            return undefined
          }

          if (
            normalizedId.includes('/node_modules/sigma/') ||
            normalizedId.includes('/node_modules/graphology/') ||
            normalizedId.includes('/node_modules/graphology-layout-forceatlas2/')
          ) {
            return 'graph-vendor'
          }

          if (
            normalizedId.includes('/node_modules/vis-data/') ||
            normalizedId.includes('/node_modules/vis-timeline/')
          ) {
            return 'timeline-vendor'
          }

          if (normalizedId.includes('/node_modules/@tanstack/react-query/')) {
            return 'query-vendor'
          }

          return undefined
        },
      },
    },
  },
  optimizeDeps: {
    // Keep dependency pre-bundling aligned with the production build target.
    // esbuild >=0.28 no longer lowers destructuring for Vite's default target.
    esbuildOptions: {
      target: 'esnext',
    },
  },
  server: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: wsTarget,
        ws: true,
      },
    },
  },
})
