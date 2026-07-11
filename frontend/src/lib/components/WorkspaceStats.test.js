import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import WorkspaceStats from './WorkspaceStats.svelte';
import { getInventory } from '$lib/api.js';

vi.mock('$lib/api.js', () => ({
	getInventory: vi.fn()
}));

const photo = (over = {}) => ({
	fbid: 'p',
	exists: true,
	file_size_bytes: 1_048_576, // 1 MB
	creation_at: null,
	post_timestamp: null,
	taken_timestamp: null,
	...over
});

const INV = {
	albums: [
		{
			fb_album_id: 'a1',
			origin: null,
			count_selected: 2,
			photos: [
				photo({ taken_timestamp: '2099-07-01T10:00:00' }),
				photo({ taken_timestamp: '2099-07-04T10:00:00' })
			]
		},
		{ fb_album_id: 'a2', origin: 'Mobile uploads', count_selected: 0, photos: [photo()] }
	],
	archived_albums: [],
	non_album: [photo()],
	archive: [],
	videos: [photo({ post_timestamp: '2099-07-02T10:00:00' })]
};

describe('WorkspaceStats', () => {
	beforeEach(() => vi.clearAllMocks());

	it('renders the workspace name and the computed stat rows', async () => {
		getInventory.mockResolvedValue(INV);
		render(WorkspaceStats, { displayName: 'MyPage | 2099-07-05', onClose: () => {} });

		expect(await screen.findByText('MyPage | 2099-07-05')).toBeTruthy();
		expect(await screen.findByText('Jul 1 (Wed), 2099 – Jul 4 (Sat), 2099')).toBeTruthy();
		expect(screen.getByText('1 (+1 derived)')).toBeTruthy(); // albums: main (+derived)
		expect(screen.getByText('4')).toBeTruthy(); // photos: 3 in albums + 1 non-album
		expect(screen.getByText('4.0 MB')).toBeTruthy(); // photos only, not the video thumb
	});

	it('closes from the ✕ button and from Escape', async () => {
		getInventory.mockResolvedValue(INV);
		const onClose = vi.fn();
		render(WorkspaceStats, { displayName: 'ws', onClose });

		await fireEvent.click(screen.getByRole('button', { name: /close/i }));
		expect(onClose).toHaveBeenCalledTimes(1);

		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		expect(onClose).toHaveBeenCalledTimes(2);
	});

	it('shows a readable message when the inventory cannot load', async () => {
		getInventory.mockResolvedValue(null); // 404 — no session
		render(WorkspaceStats, { displayName: 'ws', onClose: () => {} });
		expect(await screen.findByText(/couldn't load/i)).toBeTruthy();
	});
});
