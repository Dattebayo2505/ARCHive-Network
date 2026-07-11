// frontend/vitest-setup.js
import '@testing-library/jest-dom/vitest';

// jsdom lacks ResizeObserver, which Svelte's bind:clientWidth/clientHeight relies on.
globalThis.ResizeObserver ??= class {
	observe() {}
	unobserve() {}
	disconnect() {}
};

// jsdom lacks the Web Animations API, which Svelte 5 transitions are built on:
// without it the outro throws and the outgoing element is never removed. The
// stub fires onfinish through a timeout so fake-timer tests can flush it.
if (!Element.prototype.animate) {
	class FakeAnimation {
		onfinish = null;
		oncancel = null;
		playState = 'finished';
		constructor(duration) {
			this.currentTime = duration;
			this._timer = setTimeout(() => this.onfinish?.(), duration);
		}
		cancel() {
			clearTimeout(this._timer);
		}
		finish() {
			clearTimeout(this._timer);
			this.onfinish?.();
		}
	}
	Element.prototype.animate = function (_keyframes, options = {}) {
		const duration = typeof options === 'number' ? options : (options.duration ?? 0);
		return new FakeAnimation(duration);
	};
}

// jsdom lacks matchMedia, which reduced-motion checks rely on.
globalThis.matchMedia ??= (query) => ({
	matches: false,
	media: query,
	addEventListener() {},
	removeEventListener() {},
	addListener() {},
	removeListener() {},
	dispatchEvent() {
		return false;
	}
});
