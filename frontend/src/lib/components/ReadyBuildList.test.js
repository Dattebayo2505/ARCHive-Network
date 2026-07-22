import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import ReadyBuildList from './ReadyBuildList.svelte';

const BUILDS = [
	{
		id: 'b1',
		display_name: 'MyPage Export | 2026-07-20',
		built_ts: 1_753_000_000,
		size_bytes: 12 * 1024 * 1024,
		photos: 8,
		videos: 2,
		albums: 3
	},
	{
		id: 'b2',
		display_name: 'MyPage Export | 2026-07-13',
		built_ts: 1_752_000_000,
		size_bytes: 5 * 1024 * 1024,
		photos: null,
		videos: null,
		albums: null
	}
];

describe('ReadyBuildList', () => {
	it('renders a row per build with name and counts', () => {
		render(ReadyBuildList, { builds: BUILDS, onReveal: () => {} });
		expect(screen.getByText('MyPage Export | 2026-07-20')).toBeTruthy();
		expect(screen.getByText(/8 photos · 2 videos · 3 albums/)).toBeTruthy();
	});

	it('renders a build with null counts without a counts segment', () => {
		render(ReadyBuildList, { builds: [BUILDS[1]], onReveal: () => {} });
		expect(screen.getByText('MyPage Export | 2026-07-13')).toBeTruthy();
		expect(screen.queryByText(/photo/)).toBeNull();
	});

	it('calls onReveal with the build id when the button is clicked', async () => {
		const onReveal = vi.fn();
		render(ReadyBuildList, { builds: [BUILDS[0]], onReveal });
		await fireEvent.click(screen.getByRole('button', { name: /open in explorer/i }));
		expect(onReveal).toHaveBeenCalledWith('b1');
	});

	// Destructive, so the trash must arm the inline band and never delete on its own —
	// the same two-click shape the workspace rows use.
	it('does not call onDelete until the inline confirm is accepted', async () => {
		const onDelete = vi.fn();
		render(ReadyBuildList, { builds: [BUILDS[0]], onReveal: () => {}, onDelete });

		await fireEvent.click(
			screen.getByRole('button', { name: /delete the ready folder MyPage Export \| 2026-07-20/i })
		);
		expect(onDelete).not.toHaveBeenCalled();
		expect(screen.getByText('Delete ready folder?')).toBeTruthy();

		await fireEvent.click(screen.getByRole('button', { name: /^delete folder$/i }));
		expect(onDelete).toHaveBeenCalledWith('b1');
	});

	it('cancelling the confirm restores the row and deletes nothing', async () => {
		const onDelete = vi.fn();
		render(ReadyBuildList, { builds: [BUILDS[0]], onReveal: () => {}, onDelete });

		await fireEvent.click(screen.getByRole('button', { name: /^delete the ready folder/i }));
		await fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));

		expect(onDelete).not.toHaveBeenCalled();
		expect(screen.queryByText('Delete ready folder?')).toBeNull();
		expect(screen.getByRole('button', { name: /^delete the ready folder/i })).toBeTruthy();
	});

	// Two rows armed at once would put two identical "Delete folder" buttons on screen
	// with nothing to tell them apart — the second arm has to disarm the first.
	it('only ever arms one row at a time', async () => {
		render(ReadyBuildList, { builds: BUILDS, onReveal: () => {}, onDelete: () => {} });
		const [first, second] = screen.getAllByRole('button', { name: /^delete the ready folder/i });

		await fireEvent.click(first);
		await fireEvent.click(second);

		expect(screen.getAllByText('Delete ready folder?')).toHaveLength(1);
	});
});
