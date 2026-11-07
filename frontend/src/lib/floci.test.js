import { beforeEach, expect, test } from 'vitest';
import {
	canUpload,
	flociAutoOpen,
	flociUiUrl,
	s3Target,
	shouldOpenFlociUi
} from './floci.svelte.js';

beforeEach(() => {
	localStorage.clear();
	s3Target.set('floci');
	flociAutoOpen.set(true);
});

test('the target defaults to floci', () => {
	expect(s3Target.target).toBe('floci');
});

test('toggling flips the target and persists it', () => {
	s3Target.toggle();
	expect(s3Target.target).toBe('aws');
	expect(localStorage.getItem('archive-s3-target')).toBe('aws');

	s3Target.toggle();
	expect(s3Target.target).toBe('floci');
	expect(localStorage.getItem('archive-s3-target')).toBe('floci');
});

test('an unrecognised stored value falls back to floci', () => {
	s3Target.set('nonsense');
	expect(s3Target.target).toBe('floci');
});

const up = { aws: { enabled: true }, floci: { enabled: true, reachable: true } };
const down = { aws: { enabled: true }, floci: { enabled: true, reachable: false } };

test('floci uploads are blocked while the emulator is unreachable', () => {
	expect(canUpload('floci', up)).toBe(true);
	expect(canUpload('floci', down)).toBe(false);
});

test('the floci probe never gates an AWS upload', () => {
	expect(canUpload('aws', down)).toBe(true);
});

test('AWS uploads are blocked when AWS is not configured', () => {
	expect(canUpload('aws', { aws: { enabled: false }, floci: { enabled: true, reachable: true } })).toBe(
		false
	);
});

test('a missing or malformed status object is false, not a throw', () => {
	expect(canUpload('floci', null)).toBe(false);
	expect(canUpload('floci', undefined)).toBe(false);
	expect(canUpload('aws', {})).toBe(false);
});

// --- The Floci UI ------------------------------------------------------------------------

test('the Floci UI hangs off the same endpoint the S3 API does', () => {
	expect(flociUiUrl('http://127.0.0.1:4566')).toBe('http://127.0.0.1:4566/_floci/ui');
	expect(flociUiUrl('http://127.0.0.1:4566/')).toBe('http://127.0.0.1:4566/_floci/ui');
	expect(flociUiUrl('http://localhost:9000')).toBe('http://localhost:9000/_floci/ui');
});

test('the link is never undefined/_floci/ui before /api/s3/status answers', () => {
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
