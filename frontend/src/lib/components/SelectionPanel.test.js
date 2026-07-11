import { render } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';

import SelectionPanel from './SelectionPanel.svelte';
import SelectionStrip from './SelectionStrip.svelte';

// The dock mirrors whichever surface is showing — for Videos, thumbnails live at
// /api/video/{fbid}/thumbnail (cache-busted per pick), not /api/thumb. The page
// passes the surface's thumb function down; the dock must use it.
describe('selection dock thumb source', () => {
	const album = {
		name: 'Videos',
		photos: [{ fbid: 'v01', caption: 'clip', selected: true, exists: true }]
	};
	const videoThumb = (fbid) => `/api/video/${fbid}/thumbnail?v=7`;

	it('SelectionPanel renders tiles with the provided thumb function', () => {
		const { container } = render(SelectionPanel, {
			props: { album, open: true, thumb: videoThumb }
		});
		const img = container.querySelector('img.thumb-img');
		expect(img?.getAttribute('src')).toBe('/api/video/v01/thumbnail?v=7');
	});

	it('SelectionStrip renders tiles with the provided thumb function', () => {
		const { container } = render(SelectionStrip, {
			props: { album, open: true, thumb: videoThumb }
		});
		const img = container.querySelector('img.thumb-img');
		expect(img?.getAttribute('src')).toBe('/api/video/v01/thumbnail?v=7');
	});
});
