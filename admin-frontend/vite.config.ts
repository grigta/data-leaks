import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		port: 5174,
		host: '0.0.0.0',
		strictPort: true,
		cors: true,
		allowedHosts: [
			'localhost',
			'ois8u912jknasjb.top',
			'www.ois8u912jknasjb.top',
			'f72nak8127sd.top',
			'www.f72nak8127sd.top',
			'157.180.103.39'
		],
		proxy: {
			'/api': {
				target: process.env.ADMIN_API_URL || 'http://admin_api:8002',
				changeOrigin: true,
				rewrite: (path) => path.replace(/^\/api/, '')
			}
		}
	},
	optimizeDeps: {
		include: ['@lucide/svelte', 'chart.js']
	}
});
