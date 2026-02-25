import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 5175,
    host: '0.0.0.0',
    strictPort: true,
    proxy: {
      '/api/worker/ws': {
        target: process.env.WORKER_API_URL || 'http://worker_api:8003',
        changeOrigin: true,
        secure: false,
        ws: true,
        rewrite: (path) => path.replace(/^\/api\/worker/, '')
      },
      '/api/worker': {
        target: process.env.WORKER_API_URL || 'http://worker_api:8003',
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path.replace(/^\/api\/worker/, '')
      }
    }
  }
});
