// frontend/src/lib/viewSizes.test.js
import { describe, expect, it } from 'vitest';
import { DEFAULT_SIZE, VIEW_SIZES, sizeMin } from './viewSizes.js';

describe('VIEW_SIZES', () => {
	it('offers the five density steps in ascending order', () => {
		expect(VIEW_SIZES.map((s) => s.id)).toEqual(['xs', 's', 'm', 'l', 'xl']);
		const rems = VIEW_SIZES.map((s) => parseFloat(s.min));
		expect(rems).toEqual([...rems].sort((a, b) => a - b));
	});

	it('defaults to the medium step', () => {
		expect(DEFAULT_SIZE).toBe('m');
		expect(VIEW_SIZES.some((s) => s.id === DEFAULT_SIZE)).toBe(true);
	});
});

describe('sizeMin', () => {
	it('returns the track floor for a known id', () => {
		expect(sizeMin('xl')).toBe('18rem');
	});

	it('falls back to the medium floor for an unknown id', () => {
		expect(sizeMin('bogus')).toBe('11rem');
	});
});
