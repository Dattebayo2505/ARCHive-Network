import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import PhotoGrid from './PhotoGrid.svelte';

const album = {
	name: 'Test',
	photos: [{ fbid: 'p1', exists: true, selected: false, caption: null }]
};

describe('PhotoGrid responsive thumbnails', () => {
	it('gives photo tiles a srcset of thumb + preview and a sizes hint from the column count', () => {
		render(PhotoGrid, {
			props: {
				album,
				size: 'xl', // 2 cols → 50vw
				thumb: (id) => `/thumb/${id}`,
				preview: (id) => `/preview/${id}`
			}
		});
		const img = screen.getByAltText('p1');
		expect(img).toHaveAttribute('srcset', '/thumb/p1 512w, /preview/p1 1280w');
		expect(img).toHaveAttribute('sizes', '50vw');
	});

	it('derives the sizes hint from the current grid size', () => {
		render(PhotoGrid, {
			props: {
				album,
				size: 'm', // 6 cols → round(100/6) = 17vw
				thumb: (id) => `/thumb/${id}`,
				preview: (id) => `/preview/${id}`
			}
		});
		expect(screen.getByAltText('p1')).toHaveAttribute('sizes', '17vw');
	});

	it('renders no srcset when the grid has no preview source (videos grid)', () => {
		render(PhotoGrid, {
			props: {
				album,
				video: true,
				thumb: (id) => `/vthumb/${id}`
			}
		});
		const img = screen.getByAltText('p1');
		expect(img).not.toHaveAttribute('srcset');
		expect(img).not.toHaveAttribute('sizes');
	});
});
