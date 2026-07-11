import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import PhotoGrid from './PhotoGrid.svelte';

function pointerEvent(type, { x = 0, y = 0, button = 0 } = {}) {
	const e = new MouseEvent(type, { bubbles: true, cancelable: true, button });
	Object.defineProperty(e, 'clientX', { value: x });
	Object.defineProperty(e, 'clientY', { value: y });
	Object.defineProperty(e, 'isPrimary', { value: true });
	return e;
}

const album = {
	name: 'Test',
	photos: [{ fbid: 'p1', exists: true, selected: false, caption: null }]
};

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('PhotoGrid hold-to-peek', () => {
	it('shows the peek overlay on hold and removes it on release', async () => {
		render(PhotoGrid, {
			props: { album, thumb: (id) => `/thumb/${id}`, preview: (id) => `/preview/${id}` }
		});
		const tile = screen.getByTestId('tile-p1');

		tile.dispatchEvent(pointerEvent('pointerdown'));
		vi.advanceTimersByTime(450);
		await tick();
		expect(screen.getByTestId('peek-overlay')).toBeInTheDocument();

		window.dispatchEvent(pointerEvent('pointerup'));
		await tick();
		vi.runAllTimers(); // let the out transition finish
		await tick();
		expect(screen.queryByTestId('peek-overlay')).toBeNull();
	});
});
