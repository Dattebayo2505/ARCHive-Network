import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import PhotoTile from './PhotoTile.svelte';

const photo = { fbid: 'p1', exists: true, selected: false, caption: null };

describe('PhotoTile srcset', () => {
	it('renders srcset and sizes on the image when provided', () => {
		render(PhotoTile, {
			props: {
				photo,
				src: '/thumb/p1',
				srcset: '/thumb/p1 512w, /preview/p1 1280w',
				sizes: '50vw'
			}
		});
		const img = screen.getByAltText('p1');
		expect(img).toHaveAttribute('srcset', '/thumb/p1 512w, /preview/p1 1280w');
		expect(img).toHaveAttribute('sizes', '50vw');
	});

	it('omits srcset and sizes entirely when not provided', () => {
		render(PhotoTile, { props: { photo, src: '/thumb/p1' } });
		const img = screen.getByAltText('p1');
		expect(img).not.toHaveAttribute('srcset');
		expect(img).not.toHaveAttribute('sizes');
	});
});
