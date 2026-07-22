// frontend/src/lib/api.js
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

const url = (path) => `${API_BASE}${path}`;
const jsonHeaders = { 'content-type': 'application/json' };

export function thumbUrl(fbid) {
	return url(`/api/thumb/${encodeURIComponent(fbid)}?v=512`);
}

export function previewUrl(fbid) {
	return url(`/api/preview/${encodeURIComponent(fbid)}`);
}

export async function getSession(fetchFn = fetch) {
	return (await fetchFn(url('/api/session'))).json();
}

export async function getInventory(fetchFn = fetch) {
	const res = await fetchFn(url('/api/inventory'));
	if (res.status === 404) return null;
	return res.json();
}

// A cross-origin/CORS or connection failure makes fetch reject (throw) rather
// than return a response. Turn that into a readable message so the UI shows an
// error instead of hanging (e.g. the folder picker stuck on skeletons).
const UNREACHABLE = 'Could not reach the API server. Is it running on port 8000?';

export async function browse(path, fetchFn = fetch) {
	const qs = path ? `?path=${encodeURIComponent(path)}` : '';
	let res;
	try {
		res = await fetchFn(url(`/api/browse${qs}`));
	} catch {
		return { ok: false, error: UNREACHABLE };
	}
	if (!res.ok) {
		const data = await res.json().catch(() => ({}));
		return { ok: false, error: data.detail ?? 'Could not open that folder.' };
	}
	return { ok: true, ...(await res.json()) };
}

export async function ingestFolder(folder, fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/ingest/folder'), {
			method: 'POST',
			headers: jsonHeaders,
			body: JSON.stringify({ folder })
		});
		return res.json();
	} catch {
		return { ok: false, errors: [UNREACHABLE] };
	}
}

export async function ingestZip(path, fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/ingest/zip'), {
			method: 'POST',
			headers: jsonHeaders,
			body: JSON.stringify({ path })
		});
		return res.json();
	} catch {
		return { ok: false, errors: [UNREACHABLE] };
	}
}

/**
 * Upload an export archive over HTTP. Uses XMLHttpRequest (not fetch) because it
 * is the only way to observe upload progress in the browser — `onProgress`
 * receives a 0..1 fraction. `createXhr` is injectable for testing.
 */
export function ingestUpload(file, { onProgress, createXhr = () => new XMLHttpRequest() } = {}) {
	return new Promise((resolve) => {
		const xhr = createXhr();
		xhr.open('POST', url('/api/ingest/upload'));
		xhr.upload.onprogress = (e) => {
			if (onProgress && e.lengthComputable) onProgress(e.loaded / e.total);
		};
		xhr.onload = () => {
			try {
				resolve(JSON.parse(xhr.responseText));
			} catch {
				resolve({ ok: false, errors: ['The server returned an unexpected response.'] });
			}
		};
		xhr.onerror = () =>
			resolve({ ok: false, errors: ['Upload failed — is the API server running?'] });
		const fd = new FormData();
		fd.append('file', file);
		xhr.send(fd);
	});
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

export async function deselectAll(albumFbid, fetchFn = fetch) {
	const res = await fetchFn(url('/api/deselect_all'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ album_fbid: albumFbid })
	});
	return res.json();
}

export async function build(fetchFn = fetch) {
	return (await fetchFn(url('/api/build'), { method: 'POST' })).json();
}

/**
 * Ask the local server to open the OS file manager on a photo's file or an
 * album's folder. Pass exactly one of `photoFbid` / `albumFbid`.
 */
export async function reveal({ photoFbid, albumFbid } = {}, fetchFn = fetch) {
	const res = await fetchFn(url('/api/reveal'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ photo_fbid: photoFbid ?? null, album_fbid: albumFbid ?? null })
	});
	if (!res.ok) {
		const data = await res.json().catch(() => ({}));
		return { ok: false, error: data.detail ?? 'Could not open the file manager.' };
	}
	return { ok: true };
}

