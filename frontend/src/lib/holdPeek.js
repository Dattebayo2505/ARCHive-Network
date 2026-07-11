// Svelte action: press-and-hold "peek" gesture for photo tiles.
//
// Hold the primary button for `delay` ms without drifting past `slop` px and
// `onStart()` fires; releasing (pointerup/pointercancel, or destroy) fires
// `onEnd()`. The gesture is a *look*, not an action, so the click that the
// browser synthesizes on release is swallowed — a hold must never toggle the
// tile's selection. Quick clicks (released before the delay) pass through
// untouched, which keeps single-click-select and dblclick-preview working.

const DEFAULTS = { delay: 350, slop: 6, enabled: true };

export function holdPeek(node, params = {}) {
	let opts = { ...DEFAULTS, ...params };
	let timer = 0;
	let startX = 0;
	let startY = 0;
	let peeking = false;
	let disarmTimer = 0;

	function clearHoldTimer() {
		clearTimeout(timer);
		timer = 0;
	}

	function suppressClick(e) {
		e.preventDefault();
		e.stopPropagation();
	}

	// The click suppressor is `once`, but a peek can end without a click ever
	// firing (pointercancel, Escape-then-release off-window). Disarm it a tick
	// after the peek ends: the release click is dispatched before timers run,
	// so it is still swallowed, while later unrelated clicks are not.
	function disarmSuppressorSoon() {
		clearTimeout(disarmTimer);
		disarmTimer = setTimeout(() => {
			window.removeEventListener('click', suppressClick, { capture: true });
		}, 0);
	}

	function endPeek() {
		clearHoldTimer();
		window.removeEventListener('pointerup', onRelease);
		window.removeEventListener('pointercancel', onRelease);
		if (!peeking) return;
		peeking = false;
		disarmSuppressorSoon();
		opts.onEnd?.();
	}

	function onPointerDown(e) {
		if (!opts.enabled || e.button !== 0 || e.isPrimary === false) return;
		startX = e.clientX;
		startY = e.clientY;
		clearHoldTimer();
		// Release can land anywhere (the peek covers the tile), so listen globally.
		window.addEventListener('pointerup', onRelease);
		window.addEventListener('pointercancel', onRelease);
		timer = setTimeout(() => {
			timer = 0;
			peeking = true;
			clearTimeout(disarmTimer);
			window.addEventListener('click', suppressClick, { capture: true, once: true });
			opts.onStart?.();
		}, opts.delay);
	}

	function onPointerMove(e) {
		if (timer && (Math.abs(e.clientX - startX) > opts.slop || Math.abs(e.clientY - startY) > opts.slop)) {
			clearHoldTimer();
		}
	}

	function onRelease() {
		endPeek();
	}

	// A long-press on an <img> can start a native drag, which steals the
	// pointer stream mid-hold; block it while a peek is pending or showing.
	function onDragStart(e) {
		if (timer || peeking) e.preventDefault();
	}

	node.addEventListener('pointerdown', onPointerDown);
	node.addEventListener('pointermove', onPointerMove);
	node.addEventListener('dragstart', onDragStart);

	return {
		update(next = {}) {
			opts = { ...DEFAULTS, ...next };
		},
		destroy() {
			endPeek();
			clearTimeout(disarmTimer);
			window.removeEventListener('click', suppressClick, { capture: true });
			node.removeEventListener('pointerdown', onPointerDown);
			node.removeEventListener('pointermove', onPointerMove);
			node.removeEventListener('dragstart', onDragStart);
		}
	};
}
