// frontend/vitest.config.js
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { svelteTesting } from '@testing-library/svelte/vite';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [svelte(), svelteTesting()],
	// The test config uses the plain svelte plugin (not sveltekit), so `$lib` isn't
	// registered — alias it so components importing `$lib/*` can be unit-tested.
	resolve: {
		alias: { $lib: fileURLToPath(new URL('./src/lib', import.meta.url)) }
	},
	test: {
		environment: 'jsdom',
		setupFiles: ['./vitest-setup.js'],
		globals: true
	}
});
