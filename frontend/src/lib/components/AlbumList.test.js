import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import AlbumList from './AlbumList.svelte';

const albums = [
	{ fb_album_id: '111', name: 'Animo Fest', count_selected: 2, max_per_album: 10 },
	{ fb_album_id: '555', name: 'Mobile uploads', count_selected: 3, max_per_album: null }
];

describe('AlbumList', () => {
	it('shows a denominator only for capped albums', () => {
		render(AlbumList, {
			props: { albums, nonAlbumCount: 0, archiveCount: 2, activeId: '111', onSelect: vi.fn() }
		});
		expect(screen.getByText('2/10')).toBeInTheDocument(); // capped
		expect(screen.queryByText('3/10')).not.toBeInTheDocument(); // uncapped: no denominator
	});

	it('selects the archive section', async () => {
		const onSelect = vi.fn();
		render(AlbumList, {
			props: { albums, nonAlbumCount: 0, archiveCount: 2, activeId: '111', onSelect }
		});
		await fireEvent.click(screen.getByText('Archive'));
		expect(onSelect).toHaveBeenCalledWith('__archive__');
	});

	it('renders an origin subheader for derived albums', () => {
		const withOrigin = [
			{ fb_album_id: '111', name: 'Animo Fest', count_selected: 0, max_per_album: 10, origin: null },
			{ fb_album_id: 'g01', name: 'HEADLINE ONE', count_selected: 0, max_per_album: null, origin: 'Mobile uploads' },
			{ fb_album_id: 'g03', name: 'HEADLINE TWO', count_selected: 0, max_per_album: null, origin: 'Mobile uploads' }
		];
		render(AlbumList, {
			props: { albums: withOrigin, nonAlbumCount: 0, archiveCount: 0, activeId: '111', onSelect: vi.fn() }
		});
		expect(screen.getByText('Mobile uploads')).toBeInTheDocument();
		expect(screen.getByText('HEADLINE ONE')).toBeInTheDocument();
		expect(screen.getByText('HEADLINE TWO')).toBeInTheDocument();
	});
});
