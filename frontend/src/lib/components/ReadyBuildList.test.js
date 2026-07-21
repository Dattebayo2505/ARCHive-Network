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
});
