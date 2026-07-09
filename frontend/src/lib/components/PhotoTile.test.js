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
				selectionEnabled: true,
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
		expect(screen.getByTestId('tile-m02')).toHaveAttribute('aria-disabled', 'true');
	});

	it('is inert and shows its tag when not selectable (archive tile)', async () => {
		const onToggle = vi.fn();
		render(PhotoTile, {
			props: {
				photo: { fbid: 'u01', exists: true, caption: 'BREAKING: fire', archive_tag: 'BREAKING' },
				src: '/x.jpg',
				selectable: false,
				onToggle
			}
		});
		const tile = screen.getByTestId('tile-u01');
		expect(tile).toHaveAttribute('aria-disabled', 'true');
		await fireEvent.click(tile);
		expect(onToggle).not.toHaveBeenCalled();
		expect(screen.getByText('BREAKING')).toBeInTheDocument();
	});

	it('renders a video tile with a play badge, no checkmark, and opens on click', async () => {
		const onToggle = vi.fn();
		render(PhotoTile, {
			props: {
				photo: { fbid: 'v01', exists: true, caption: 'clip' },
				src: '/api/video/v01/thumbnail',
				video: true,
				selectable: true,
				selectionEnabled: true,
				onToggle
			}
		});
		const tile = screen.getByTestId('tile-v01');
		expect(tile).not.toHaveAttribute('aria-disabled', 'true');
		expect(screen.getByTestId('video-badge-v01')).toBeInTheDocument();
		await fireEvent.click(tile);
		expect(onToggle).toHaveBeenCalledOnce();
	});
});
