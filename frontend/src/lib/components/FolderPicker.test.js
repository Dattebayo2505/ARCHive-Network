import { render, screen, waitFor } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import FolderPicker from './FolderPicker.svelte';
import * as api from '$lib/api.js';

vi.mock('$lib/api.js', () => ({
	browse: vi.fn()
}));

describe('FolderPicker', () => {
	it('displays "Locations" when drives are Unix paths', async () => {
		vi.mocked(api.browse).mockResolvedValueOnce({
			ok: true,
			path: '/Users/alice',
			parent: '/Users',
			dirs: [],
			files: [],
			is_export: false,
			drives: ['/', '/Volumes/Data']
		});

		render(FolderPicker, { open: true });

		await waitFor(() => {
			expect(screen.getByText('Locations')).toBeTruthy();
		});
	});

	it('displays "Drives" when drives are Windows drive letters', async () => {
		vi.mocked(api.browse).mockResolvedValueOnce({
			ok: true,
			path: 'C:\\Users\\alice',
			parent: 'C:\\Users',
			dirs: [],
			files: [],
			is_export: false,
			drives: ['C:\\', 'D:\\']
		});

		render(FolderPicker, { open: true });

		await waitFor(() => {
			expect(screen.getByText('Drives')).toBeTruthy();
		});
	});
});