export function videoUrl(fbid) {
	return url(`/api/video/${encodeURIComponent(fbid)}`);
}

export function videoThumbUrl(fbid) {
	return url(`/api/video/${encodeURIComponent(fbid)}/thumbnail`);
}

export async function saveVideoThumbnail(fbid, blob, auto = false, timestamp = 0.0, fetchFn = fetch) {
	const u = new URL(videoThumbUrl(fbid), window.location.origin);
	if (auto) u.searchParams.set('auto', 'true');
	u.searchParams.set('timestamp', timestamp.toString());
	const urlStr = u.href;
	const res = await fetchFn(urlStr, {
		method: 'POST',
		headers: { 'content-type': 'image/jpeg' },
		body: blob
	});
	if (!res.ok) return { ok: false };
	return { ok: true, ...(await res.json()) };
}

/** Rename an album (display name only — the export on disk is untouched). */
export async function renameAlbum(albumFbid, name, fetchFn = fetch) {
	const res = await fetchFn(url('/api/album/rename'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ album_fbid: albumFbid, name })
	});
	if (!res.ok) {
		const data = await res.json().catch(() => ({}));
		return { ok: false, error: data.detail ?? 'Could not rename the album.' };
	}
	return { ok: true, ...(await res.json()) };
}

/** Reset an album's name back to its original name. */
export async function resetAlbumName(albumFbid, fetchFn = fetch) {
	const res = await fetchFn(url('/api/album/reset'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ album_fbid: albumFbid, name: "" }) // name is required by the Pydantic model
	});
	if (!res.ok) {
		const data = await res.json().catch(() => ({}));
		return { ok: false, error: data.detail ?? 'Could not reset the album name.' };
	}
	return { ok: true, ...(await res.json()) };
}

/**
 * Override an album's caption. `caption` is **prose only** — the album's hashtags are
 * re-attached server-side, so an edit can never delete the canonical `#ARCH…` section tag
 * that decides where the album's photos land downstream.
 */
export async function setAlbumCaption(albumFbid, caption, fetchFn = fetch) {
	const res = await fetchFn(url('/api/album/caption'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ album_fbid: albumFbid, caption })
	});
	if (!res.ok) {
		const data = await res.json().catch(() => ({}));
		return { ok: false, error: data.detail ?? 'Could not save the caption.' };
	}
	return { ok: true, ...(await res.json()) };
}

/** Drop the caption override and restore the caption the export shipped with. */
export async function resetAlbumCaption(albumFbid, fetchFn = fetch) {
	const res = await fetchFn(url('/api/album/caption/reset'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ album_fbid: albumFbid })
	});
	if (!res.ok) {
		const data = await res.json().catch(() => ({}));
		return { ok: false, error: data.detail ?? 'Could not reset the caption.' };
	}
	return { ok: true, ...(await res.json()) };
}

/** Move every photo in an album to the archive, then remove the album. */
export async function archiveAlbum(albumFbid, fetchFn = fetch) {
	const res = await fetchFn(url('/api/album/archive'), {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ album_fbid: albumFbid })
	});
	const data = await res.json();
	if (!res.ok) {
		return { ok: false, error: data.detail ?? 'Could not archive the album.' };
	}
	return data; // {ok, moved}
}

/** Restore an album from the archive back to normal albums. */
export async function unarchiveAlbum(albumFbid, fetchFn = fetch) {
	const res = await fetchFn(url('/api/album/unarchive'), {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ album_fbid: albumFbid })
	});
	const data = await res.json();
	if (!res.ok) {
		return { ok: false, error: data.detail ?? 'Could not unarchive the album.' };
	}
	return data; // {ok, moved}
}

/** Increase limit of the album */
export async function increaseLimit(albumFbid, fetchFn = fetch) {
	const res = await fetchFn(url('/api/album/increase_limit'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ album_fbid: albumFbid })
	});
	if (!res.ok) {
		const data = await res.json().catch(() => ({}));
		return { ok: false, error: data.detail ?? 'Could not increase the limit.' };
	}
	return { ok: true, ...(await res.json()) };
}

