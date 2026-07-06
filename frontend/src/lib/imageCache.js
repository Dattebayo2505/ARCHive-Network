// frontend/src/lib/imageCache.js
//
// Eagerly prefetch all thumbnails for an album the first time it is opened,
// so switching back to a previously-viewed album loads images instantly from
// the browser's HTTP cache instead of making new network requests.

/** @type {Set<string>} album IDs whose thumbnails have already been prefetched */
const prefetched = new Set();

/**
 * Eagerly load every thumbnail for an album into the browser cache.
 * Skips albums that were already prefetched in this page session.
 *
 * Uses `new Image()` (same request mode as the grid's `<img>` tags) so the
 * browser cache entry is reusable without CORS mismatches.
 *
 * @param {string} albumId - unique album identifier (fb_album_id, '__archive__', '__videos__')
 * @param {{ fbid: string, exists: boolean }[]} photos - the album's photo list
 * @param {(fbid: string) => string} thumbUrlFn - returns the thumbnail URL for a given fbid
 */
export function prefetchAlbumThumbs(albumId, photos, thumbUrlFn) {
	if (prefetched.has(albumId)) return;
	prefetched.add(albumId);

	for (const photo of photos) {
		if (!photo.exists) continue;
		const img = new Image();
		img.src = thumbUrlFn(photo.fbid);
	}
}

/** Clear all prefetch tracking (e.g. when loading a different export). */
export function clearPrefetchCache() {
	prefetched.clear();
}
