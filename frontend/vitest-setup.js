// frontend/vitest-setup.js
import '@testing-library/jest-dom/vitest';

// jsdom lacks ResizeObserver, which Svelte's bind:clientWidth/clientHeight relies on.
globalThis.ResizeObserver ??= class {
	observe() {}
	unobserve() {}
	disconnect() {}
};
