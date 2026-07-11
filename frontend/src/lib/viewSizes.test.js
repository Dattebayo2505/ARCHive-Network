// frontend/src/lib/viewSizes.test.js
import { describe, expect, it } from 'vitest';
import { DEFAULT_SIZE, VIEW_SIZES, sizeCols } from './viewSizes.js';

describe('VIEW_SIZES', () => {
	it('offers the five density steps in ascending order', () => {
		expect(VIEW_SIZES.map((s) => s.id)).toEqual(['xs', 's', 'm', 'l', 'xl']);
		const cols = VIEW_SIZES.map((s) => s.cols);
		// Note cols descend from xs(10) to xl(2)
		expect(cols).toEqual([...cols].sort((a, b) => b - a));
	});

	it('defaults to the medium step', () => {
		expect(DEFAULT_SIZE).toBe('m');
		expect(VIEW_SIZES.some((s) => s.id === DEFAULT_SIZE)).toBe(true);
	});
});

describe('sizeCols', () => {
	it('returns the columns for a known id', () => {
		expect(sizeCols('xl')).toBe(2);
	});

	it('falls back to the medium cols for an unknown id', () => {
		expect(sizeCols('bogus')).toBe(6);
	});
});