/** Undo increase limit of the album */
export async function undoIncreaseLimit(albumFbid, fetchFn = fetch) {
	const res = await fetchFn(url('/api/album/undo_increase_limit'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ album_fbid: albumFbid })
	});
	if (!res.ok) {
		const data = await res.json().catch(() => ({}));
		return { ok: false, error: data.detail ?? 'Could not undo the limit increase.' };
	}
	return { ok: true, ...(await res.json()) };
}

/** Persist that the workspace-stats popup was shown for the open workspace. */
export async function markStatsSeen(fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/stats/seen'), { method: 'POST' });
		return { ok: res.ok };
	} catch {
		return { ok: false };
	}
}

/** List every known workspace, newest-opened first, plus the last-active id. */
export async function listWorkspaces(fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/workspaces'));
		if (!res.ok) return { workspaces: [], last_active: null };
		return res.json();
	} catch {
		return { workspaces: [], last_active: null };
	}
}

/** Get brief stats for a specific workspace without opening it. */
export async function getWorkspaceStats(id, fetchFn = fetch) {
	try {
		const res = await fetchFn(url(`/api/workspaces/${encodeURIComponent(id)}/stats`));
		if (!res.ok) return null;
		return res.json();
	} catch {
		return null;
	}
}

/** Open a workspace by id, rebuilding its session (restores its saved state). */
export async function openWorkspace(id, fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/workspaces/open'), {
			method: 'POST',
			headers: jsonHeaders,
			body: JSON.stringify({ id })
		});
		if (!res.ok) {
			const data = await res.json().catch(() => ({}));
			return { ok: false, error: data.detail ?? 'Could not open that workspace.' };
		}
		return res.json();
	} catch {
		return { ok: false, error: UNREACHABLE };
	}
}

/** Remove a workspace from the list; optionally delete its files (managed only). */
export async function removeWorkspace(id, deleteFiles, fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/workspaces/remove'), {
			method: 'POST',
			headers: jsonHeaders,
			body: JSON.stringify({ id, delete_files: deleteFiles })
		});
		if (!res.ok) {
			const data = await res.json().catch(() => ({}));
			return { ok: false, error: data.detail ?? 'Could not remove that workspace.' };
		}
		return res.json();
	} catch {
		return { ok: false, error: UNREACHABLE };
	}
}

/** List every built ready folder, newest-built first. Never throws. */
export async function listReadyBuilds(fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/ready'));
		if (!res.ok) return { builds: [] };
		return res.json();
	} catch {
		return { builds: [] };
	}
}

/**
 * The ready build for the loaded workspace, or `null` if it has never been built.
 * Never throws — an unreachable server reads as "no build", which only costs the
 * user the overwrite warning, never a wrong one.
 */
export async function getCurrentReadyBuild(fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/ready/current'));
		if (!res.ok) return null;
		return (await res.json()).build ?? null;
	} catch {
		return null;
	}
}

/** Ask the local server to open the OS file manager on a specific ready build. */
export async function revealReadyBuild(id, fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/ready/reveal'), {
			method: 'POST',
			headers: jsonHeaders,
			body: JSON.stringify({ id })
		});
		if (!res.ok) {
			const data = await res.json().catch(() => ({}));
			return { ok: false, error: data.detail ?? 'Could not open the file manager.' };
		}
		return { ok: true };
	} catch {
		return { ok: false, error: UNREACHABLE };
	}
}

/**
 * Auto-curate: pick <=N photos per album and select every video, replacing the selection.
 * A *selection* call, not a dev/DB one — it works with or without Postgres configured.
 */
export async function autoCurate(perAlbum = null, fetchFn = fetch) {
	const res = await fetchFn(url('/api/curate'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ per_album: perAlbum })
	});
	return { ok: res.ok, status: res.status, body: await res.json() };
}

