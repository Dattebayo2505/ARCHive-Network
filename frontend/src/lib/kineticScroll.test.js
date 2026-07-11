import { afterEach, describe, expect, it, vi } from 'vitest';
import { kineticScroll } from './kineticScroll.js';

function mouseEvent(type, { x = 0, y = 0, button = 0 } = {}) {
	const e = new MouseEvent(type, { bubbles: true, cancelable: true, button });
	// jsdom derives pageX/pageY lazily; pin them so the action sees our values.
	Object.defineProperty(e, 'pageX', { value: x });
	Object.defineProperty(e, 'pageY', { value: y });
	return e;
}

function setup(opts) {
	const node = document.createElement('div');
	document.body.appendChild(node);
	const action = kineticScroll(node, opts);
	return {
		node,
		destroy() {
			action.destroy();
			node.remove();
		}
	};
}

let active;
afterEach(() => {
	active?.destroy();
	active = null;
	vi.restoreAllMocks();
});

describe('kineticScroll', () => {
	it('drags scrollTop on the default (vertical) axis', () => {
		active = setup();
		const { node } = active;
		node.scrollTop = 100;
		node.dispatchEvent(mouseEvent('mousedown', { y: 50 }));
		window.dispatchEvent(mouseEvent('mousemove', { y: 10 })); // pull up 40px
		expect(node.scrollTop).toBe(140);
		window.dispatchEvent(mouseEvent('mouseup'));
	});

	it('ignores movement under the 5px drag threshold', () => {
		active = setup();
		const { node } = active;
		node.scrollTop = 100;
		node.dispatchEvent(mouseEvent('mousedown', { y: 50 }));
		window.dispatchEvent(mouseEvent('mousemove', { y: 47 }));
		expect(node.scrollTop).toBe(100);
		window.dispatchEvent(mouseEvent('mouseup'));
	});

	it('suppresses the click that ends a drag, so tiles are not removed', () => {
		active = setup();
		const { node } = active;
		const tile = document.createElement('button');
		node.appendChild(tile);
		const onTileClick = vi.fn();
		tile.addEventListener('click', onTileClick);

		node.dispatchEvent(mouseEvent('mousedown', { y: 50 }));
		window.dispatchEvent(mouseEvent('mousemove', { y: 100 }));
		window.dispatchEvent(mouseEvent('mouseup'));
		tile.dispatchEvent(mouseEvent('click'));
		expect(onTileClick).not.toHaveBeenCalled();
	});

	it('lets a clean (undragged) click through', () => {
		active = setup();
		const { node } = active;
		const tile = document.createElement('button');
		node.appendChild(tile);
		const onTileClick = vi.fn();
		tile.addEventListener('click', onTileClick);

		node.dispatchEvent(mouseEvent('mousedown', { y: 50 }));
		window.dispatchEvent(mouseEvent('mouseup'));
		tile.dispatchEvent(mouseEvent('click'));
		expect(onTileClick).toHaveBeenCalledOnce();
	});

	it('drags scrollLeft on the x axis', () => {
		active = setup({ axis: 'x' });
		const { node } = active;
		node.scrollLeft = 100;
		node.dispatchEvent(mouseEvent('mousedown', { x: 50 }));
		window.dispatchEvent(mouseEvent('mousemove', { x: 20 }));
		expect(node.scrollLeft).toBe(130);
		window.dispatchEvent(mouseEvent('mouseup'));
	});

	it('maps a vertical wheel onto scrollLeft for the x axis', () => {
		active = setup({ axis: 'x' });
		const { node } = active;
		node.scrollLeft = 0;
		const e = new WheelEvent('wheel', { deltaY: 48, bubbles: true, cancelable: true });
		node.dispatchEvent(e);
		expect(node.scrollLeft).toBe(48);
		expect(e.defaultPrevented).toBe(true);
	});

	it('does not hijack the wheel on the vertical axis', () => {
		active = setup();
		const { node } = active;
		const e = new WheelEvent('wheel', { deltaY: 48, bubbles: true, cancelable: true });
		node.dispatchEvent(e);
		expect(e.defaultPrevented).toBe(false);
	});

	it('glides on after a fast release (momentum)', async () => {
		// Deterministic clock + rAF: each frame advances 16ms.
		let now = 0;
		vi.spyOn(performance, 'now').mockImplementation(() => now);
		const queue = [];
		vi.stubGlobal('requestAnimationFrame', (cb) => queue.push(cb) && queue.length);
		vi.stubGlobal('cancelAnimationFrame', () => {});

		active = setup();
		const { node } = active;
		node.scrollTop = 500;
		node.dispatchEvent(mouseEvent('mousedown', { y: 200 }));
		now = 16;
		window.dispatchEvent(mouseEvent('mousemove', { y: 150 })); // fast upward flick
		now = 32;
		window.dispatchEvent(mouseEvent('mousemove', { y: 100 }));
		window.dispatchEvent(mouseEvent('mouseup'));

		const atRelease = node.scrollTop;
		expect(queue.length).toBe(1); // a glide was scheduled
		// Pump frames until the glide decays out.
		for (let i = 0; i < 200 && queue.length; i++) {
			now += 16;
			queue.shift()(now);
		}
		expect(node.scrollTop).toBeGreaterThan(atRelease); // kept scrolling downward-in-content
		expect(queue.length).toBe(0); // and came to rest
	});

	it('does not glide when the pointer held still before release (a place, not a throw)', () => {
		let now = 0;
		vi.spyOn(performance, 'now').mockImplementation(() => now);
		const queue = [];
		vi.stubGlobal('requestAnimationFrame', (cb) => queue.push(cb) && queue.length);
		vi.stubGlobal('cancelAnimationFrame', () => {});

		active = setup();
		const { node } = active;
		node.scrollTop = 500;
		node.dispatchEvent(mouseEvent('mousedown', { y: 200 }));
		now = 16;
		window.dispatchEvent(mouseEvent('mousemove', { y: 100 })); // fast flick...
		now = 400; // ...then held still for ~384ms
		window.dispatchEvent(mouseEvent('mouseup'));
		expect(queue.length).toBe(0); // no glide scheduled
	});
});
