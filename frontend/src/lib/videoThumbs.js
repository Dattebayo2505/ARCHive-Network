import { saveVideoThumbnail, videoThumbUrl } from './api.js';

/**
 * Draw a <video>'s current frame to a JPEG Blob. The <video> MUST be loaded with
 * crossorigin="anonymous" from a CORS-enabled source, or the canvas is tainted and
 * toBlob throws a SecurityError.
 */
export function captureFrame(videoEl, quality = 0.85) {
	const canvas = document.createElement('canvas');
	canvas.width = videoEl.videoWidth;
	canvas.height = videoEl.videoHeight;
	canvas.getContext('2d').drawImage(videoEl, 0, 0, canvas.width, canvas.height);
	return new Promise((resolve, reject) => {
		canvas.toBlob(
			(b) => (b ? resolve(b) : reject(new Error('capture produced no blob'))),
			'image/jpeg',
			quality
		);
	});
}

/** Load a video off-screen, seek ~0.1s, capture, and save as its default still. */
export async function seedThumbnail(fbid, videoSrc) {
	const v = document.createElement('video');
	v.crossOrigin = 'anonymous';
	v.muted = true;
	v.preload = 'auto';
	v.src = videoSrc;
	await new Promise((res, rej) => {
		v.addEventListener('loadeddata', res, { once: true });
		v.addEventListener('error', () => rej(new Error('video load failed')), { once: true });
	});
	await new Promise((res) => {
		v.addEventListener('seeked', res, { once: true });
		v.currentTime = Math.min(0.1, (v.duration || 1) / 2);
	});
	const blob = await captureFrame(v);
	v.removeAttribute('src');
	v.load();
	return saveVideoThumbnail(fbid, blob);
}

/**
 * Seed default stills for videos that don't have one yet, one at a time so we don't
 * pull every mp4 at once. `needsSeed(fbid) -> Promise<bool>`, `videoSrc(fbid) -> url`.
 */
export async function seedMissingThumbnails(videos, { videoSrc, needsSeed, onSeeded }) {
	for (const v of videos) {
		try {
			if (!(await needsSeed(v.fbid))) continue;
			await seedThumbnail(v.fbid, videoSrc(v.fbid));
			onSeeded?.(v.fbid);
		} catch {
			/* leave the placeholder; the build reports videos with no still */
		}
	}
}

/** Default `needsSeed`: a video needs a default when GET thumbnail is not 200. */
export function thumbnailMissing(fbid, fetchFn = fetch) {
	return fetchFn(videoThumbUrl(fbid), { method: 'GET' })
		.then((r) => !r.ok)
		.catch(() => true);
}