// --- Dev-mode: the local Postgres + object store. Every route 404s unless the backend has
// ARCHIVENETWORK_DATABASE_URL set, so the panel must handle `enabled: false` gracefully. ---

/** Build the URL an object is served from: <base>/<storage_path>. In prod the base is a CDN. */
export function storeUrl(storagePath, baseUrl = '/store') {
	return url(`${baseUrl}/${storagePath}`);
}

/** Connection + schema status. Never throws on a missing DB — it reports it. */
export async function devStatus(fetchFn = fetch) {
	return (await fetchFn(url('/api/dev/status'))).json();
}

/** Create the tables; `reset` drops and recreates them (destructive). */
export async function devSchema(reset = false, fetchFn = fetch) {
	const res = await fetchFn(url('/api/dev/schema'), {
		method: 'POST',
		headers: jsonHeaders,
		body: JSON.stringify({ reset })
	});
	return { ok: res.ok, status: res.status, body: await res.json() };
}

/** Run the ETL over the current workspace's ready folder. 409 = not built yet. */
export async function devLoad(fetchFn = fetch) {
	const res = await fetchFn(url('/api/dev/load'), { method: 'POST' });
	return { ok: res.ok, status: res.status, body: await res.json() };
}

/** Paginated rows from `media` or `photo_album`. */
export async function devRows(table = 'media', limit = 50, offset = 0, fetchFn = fetch) {
	const qs = new URLSearchParams({ table, limit: String(limit), offset: String(offset) });
	const res = await fetchFn(url(`/api/dev/rows?${qs}`));
	return { ok: res.ok, status: res.status, body: await res.json() };
}

/** The schema-validation report. */
export async function devValidate(fetchFn = fetch) {
	const res = await fetchFn(url('/api/dev/validate'));
	return { ok: res.ok, status: res.status, body: await res.json() };
}

// --- The database itself (not its tables). `devSchema` above needs the database to already
// exist; these three are what you reach for when it does not. The backend answers them via
// the `postgres` maintenance database, so they work when /api/dev/status cannot connect. ---

/** Is the server up, and does our database exist? Never throws. */
export async function devDatabase(fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/dev/database'));
		if (!res.ok) return { server_up: false, database_exists: false, reason: 'dev mode is off' };
		return res.json();
	} catch {
		return { server_up: false, database_exists: false, reason: UNREACHABLE };
	}
}

/** CREATE DATABASE. Idempotent — `created: false` means it was already there. */
export async function devDatabaseCreate(fetchFn = fetch) {
	const res = await fetchFn(url('/api/dev/database'), { method: 'POST' });
	return { ok: res.ok, status: res.status, body: await res.json() };
}

/** DROP DATABASE — destructive, takes every table and row with it. */
export async function devDatabaseDrop(fetchFn = fetch) {
	const res = await fetchFn(url('/api/dev/database'), { method: 'DELETE' });
	return { ok: res.ok, status: res.status, body: await res.json() };
}

// --- On-demand S3 upload. Gated on the backend having ARCHIVENETWORK_S3_BUCKET set;
// GET status 200s regardless (enabled:false when unset) so the panel can reveal itself. ---

/** Whether S3 upload is configured, and against which bucket/region. Never throws. */
export async function s3Status(fetchFn = fetch) {
	try {
		const res = await fetchFn(url('/api/s3/status'));
		if (!res.ok) return { enabled: false };
		return res.json();
	} catch {
		return { enabled: false };
	}
}

/** Push the current built workspace's ready folder to S3. 404=not configured, 409=not built,
 *  502=S3 unreachable. */
export async function uploadToS3(fetchFn = fetch) {
	const res = await fetchFn(url('/api/s3/upload'), { method: 'POST' });
	return { ok: res.ok, status: res.status, body: await res.json() };
}

export { API_BASE };
