import { beforeEach, expect, test } from 'vitest';
import {
	canUpload,
	flociAutoOpen,
	flociExplorerUrl,
	flociUiUrl,
	s3Target,
	shouldOpenFlociUi
} from './s3target.svelte.js';

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

test('a first upload opens the UI, an all-skipped re-run does not', () => {
	expect(shouldOpenFlociUi('floci', { uploaded: 137, skipped: 0 })).toBe(true);
	expect(shouldOpenFlociUi('floci', { uploaded: 0, skipped: 137 })).toBe(false);
});

test('a re-autocurated build uploads new keys, so it opens the UI', () => {
	// The new selection ships photos the bucket has never seen; the ones it has are skipped.
	expect(shouldOpenFlociUi('floci', { uploaded: 6, skipped: 131 })).toBe(true);
});

test('AWS never auto-opens — there is no local UI to open', () => {
	expect(shouldOpenFlociUi('aws', { uploaded: 137, skipped: 0 })).toBe(false);
});

test('a missing or malformed result never opens a tab', () => {
	expect(shouldOpenFlociUi('floci', null)).toBe(false);
	expect(shouldOpenFlociUi('floci', {})).toBe(false);
});

test('auto-open defaults on and persists an opt-out', () => {
	expect(flociAutoOpen.enabled).toBe(true);
	flociAutoOpen.set(false);
	expect(flociAutoOpen.enabled).toBe(false);
	expect(localStorage.getItem('archive-floci-autoopen')).toBe('off');
	flociAutoOpen.set(true);
	expect(localStorage.getItem('archive-floci-autoopen')).toBe('on');
});

test('the storage explorer lives on the UI container own port, not the S3 one', () => {
	// 4500 is the sibling floci/floci-ui container; only the host is shared with :4566.
	expect(flociExplorerUrl('http://127.0.0.1:4566')).toBe(
		'http://127.0.0.1:4500/cloud-explorer/aws/storage'
	);
	expect(flociExplorerUrl('http://floci.local:9999')).toBe(
		'http://floci.local:4500/cloud-explorer/aws/storage'
	);
});

test('a malformed endpoint still yields a usable explorer url', () => {
	expect(flociExplorerUrl('')).toBe('http://127.0.0.1:4500/cloud-explorer/aws/storage');
	expect(flociExplorerUrl('not a url')).toBe('http://127.0.0.1:4500/cloud-explorer/aws/storage');
});
