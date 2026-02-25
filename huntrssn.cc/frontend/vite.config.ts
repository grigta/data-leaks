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
    allowedHosts: ['localhost', 'na71ka921ma.top', 'www.na71ka921ma.top'],
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
      }
    }
  },
  optimizeDeps: {
    include: ['@lucide/svelte']
  }
});
