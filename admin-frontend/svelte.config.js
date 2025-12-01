import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),

	kit: {
		adapter: adapter({
			out: 'build',
			precompress: true
		}),
		alias: {
			$lib: 'src/lib',
			$components: 'src/lib/components',
			$stores: 'src/lib/stores',
			$api: 'src/lib/api'
		},
		paths: {
			base: ''
		},
		csrf: {
			checkOrigin: false
		}
	},

	vite: {
		ssr: {
			noExternal: ['chart.js', 'chartjs-adapter-date-fns']
		}
	}
};

export default config;
