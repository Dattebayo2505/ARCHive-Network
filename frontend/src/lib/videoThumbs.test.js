import { describe, expect, it, vi } from 'vitest';
import { captureFrame } from './videoThumbs.js';

describe('captureFrame', () => {
	it('draws the video and resolves the canvas blob', async () => {
		const blob = new Blob(['frame'], { type: 'image/jpeg' });
		const ctx = { drawImage: vi.fn() };
		const canvas = {
			width: 0,
			height: 0,
			getContext: () => ctx,
			toBlob: (cb) => cb(blob)
		};
		vi.spyOn(document, 'createElement').mockReturnValue(canvas);
		const video = { videoWidth: 320, videoHeight: 240 };

		const out = await captureFrame(video);
		expect(out).toBe(blob);
		expect(canvas.width).toBe(320);
		expect(canvas.height).toBe(240);
		expect(ctx.drawImage).toHaveBeenCalledWith(video, 0, 0, 320, 240);
	});
});
