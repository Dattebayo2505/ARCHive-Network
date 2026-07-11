/**
 * Momentum drag-scrolling for the selection docks: hold the mouse to scroll, and
 * a fast release "throws" the list, which glides on with exponential decay.
 * Mouse-only on purpose — touch already gets native momentum scrolling.
 *
 * Options:
 *   axis: 'y' (default) scrolls scrollTop from vertical drags;
 *         'x' scrolls scrollLeft from horizontal drags AND maps the mouse wheel's
 *         vertical delta onto scrollLeft, so a plain wheel drives a horizontal dock.
 */
const GLIDE_TAU = 325; // ms — decay constant for the glide (~native-scroll feel)
const MIN_FLICK = 0.05; // px/ms — release slower than this and there is no glide
const STOP_AT = 0.02; // px/ms — the glide ends once velocity decays below this
const SAMPLE_WINDOW = 100; // ms of trailing pointer samples used for release velocity

export function kineticScroll(node, opts = {}) {
	const axis = opts.axis === 'x' ? 'x' : 'y';
	const prop = axis === 'x' ? 'scrollLeft' : 'scrollTop';

	let isDown = false;
	let dragged = false;
	let startPos = 0;
	let startScroll = 0;
	let samples = []; // trailing {t, p} pointer positions for the release velocity
	let glideFrame = 0;

	// Guarded: jsdom (unit tests) has no matchMedia.
	const reducedMotion =
		typeof window.matchMedia === 'function'
			? window.matchMedia('(prefers-reduced-motion: reduce)')
			: null;

	const page = (e) => (axis === 'x' ? e.pageX : e.pageY);

	function stopGlide() {
		if (glideFrame) cancelAnimationFrame(glideFrame);
		glideFrame = 0;
	}

	function mousedown(e) {
		if (e.button !== 0) return; // left button only
		stopGlide(); // grabbing a gliding list stops it, like native scrolling
		isDown = true;
		dragged = false;
		startPos = page(e);
		startScroll = node[prop];
		samples = [{ t: performance.now(), p: startPos }];
		node.style.cursor = 'grabbing';
	}

	function mousemove(e) {
		if (!isDown) return;
		const p = page(e);
		const walk = p - startPos;
		// Threshold before treating it as a drag, so tile clicks still land.
		if (Math.abs(walk) > 5) dragged = true;
		if (!dragged) return;
		e.preventDefault(); // no text/image selection mid-drag
		node[prop] = startScroll - walk;
		const now = performance.now();
		samples.push({ t: now, p });
		while (samples.length > 2 && now - samples[0].t > SAMPLE_WINDOW) samples.shift();
	}

	function mouseup() {
		if (!isDown) return;
		isDown = false;
		node.style.cursor = '';
		if (dragged && !reducedMotion?.matches) startGlide();
		// Delayed so the click event can fire first and be intercepted below.
		setTimeout(() => (dragged = false), 0);
	}

	function startGlide() {
		const first = samples[0];
		const last = samples[samples.length - 1];
		// Dragging, stopping, then letting go is a place, not a throw — stale
		// samples from before the pause must not fling the list.
		if (performance.now() - last.t > SAMPLE_WINDOW) return;
		const dt = last.t - first.t;
		if (dt <= 0) return;
		let velocity = (last.p - first.p) / dt; // px/ms, in pointer direction
		if (Math.abs(velocity) < MIN_FLICK) return;
		let prev = performance.now();
		function step(now) {
			glideFrame = 0;
			const elapsed = Math.max(1, now - prev);
			prev = now;
			const before = node[prop];
			node[prop] = before - velocity * elapsed;
			velocity *= Math.exp(-elapsed / GLIDE_TAU);
			// An unchanged value means the write was clamped at an edge — stop there.
			if (node[prop] === before || Math.abs(velocity) < STOP_AT) return;
			glideFrame = requestAnimationFrame(step);
		}
		glideFrame = requestAnimationFrame(step);
	}

	// Capture-phase, so a drag release never fires the tile's own click handler.
	function click(e) {
		if (dragged) {
			e.preventDefault();
			e.stopPropagation();
		}
	}

	function dragstart(e) {
		e.preventDefault();
	}

	// Horizontal docks scroll left-to-right from a plain (vertical) wheel.
	function wheel(e) {
		const delta =
			(Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX) *
			(e.deltaMode === 1 ? 16 : 1); // line-mode wheels (Firefox) → px
		if (!delta) return;
		e.preventDefault();
		stopGlide();
		node.scrollLeft += delta;
	}

	node.addEventListener('mousedown', mousedown);
	window.addEventListener('mousemove', mousemove, { passive: false });
	window.addEventListener('mouseup', mouseup);
	node.addEventListener('click', click, { capture: true });
	node.addEventListener('dragstart', dragstart);
	if (axis === 'x') node.addEventListener('wheel', wheel, { passive: false });

	return {
		destroy() {
			stopGlide();
			node.removeEventListener('mousedown', mousedown);
			window.removeEventListener('mousemove', mousemove);
			window.removeEventListener('mouseup', mouseup);
			node.removeEventListener('click', click, { capture: true });
			node.removeEventListener('dragstart', dragstart);
			if (axis === 'x') node.removeEventListener('wheel', wheel);
		}
	};
}
