import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  build: {
    // Enable source maps for production debugging
    sourcemap: true,
    // Optional: you can use 'hidden' for source maps without exposing them in browser devtools
    // sourcemap: 'hidden',
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    strictPort: true,
    cors: true,
    allowedHosts: ['localhost', 'data-leaks.cc', 'www.data-leaks.cc', '157.180.103.39'],
    proxy: {
      '/api/public': {
        target: process.env.PUBLIC_API_URL || 'http://public_api:8000',
        changeOrigin: true,
        secure: false,
        ws: true,
        configure: (proxy, _options) => {
          proxy.on('error', (err, _req, _res) => {
            console.log('proxy error', err);
          });
          proxy.on('proxyReq', (_proxyReq, req, _res) => {
            console.log('Sending Request to the Target:', req.method, req.url);
          });
        },
        rewrite: (path) => path.replace(/^\/api\/public/, '')
      },
      '/api/enrichment': {
        target: process.env.ENRICHMENT_API_URL || 'http://enrichment_api:8001',
        changeOrigin: true,
        secure: false,
        ws: true,
        rewrite: (path) => path.replace(/^\/api\/enrichment/, '')
      }
    }
  },
  optimizeDeps: {
    include: ['@lucide/svelte']
  }
});
