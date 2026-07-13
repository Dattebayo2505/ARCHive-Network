import { fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AlbumList from './AlbumList.svelte';
import { devMode } from '$lib/devmode.svelte.js';

const albums = [
	{ fb_album_id: '111', name: 'Animo Fest', count_selected: 2, max_per_album: 10 },
	{ fb_album_id: '555', name: 'Mobile uploads', count_selected: 3, max_per_album: null }
];

describe('AlbumList', () => {
	it('shows a denominator only for capped albums', () => {
		render(AlbumList, {
			props: { albums, archiveCount: 2, activeId: '111', onSelect: vi.fn() }
		});
		expect(screen.getByText('2/10')).toBeInTheDocument(); // capped
		expect(screen.queryByText('3/10')).not.toBeInTheDocument(); // uncapped: no denominator
	});

	it('selects the archive section', async () => {
		const onSelect = vi.fn();
		render(AlbumList, {
			props: { albums, archiveCount: 2, activeId: '111', onSelect }
		});
		await fireEvent.click(screen.getByText('Archive'));
		expect(onSelect).toHaveBeenCalledWith('__archive__');
	});

	it('shows a Videos entry and selects it', async () => {
		const onSelect = vi.fn();
		render(AlbumList, {
			props: { albums: [], videosCount: 3, activeId: null, onSelect, onContextMenu: vi.fn() }
		});
		const btn = screen.getByRole('button', { name: /videos/i });
		expect(btn).toBeInTheDocument();
		await fireEvent.click(btn);
		expect(onSelect).toHaveBeenCalledWith('__videos__');
	});

	it('renders an origin subheader for derived albums', () => {
		const withOrigin = [
			{ fb_album_id: '111', name: 'Animo Fest', count_selected: 0, max_per_album: 10, origin: null },
			{ fb_album_id: 'g01', name: 'HEADLINE ONE', count_selected: 0, max_per_album: null, origin: 'Mobile uploads' },
			{ fb_album_id: 'g03', name: 'HEADLINE TWO', count_selected: 0, max_per_album: null, origin: 'Mobile uploads' }
		];
		render(AlbumList, {
			props: { albums: withOrigin, archiveCount: 0, activeId: '111', onSelect: vi.fn() }
		});
		expect(screen.getByText('Mobile uploads')).toBeInTheDocument();
		expect(screen.getByText('HEADLINE ONE')).toBeInTheDocument();
		expect(screen.getByText('HEADLINE TWO')).toBeInTheDocument();
	});

	describe('Dev Mode entry', () => {
		afterEach(() => devMode.set(false));

		it('is hidden unless dev mode is enabled', () => {
			devMode.set(false);
			render(AlbumList, { props: { albums, activeId: '111', onSelect: vi.fn() } });
			expect(screen.queryByText('Dev Mode')).not.toBeInTheDocument();
		});

		it('appears and is selectable when dev mode is enabled', async () => {
			devMode.set(true);
			const onSelect = vi.fn();
			render(AlbumList, { props: { albums, activeId: '111', onSelect } });

			const entry = screen.getByText('Dev Mode');
			expect(entry).toBeInTheDocument();
			await fireEvent.click(entry);
			expect(onSelect).toHaveBeenCalledWith('__dev__');
		});
	});
});
