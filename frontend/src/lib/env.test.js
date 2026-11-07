import { beforeEach, describe, expect, it } from 'vitest';
import { bannerTone, canPublish, envChoice, pickEnv } from './env.svelte.js';

const local = { name: 'local', kind: 'floci', confirm: false, configured: true };
const dev = { name: 'dev', kind: 'aws', confirm: false, configured: true };
const prod = { name: 'prod', kind: 'aws', confirm: true, configured: true };
const list = (envs = [local, dev, prod]) => ({
	default: 'local',
	envs,
	stale_settings: [],
	errors: []
});

beforeEach(() => {
	localStorage.clear();
	envChoice.set('local');
	localStorage.clear();
});

describe('pickEnv', () => {
	it('keeps a stored env that is listed and configured', () => {
		expect(pickEnv('dev', list())).toBe('dev');
	});

	it('falls back to the default when the stored env is not configured', () => {
		expect(pickEnv('dev', list([local, { ...dev, configured: false }, prod]))).toBe('local');
	});

	it('falls back to the default when the stored env is gone from the list', () => {
		expect(pickEnv('gone', list())).toBe('local');
	});

	it('uses the server default when nothing is stored', () => {
		expect(pickEnv(null, { ...list(), default: 'emu' })).toBe('emu');
	});

	it('never throws on a missing list', () => {
		expect(pickEnv('dev', null)).toBe('local');
	});
});

describe('envChoice', () => {
	it('starts on local before the server list arrives', () => {
		expect(envChoice.name).toBe('local');
	});

	it('persists an explicit choice', () => {
		envChoice.set('dev');
		expect(envChoice.name).toBe('dev');
		expect(localStorage.getItem('archive-env')).toBe('dev');
	});

	it('restores a stored env that is still usable', () => {
		localStorage.setItem('archive-env', 'prod');
		expect(envChoice.reconcile(list())).toBe('prod');
		expect(envChoice.name).toBe('prod');
	});

	it('rewrites a stale stored env to the server default', () => {
		// The env was removed from environments.local.toml, or lost its sign-in values.
		localStorage.setItem('archive-env', 'dev');
		envChoice.reconcile(list([local, { ...dev, configured: false }, prod]));
		expect(envChoice.name).toBe('local');
		expect(localStorage.getItem('archive-env')).toBe('local');

		localStorage.setItem('archive-env', 'personal');
		envChoice.reconcile(list());
		expect(envChoice.name).toBe('local');
		expect(localStorage.getItem('archive-env')).toBe('local');
	});

	it('ignores another tab’s stored choice on a later reconcile', () => {
		// Review round 1 #2: tab A wrote 'prod'; this tab, on dev, re-lists after a sign-in.
		envChoice.set('dev');
		localStorage.setItem('archive-env', 'prod');
		expect(envChoice.reconcile(list(), { fromStorage: false })).toBe('dev');
		expect(envChoice.name).toBe('dev');
	});

	it('keeps the in-memory env, and the stored one, through an offline later reconcile', () => {
		envChoice.set('dev');
		const offline = { api_reachable: false, default: 'local', envs: [], stale_settings: [], errors: [] };
		expect(envChoice.reconcile(offline, { fromStorage: false })).toBe('dev');
		expect(localStorage.getItem('archive-env')).toBe('dev');
	});

	it('still drops an in-memory env that became unusable on a later reconcile', () => {
		envChoice.set('dev');
		envChoice.reconcile(list([local, { ...dev, configured: false }, prod]), { fromStorage: false });
		expect(envChoice.name).toBe('local');
	});

	it('sits on the default but keeps the stored choice while the API is down', () => {
		localStorage.setItem('archive-env', 'dev');
		envChoice.reconcile({ api_reachable: false, default: 'local', envs: [], stale_settings: [], errors: [] });
		expect(envChoice.name).toBe('local');
		expect(localStorage.getItem('archive-env')).toBe('dev');
	});
});

describe('bannerTone', () => {
	it('is silent on floci, aws on a plain AWS env, prod on a confirm env', () => {
		expect(bannerTone(local)).toBe('none');
		expect(bannerTone(dev)).toBe('aws');
		expect(bannerTone(prod)).toBe('prod');
		expect(bannerTone(null)).toBe('none');
	});
});

describe('canPublish', () => {
	const ready = { built: true, signedIn: true, tablesReady: true, busy: false };

	it('is true only when every gate passes', () => {
		expect(canPublish(dev, ready)).toBe(true);
	});

	it.each([
		['not built', { built: false }],
		['signed out', { signedIn: false }],
		['tables missing', { tablesReady: false }],
		['busy', { busy: true }]
	])('is false when %s', (_label, over) => {
		expect(canPublish(dev, { ...ready, ...over })).toBe(false);
	});

	it('needs no sign-in on floci', () => {
		expect(canPublish(local, { ...ready, signedIn: false })).toBe(true);
	});

	it('is false for an unconfigured or missing env', () => {
		expect(canPublish({ ...dev, configured: false }, ready)).toBe(false);
		expect(canPublish(null, ready)).toBe(false);
	});
});
