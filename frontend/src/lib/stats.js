// frontend/src/lib/stats.js
// Pure computations behind the Workspace Stats popup. Everything derives from
// the /api/inventory payload; nothing here fetches or renders.

/** Best available moment for a photo: when it was taken, else posted, else created. */
function photoDate(p) {
	return p.taken_timestamp ?? p.post_timestamp ?? p.creation_at ?? null;
}

/**
 * Summarize an inventory payload into the numbers the stats popup shows.
 * Videos are excluded from the size sum — their file_size_bytes field carries
 * the replacement thumbnail's size, and the .mp4 is never copied anyway.
 */
export function computeStats(inv) {
	const albums = inv?.albums ?? [];
	const archivedAlbums = inv?.archived_albums ?? [];
	const nonAlbum = inv?.non_album ?? [];
	const archive = inv?.archive ?? [];
	const videos = inv?.videos ?? [];

	const albumPhotos = albums.flatMap((a) => a.photos ?? []);
	const archivedAlbumPhotos = archivedAlbums.flatMap((a) => a.photos ?? []);
	const allPhotos = [...albumPhotos, ...archivedAlbumPhotos, ...nonAlbum, ...archive];

	let start = null;
	let end = null;
	for (const p of [...allPhotos, ...videos]) {
		const iso = photoDate(p);
		if (!iso) continue;
		if (start === null || iso < start) start = iso;
		if (end === null || iso > end) end = iso;
	}

	return {
		mainAlbums: albums.filter((a) => !a.origin).length,
		derivedAlbums: albums.filter((a) => a.origin).length,
		archivedAlbums: archivedAlbums.length,
		totalPhotos: allPhotos.length,
		totalVideos: videos.length,
		mediaBytes: allPhotos.reduce((sum, p) => sum + (p.file_size_bytes ?? 0), 0),
		selectedCount: albums.reduce((sum, a) => sum + (a.count_selected ?? 0), 0),
		albumCount: albums.length,
		dateRange: start ? { start, end } : null
	};
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function fmtDay(d, withYear) {
	const base = `${MONTHS[d.getMonth()]} ${d.getDate()} (${DAYS[d.getDay()]})`;
	return withYear ? `${base}, ${d.getFullYear()}` : base;
}

/**
 * "Jun 29 (Mon) – Jul 5 (Sun)". Years appear only when they carry information:
 * the range spans two years, or it isn't the current year. A single-day range
 * collapses to one date. `now` is injectable for tests.
 */
export function formatDateRange(range, now = new Date()) {
	if (!range) return null;
	const start = new Date(range.start);
	const end = new Date(range.end);
	const withYear =
		start.getFullYear() !== end.getFullYear() || end.getFullYear() !== now.getFullYear();
	const from = fmtDay(start, withYear);
	if (
		start.getFullYear() === end.getFullYear() &&
		start.getMonth() === end.getMonth() &&
		start.getDate() === end.getDate()
	) {
		return from;
	}
	return `${from} – ${fmtDay(end, withYear)}`;
}

/** "512.3 MB", stepping up to GB past 1024 MB. */
export function formatSize(bytes) {
	const mb = bytes / (1024 * 1024);
	if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
	return `${mb.toFixed(1)} MB`;
}
