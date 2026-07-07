import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import WorkspaceList from './WorkspaceList.svelte';

const WS = [
	{ id: 'w1', display_name: 'MyPage Facebook Export | 2026-07-03', raw_name: 'facebook-...-7xOuGnNl', last_opened_ts: 2, managed: true },
	{ id: 'w2', display_name: 'MyPage Facebook Export | 2026-06-08', raw_name: 'facebook-...-Th2bzEER', last_opened_ts: 1, managed: false }
];

describe('WorkspaceList', () => {
	it('renders a card per workspace with its display name', () => {
		render(WorkspaceList, { workspaces: WS, onOpen: () => {}, onRemove: () => {} });
		expect(screen.getByText('MyPage Facebook Export | 2026-07-03')).toBeTruthy();
		expect(screen.getByText('MyPage Facebook Export | 2026-06-08')).toBeTruthy();
	});

	it('calls onOpen with the id when a card is clicked', async () => {
		const onOpen = vi.fn();
		render(WorkspaceList, { workspaces: WS, onOpen, onRemove: () => {} });
		await fireEvent.click(screen.getByText('MyPage Facebook Export | 2026-07-03'));
		expect(onOpen).toHaveBeenCalledWith('w1');
	});

	it('requires two steps before calling onRemove', async () => {
		const onRemove = vi.fn();
		render(WorkspaceList, { workspaces: [WS[0]], onOpen: () => {}, onRemove });

		await fireEvent.click(screen.getByRole('button', { name: /remove/i }));
		expect(onRemove).not.toHaveBeenCalled();                 // first click only reveals confirm

		await fireEvent.click(screen.getByRole('button', { name: /delete permanently/i }));
		expect(onRemove).toHaveBeenCalledWith('w1', true);       // managed -> delete files
	});
});
