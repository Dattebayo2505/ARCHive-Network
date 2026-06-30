import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import PhotoTile from './PhotoTile.svelte';

describe('PhotoTile', () => {
	it('calls onToggle when an existing, selectable tile is clicked', async () => {
		const onToggle = vi.fn();
		render(PhotoTile, {
			props: {
				photo: { fbid: 'a01', exists: true, selected: false, caption: null },
				src: '/x.jpg',
				selectable: true,
				onToggle
			}
		});
		await fireEvent.click(screen.getByTestId('tile-a01'));
		expect(onToggle).toHaveBeenCalledOnce();
	});

	it('disables an orphan tile', () => {
		render(PhotoTile, {
			props: {
				photo: { fbid: 'm02', exists: false, selected: false, caption: null },
				onToggle: vi.fn()
			}
		});
		expect(screen.getByTestId('tile-m02')).toBeDisabled();
	});
});
