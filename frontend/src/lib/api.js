// frontend/src/lib/api.js
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

const url = (path) => `${API_BASE}${path}`;
const jsonHeaders = { 'content-type': 'application/json' };

export function thumbUrl(fbid) {
	return url(`/api/thumb/${encodeURIComponent(fbid)}`);
}

export async function getSession(fetchFn = fetch) {
	return (await fetchFn(url('/api/session'))).json();
}

export async function getInventory(fetchFn = fetch) {
	const res = await fetchFn(url('/api/inventory'));
	if (res.status === 404) return null;
	return res.json();
}

export async function ingestFolder(folder, fetchFn = fetch) {
	const res = await fetchFn(url('/api/ingest/folder'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ folder })
	});
	return res.json();
}

export async function ingestUpload(file, fetchFn = fetch) {
	const fd = new FormData();
	fd.append('file', file);
	const res = await fetchFn(url('/api/ingest/upload'), { method: 'POST', body: fd });
	return res.json();
}

export async function toggle(albumFbid, photoFbid, fetchFn = fetch) {
	const res = await fetchFn(url('/api/toggle'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ album_fbid: albumFbid, photo_fbid: photoFbid })
	});
	if (res.status === 409) {
		const data = await res.json();
		return { ok: false, cap: true, count: data.count };
	}
	const data = await res.json();
	return { ok: true, cap: false, selected: data.selected, count: data.count };
}

export async function build(fetchFn = fetch) {
	return (await fetchFn(url('/api/build'), { method: 'POST' })).json();
}

export { API_BASE };
