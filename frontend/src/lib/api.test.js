// frontend/src/lib/api.test.js
import { describe, expect, it, vi } from 'vitest';
import {
	browse,
	getInventory,
	ingestFolder,
	ingestUpload,
	ingestZip,
	previewUrl,
	reveal,
	thumbUrl,
	toggle
} from './api.js';

describe('thumbUrl', () => {
	it('builds an absolute thumb URL', () => {
		expect(thumbUrl('a01')).toMatch(/\/api\/thumb\/a01$/);
	});
});

describe('previewUrl', () => {
	it('builds an absolute preview URL', () => {
		expect(previewUrl('a01')).toMatch(/\/api\/preview\/a01$/);
	});

	it('encodes the fbid', () => {
		expect(previewUrl('a/01')).toMatch(/\/api\/preview\/a%2F01$/);
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

describe('reveal', () => {
	it('posts the photo fbid and reports success', async () => {
		const fakeFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
		expect(await reveal({ photoFbid: 'a01' }, fakeFetch)).toEqual({ ok: true });
		const [, opts] = fakeFetch.mock.calls[0];
		expect(JSON.parse(opts.body)).toEqual({ photo_fbid: 'a01', album_fbid: null });
	});

	it('posts the album fbid', async () => {
		const fakeFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
		await reveal({ albumFbid: '111' }, fakeFetch);
		const [, opts] = fakeFetch.mock.calls[0];
		expect(JSON.parse(opts.body)).toEqual({ photo_fbid: null, album_fbid: '111' });
	});

	it('surfaces the server error detail on failure', async () => {
		const fakeFetch = vi.fn().mockResolvedValue({
			ok: false,
			json: async () => ({ detail: 'File is missing from the export' })
		});
		expect(await reveal({ photoFbid: 'm02' }, fakeFetch)).toEqual({
			ok: false,
			error: 'File is missing from the export'
		});
	});
});

describe('getInventory', () => {
	it('returns null when no export is loaded (404)', async () => {
		const fakeFetch = vi.fn().mockResolvedValue({ status: 404, json: async () => ({}) });
		expect(await getInventory(fakeFetch)).toBeNull();
	});
});

describe('network failure handling (CORS / server down)', () => {
	// A rejected fetch (CORS block or connection refused) must become a readable
	// error result, not an unhandled throw that hangs the UI on skeletons.
	const rejecting = () => vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

	it('browse returns an error result instead of throwing', async () => {
		const res = await browse(null, rejecting());
		expect(res.ok).toBe(false);
		expect(res.error).toMatch(/API server/i);
	});

	it('ingestFolder returns an error result instead of throwing', async () => {
		const res = await ingestFolder('C:\\x', rejecting());
		expect(res.ok).toBe(false);
		expect(res.errors?.[0]).toMatch(/API server/i);
	});

	it('ingestZip returns an error result instead of throwing', async () => {
		const res = await ingestZip('C:\\x.zip', rejecting());
		expect(res.ok).toBe(false);
		expect(res.errors?.[0]).toMatch(/API server/i);
	});
});

describe('ingestZip', () => {
	it('posts the local archive path and returns the result', async () => {
		const fakeFetch = vi
			.fn()
			.mockResolvedValue({ json: async () => ({ ok: true, export_name: 'export' }) });
		const result = await ingestZip('C:\\exports\\fb.zip', fakeFetch);
		expect(result).toEqual({ ok: true, export_name: 'export' });
		const [path, opts] = fakeFetch.mock.calls[0];
		expect(path).toMatch(/\/api\/ingest\/zip$/);
		expect(JSON.parse(opts.body)).toEqual({ path: 'C:\\exports\\fb.zip' });
	});
});

describe('ingestUpload', () => {
	// Minimal stand-in for XMLHttpRequest that fires one progress event then loads.
	function fakeXhr({ status = 200, responseText = '{"ok":true}' } = {}) {
		return {
			upload: {},
			open: vi.fn(),
			send() {
				this.upload.onprogress?.({ lengthComputable: true, loaded: 30, total: 120 });
				this.status = status;
				this.responseText = responseText;
				this.onload?.();
			}
		};
	}

	it('reports upload progress as a 0..1 fraction and resolves the parsed body', async () => {
		const seen = [];
		const result = await ingestUpload(new Blob(['x']), {
			onProgress: (p) => seen.push(p),
			createXhr: () => fakeXhr({ responseText: '{"ok":true,"export_name":"export"}' })
		});
		expect(seen).toEqual([0.25]);
		expect(result).toEqual({ ok: true, export_name: 'export' });
	});

	it('resolves an error result when the request fails', async () => {
		const xhr = {
			upload: {},
			open: vi.fn(),
			send() {
				this.onerror?.();
			}
		};
		const result = await ingestUpload(new Blob(['x']), { createXhr: () => xhr });
		expect(result.ok).toBe(false);
		expect(result.errors).toBeTruthy();
	});
});
