import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import BuildConfirmDialog from './BuildConfirmDialog.svelte';

const EXISTING = {
	id: 'facebook-mypage-2026-07-20',
	display_name: 'MyPage Export | 2026-07-20',
	built_ts: 1_753_000_000,
	size_bytes: 12 * 1024 * 1024,
	photos: 8,
	videos: 2,
	albums: 3
};

const BASE = { open: true, albumsToBuild: [], totalImages: 4, totalVideos: 0, totalMB: '1.0' };

describe('BuildConfirmDialog', () => {
	it('says nothing about overwriting when no build exists yet', () => {
		render(BuildConfirmDialog, { ...BASE, existingBuild: null });
		expect(screen.queryByTestId('overwrite-warning')).toBeNull();
		expect(screen.getByRole('heading', { name: 'Build ready folder' })).toBeTruthy();
		expect(screen.getByRole('button', { name: /yes, build it/i })).toBeTruthy();
	});

	it('warns that an existing build will be overwritten', () => {
		render(BuildConfirmDialog, { ...BASE, existingBuild: EXISTING });
		expect(screen.getByTestId('overwrite-warning')).toBeTruthy();
		expect(screen.getByText(/a ready folder already exists/i)).toBeTruthy();
		expect(screen.getByRole('heading', { name: 'Rebuild ready folder' })).toBeTruthy();
		expect(screen.getByRole('button', { name: /yes, overwrite it/i })).toBeTruthy();
	});

	it('requires the second confirm before calling onConfirm', async () => {
		const onConfirm = vi.fn();
		render(BuildConfirmDialog, { ...BASE, existingBuild: EXISTING, onConfirm });

		await fireEvent.click(screen.getByRole('button', { name: /yes, overwrite it/i }));
		expect(onConfirm).not.toHaveBeenCalled();
		// The second step names the folder at risk, so the destructive step is unambiguous.
		expect(screen.getByRole('heading', { name: /overwrite existing build\?/i })).toBeTruthy();
		expect(screen.getByText(new RegExp(EXISTING.display_name))).toBeTruthy();

		await fireEvent.click(screen.getByRole('button', { name: 'Overwrite' }));
		expect(onConfirm).toHaveBeenCalledTimes(1);
	});
});
