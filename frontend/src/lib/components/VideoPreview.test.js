import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../videoThumbs.js', () => ({
	captureFrame: vi.fn().mockResolvedValue(new Blob(['f'], { type: 'image/jpeg' }))
}));
vi.mock('../api.js', () => ({
	videoUrl: (id) => `/api/video/${id}`,
	videoThumbUrl: (id) => `/api/video/${id}/thumbnail`,
	saveVideoThumbnail: vi.fn().mockResolvedValue({ ok: true })
}));

import { saveVideoThumbnail } from '../api.js';
import { captureFrame } from '../videoThumbs.js';
import VideoPreview from './VideoPreview.svelte';

describe('VideoPreview', () => {
	it('captures and saves the current frame, then notifies', async () => {
		const onThumbnailChosen = vi.fn();
		const { container } = render(VideoPreview, {
			props: { video: { fbid: 'v01', caption: 'clip' }, onClose: vi.fn(), onThumbnailChosen }
		});
		// A frame must be decoded before capture is enabled.
		const videoEl = container.querySelector('video');
		Object.defineProperty(videoEl, 'videoWidth', { value: 320, configurable: true });
		Object.defineProperty(videoEl, 'videoHeight', { value: 240, configurable: true });
		await fireEvent(videoEl, new Event('loadeddata'));

		await fireEvent.click(screen.getByRole('button', { name: /choose thumbnail/i }));
		expect(captureFrame).toHaveBeenCalledOnce();
		expect(saveVideoThumbnail).toHaveBeenCalledWith('v01', expect.any(Blob), false, 0);
		expect(onThumbnailChosen).toHaveBeenCalledWith('v01', undefined, 0);
	});

	it('keeps the capture button disabled until a frame is ready', () => {
		render(VideoPreview, {
			props: { video: { fbid: 'v01', caption: 'clip' }, onClose: vi.fn(), onThumbnailChosen: vi.fn() }
		});
		expect(screen.getByRole('button', { name: /loading/i })).toBeDisabled();
	});
});
