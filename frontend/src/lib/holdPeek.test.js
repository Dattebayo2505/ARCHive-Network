import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { holdPeek } from './holdPeek.js';

function pointerEvent(type, { x = 0, y = 0, button = 0, pointerId = 1, isPrimary = true } = {}) {
	const e = new MouseEvent(type, { bubbles: true, cancelable: true, button });
	Object.defineProperty(e, 'clientX', { value: x });
	Object.defineProperty(e, 'clientY', { value: y });
	Object.defineProperty(e, 'pointerId', { value: pointerId });
	Object.defineProperty(e, 'isPrimary', { value: isPrimary });
	return e;
}

function setup(opts) {
	const node = document.createElement('div');
	document.body.appendChild(node);
	const onStart = vi.fn();
	const onEnd = vi.fn();
	const action = holdPeek(node, { onStart, onEnd, ...opts });
	return {
		node,
		onStart,
		onEnd,
		action,
		destroy() {
			action.destroy();
			node.remove();
		}
	};
}

let active;
beforeEach(() => vi.useFakeTimers());
afterEach(() => {
	active?.destroy();
	active = null;
	vi.useRealTimers();
	vi.restoreAllMocks();
});

describe('holdPeek', () => {
	it('starts the peek after the hold delay', () => {
		active = setup();
		active.node.dispatchEvent(pointerEvent('pointerdown'));
		expect(active.onStart).not.toHaveBeenCalled();
		vi.advanceTimersByTime(450);
		expect(active.onStart).toHaveBeenCalledOnce();
	});

	it('does not peek on a quick click, and the click still goes through', () => {
		active = setup();
		const inner = document.createElement('button');
		active.node.appendChild(inner);
		const onClick = vi.fn();
		inner.addEventListener('click', onClick);

		active.node.dispatchEvent(pointerEvent('pointerdown'));
		vi.advanceTimersByTime(200);
		window.dispatchEvent(pointerEvent('pointerup'));
		inner.dispatchEvent(pointerEvent('click'));
		vi.runAllTimers();

		expect(active.onStart).not.toHaveBeenCalled();
		expect(active.onEnd).not.toHaveBeenCalled();
		expect(onClick).toHaveBeenCalledOnce();
	});

	it('ends the peek on release and suppresses the trailing click', () => {
		active = setup();
		const inner = document.createElement('button');
		active.node.appendChild(inner);
		const onClick = vi.fn();
		inner.addEventListener('click', onClick);

		active.node.dispatchEvent(pointerEvent('pointerdown'));
		vi.advanceTimersByTime(450);
		expect(active.onStart).toHaveBeenCalledOnce();

		window.dispatchEvent(pointerEvent('pointerup'));
		expect(active.onEnd).toHaveBeenCalledOnce();
		inner.dispatchEvent(pointerEvent('click'));
		expect(onClick).not.toHaveBeenCalled();
	});

	it('does not swallow later, unrelated clicks', () => {
		active = setup();
		const inner = document.createElement('button');
		active.node.appendChild(inner);
		const onClick = vi.fn();
		inner.addEventListener('click', onClick);

		active.node.dispatchEvent(pointerEvent('pointerdown'));
		vi.advanceTimersByTime(450);
		window.dispatchEvent(pointerEvent('pointercancel')); // release without a click
		vi.runAllTimers(); // suppressor disarms

		inner.dispatchEvent(pointerEvent('click'));
		expect(onClick).toHaveBeenCalledOnce();
	});

	it('cancels a pending peek when the pointer moves past the slop', () => {
		active = setup();
		active.node.dispatchEvent(pointerEvent('pointerdown', { x: 10, y: 10 }));
		active.node.dispatchEvent(pointerEvent('pointermove', { x: 30, y: 10 }));
		vi.advanceTimersByTime(450);
		expect(active.onStart).not.toHaveBeenCalled();
	});

	it('survives movement within the slop', () => {
		active = setup();
		active.node.dispatchEvent(pointerEvent('pointerdown', { x: 10, y: 10 }));
		active.node.dispatchEvent(pointerEvent('pointermove', { x: 13, y: 12 }));
		vi.advanceTimersByTime(450);
		expect(active.onStart).toHaveBeenCalledOnce();
	});

	it('ignores non-primary buttons', () => {
		active = setup();
		active.node.dispatchEvent(pointerEvent('pointerdown', { button: 2 }));
		vi.advanceTimersByTime(450);
		expect(active.onStart).not.toHaveBeenCalled();
	});

	it('does nothing while disabled, and re-arms after update', () => {
		active = setup({ enabled: false });
		active.node.dispatchEvent(pointerEvent('pointerdown'));
		vi.advanceTimersByTime(450);
		expect(active.onStart).not.toHaveBeenCalled();

		active.action.update({ enabled: true, onStart: active.onStart, onEnd: active.onEnd });
		active.node.dispatchEvent(pointerEvent('pointerdown'));
		vi.advanceTimersByTime(450);
		expect(active.onStart).toHaveBeenCalledOnce();
	});

	it('ends an active peek on destroy', () => {
		active = setup();
		active.node.dispatchEvent(pointerEvent('pointerdown'));
		vi.advanceTimersByTime(450);
		active.destroy();
		expect(active.onEnd).toHaveBeenCalledOnce();
		active = null;
	});
});
