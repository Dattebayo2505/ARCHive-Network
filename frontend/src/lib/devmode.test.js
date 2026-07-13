import { beforeEach, expect, test } from 'vitest';
import { devMode } from './devmode.svelte.js';

beforeEach(() => {
	localStorage.clear();
	devMode.set(false);
});

test('dev mode is off by default', () => {
	expect(devMode.enabled).toBe(false);
});

test('toggling flips the flag and persists it', () => {
	devMode.toggle();
	expect(devMode.enabled).toBe(true);
	expect(localStorage.getItem('archive-dev-mode')).toBe('true');

	devMode.toggle();
	expect(devMode.enabled).toBe(false);
	expect(localStorage.getItem('archive-dev-mode')).toBe('false');
});
