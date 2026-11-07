import { beforeEach, expect, test } from 'vitest';
import {
	flociAutoOpen,
	flociUiUrl,
	shouldOpenFlociUi
} from './floci.svelte.js';

beforeEach(() => {
	localStorage.clear();
	flociAutoOpen.set(true);
});

// --- The Floci UI ------------------------------------------------------------------------

test('the Floci UI hangs off the same endpoint the S3 API does', () => {
	expect(flociUiUrl('http://127.0.0.1:4566')).toBe('http://127.0.0.1:4566/_floci/ui');
	expect(flociUiUrl('http://127.0.0.1:4566/')).toBe('http://127.0.0.1:4566/_floci/ui');
	expect(flociUiUrl('http://localhost:9000')).toBe('http://localhost:9000/_floci/ui');
});

test('the link is never undefined/_floci/ui before /api/envs answers', () => {
	expect(flociUiUrl(undefined)).toBe('http://127.0.0.1:4566/_floci/ui');
	expect(flociUiUrl('')).toBe('http://127.0.0.1:4566/_floci/ui');
});

const LOCAL = { name: 'local', kind: 'floci' };
const DEV = { name: 'dev', kind: 'aws' };
const published = (stored, skipped = 0) => ({
	ok: true,
	steps: { publish: { files_stored: stored, files_skipped: skipped } }
});

test('a first publish opens the UI, an all-skipped re-run does not', () => {
	expect(shouldOpenFlociUi(LOCAL, published(137))).toBe(true);
	expect(shouldOpenFlociUi(LOCAL, published(0, 137))).toBe(false);
});

test('a re-autocurated build stores new keys, so it opens the UI', () => {
	// The new selection ships photos the bucket has never seen; the ones it has are skipped.
	expect(shouldOpenFlociUi(LOCAL, published(6, 131))).toBe(true);
});

test('an AWS env never auto-opens — there is no local UI to open', () => {
	expect(shouldOpenFlociUi(DEV, published(137))).toBe(false);
});

test('a missing or malformed result never opens a tab', () => {
	expect(shouldOpenFlociUi(LOCAL, null)).toBe(false);
	expect(shouldOpenFlociUi(LOCAL, {})).toBe(false);
	// A failed preflight leaves the publish step null.
	expect(shouldOpenFlociUi(LOCAL, { ok: false, steps: { publish: null } })).toBe(false);
	expect(shouldOpenFlociUi(null, published(137))).toBe(false);
});

test('auto-open defaults on and persists an opt-out', () => {
	expect(flociAutoOpen.enabled).toBe(true);
	flociAutoOpen.set(false);
	expect(flociAutoOpen.enabled).toBe(false);
	expect(localStorage.getItem('archive-floci-autoopen')).toBe('off');
	flociAutoOpen.set(true);
	expect(localStorage.getItem('archive-floci-autoopen')).toBe('on');
});
