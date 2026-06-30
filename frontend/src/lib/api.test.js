// frontend/src/lib/api.test.js
import { describe, expect, it, vi } from 'vitest';
import { getInventory, thumbUrl, toggle } from './api.js';

describe('thumbUrl', () => {
	it('builds an absolute thumb URL', () => {
		expect(thumbUrl('a01')).toMatch(/\/api\/thumb\/a01$/);
	});
});

describe('toggle', () => {
	it('maps a 409 to a cap result', async () => {
		const fakeFetch = vi.fn().mockResolvedValue({
			status: 409,
			json: async () => ({ error: 'cap', count: 10 })
		});
		expect(await toggle('111', 'a11', fakeFetch)).toEqual({ ok: false, cap: true, count: 10 });
	});

	it('maps a 200 to a selected result', async () => {
		const fakeFetch = vi.fn().mockResolvedValue({
			status: 200,
			json: async () => ({ selected: true, count: 1 })
		});
		expect(await toggle('111', 'a01', fakeFetch)).toEqual({
			ok: true,
			cap: false,
			selected: true,
			count: 1
		});
	});
});

describe('getInventory', () => {
	it('returns null when no export is loaded (404)', async () => {
		const fakeFetch = vi.fn().mockResolvedValue({ status: 404, json: async () => ({}) });
		expect(await getInventory(fakeFetch)).toBeNull();
	});
});
