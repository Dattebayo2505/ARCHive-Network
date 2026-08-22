import { beforeEach, expect, test } from 'vitest';
import { canUpload, s3Target } from './s3target.svelte.js';

beforeEach(() => {
	localStorage.clear();
	s3Target.set('floci');
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
