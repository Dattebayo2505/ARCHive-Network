<script>
	import { thumbUrl } from '$lib/api.js';

	let { album = null, onToggle, onDblClick, onDockDragStart, open = $bindable(false) } = $props();

	// `panelHeight` is never written below MIN_HEIGHT, so dragging the strip shut
	// can't leave you with a clipped 60px strip on the next open.
	const MIN_HEIGHT = 120;
	const MAX_HEIGHT = 300; // above this the strip starts swallowing the photo grid
	const CLOSE_AT = 60; // release shorter than this and the strip closes
	const HOLD_MS = 800; // press-and-hold on the tab detaches the dock
	const DBLCLICK_MS = 200;

	let panelHeight = $state(130);
	let dragHeight = $state(null);
	let dragging = $state(false);
	let wasDragged = $state(false);

	let effectiveHeight = $derived(
		dragging && dragHeight !== null ? dragHeight : open ? panelHeight : 0
	);

	let holdTimeout;
	let clickTimeout;

	$effect(() => () => {
		clearTimeout(holdTimeout);
		clearTimeout(clickTimeout);
	});

	function startDrag(e) {
		e.preventDefault();
		dragging = true;
		wasDragged = false;
		const startY = e.clientY;
		const startHeight = effectiveHeight;

		let frame = 0;
		let pending = null;

		function cleanup() {
			clearTimeout(holdTimeout);
			cancelAnimationFrame(frame);
			frame = 0;
			window.removeEventListener('pointermove', onMove);
			window.removeEventListener('pointerup', onUp);
			window.removeEventListener('pointercancel', onCancel);
		}

		holdTimeout = setTimeout(() => {
			dragging = false;
			cleanup();
			setTimeout(() => (wasDragged = false), 0);
			onDockDragStart?.(e);
		}, HOLD_MS);

		// One layout write per frame, not one per pointermove.
		function apply() {
			frame = 0;
			if (pending === null) return;
			const deltaY = pending - startY;
			pending = null;
			if (Math.abs(deltaY) > 5) {
				wasDragged = true;
				clearTimeout(holdTimeout);
			}
			const next = Math.min(MAX_HEIGHT, startHeight + deltaY);
			dragHeight = Math.max(0, next);
			if (next >= MIN_HEIGHT) panelHeight = next;
		}

		function onMove(ev) {
			pending = ev.clientY;
			if (!frame) frame = requestAnimationFrame(apply);
		}

		function onUp() {
			apply();
			dragging = false;
			if (wasDragged) open = dragHeight >= CLOSE_AT;
			dragHeight = null;
			cleanup();
			setTimeout(() => (wasDragged = false), 0);
		}

		function onCancel() {
			dragging = false;
			dragHeight = null;
			cleanup();
			setTimeout(() => (wasDragged = false), 0);
		}

		window.addEventListener('pointermove', onMove);
		window.addEventListener('pointerup', onUp);
		window.addEventListener('pointercancel', onCancel);
	}

	function onTabKey(e) {
		const step = e.shiftKey ? 48 : 16;
		let next = null;
		if (e.key === 'ArrowDown') next = panelHeight + step;
		else if (e.key === 'ArrowUp') next = panelHeight - step;
		else if (e.key === 'Home') next = MIN_HEIGHT;
		else if (e.key === 'End') next = MAX_HEIGHT;
		if (next === null) return;
		e.preventDefault();
		open = true;
		panelHeight = Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, next));
	}

	// Removing the photo unmounts the tile, so a raw click would eat the dblclick.
	function onThumbClick(photo) {
		clearTimeout(clickTimeout);
		clickTimeout = setTimeout(() => onToggle?.(photo), DBLCLICK_MS);
	}

	function onThumbDblClick(photo, e) {
		e.preventDefault();
		clearTimeout(clickTimeout);
		onDblClick?.(photo, e);
	}

	let selected = $derived(album ? album.photos.filter((p) => p.selected) : []);
	let thumbSize = $derived(Math.max(48, panelHeight - 64)); // less header and padding

	let ratios = $state({});
	function measure(fbid, e) {
		const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
		if (w && h) ratios[fbid] = `${w} / ${h}`;
	}
</script>

<div
	class="selection-strip-wrapper"
	class:is-dragging={dragging}
	class:is-closed={effectiveHeight === 0}
	style="height: {effectiveHeight}px;"
>
	<div class="strip-inner">
		<div class="strip-header">
			<div class="flex items-center gap-2">
				<svg viewBox="0 0 24 24" class="size-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
				<span class="strip-title">Selected</span>
				<span class="strip-count">{selected.length}</span>
			</div>
			<button
				type="button"
				class="strip-close"
				onclick={(e) => {
					e.stopPropagation();
					open = false;
				}}
				aria-label="Close selection panel"
			>
				<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
			</button>
		</div>

		<div class="strip-body">
			{#if selected.length === 0}
				<div class="strip-empty">
					<p class="text-sm text-surface-600">No photos selected</p>
				</div>
			{:else}
				<div class="thumb-grid">
					{#each selected as photo (photo.fbid)}
						<button
							type="button"
							class="thumb-item"
							style="height: {thumbSize}px; aspect-ratio: {ratios[photo.fbid] || '1 / 1'};"
							title={photo.caption || photo.fbid}
							aria-label="Remove {photo.caption || photo.fbid} from selection"
							onclick={() => onThumbClick(photo)}
							ondblclick={(e) => onThumbDblClick(photo, e)}
						>
							<img
								class="thumb-img"
								src={thumbUrl(photo.fbid)}
								alt={photo.caption || photo.fbid}
								loading="lazy"
								onload={(e) => measure(photo.fbid, e)}
							/>
							<span class="thumb-remove" aria-hidden="true">
								<svg viewBox="0 0 24 24" class="size-3" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
							</span>
						</button>
					{/each}
				</div>
			{/if}
		</div>
	</div>

	<button
		type="button"
		class="peek-tab-bottom"
		onpointerdown={startDrag}
		onkeydown={onTabKey}
		onclick={(e) => {
			if (wasDragged) e.preventDefault();
			else open = !open;
		}}
		aria-expanded={open}
		aria-label={open ? 'Hide selection panel' : 'Show selection panel'}
		title="Drag to resize · hold to move the panel"
	>
		<div class="peek-pill-horizontal"></div>
		{#if !open && selected.length > 0}
			<span class="peek-badge">{selected.length}</span>
		{/if}
	</button>
</div>

<style>
	/* Surface/primary tokens only — dark mode comes from the inverted ramp in
	   app.css. Never add a `.dark` override here: under `.dark`, surface-800 is
	   light ink, not a dark background. */
	.selection-strip-wrapper {
		position: relative;
		width: 100%;
		flex-shrink: 0;
		transition: height 0.25s cubic-bezier(0.32, 0.72, 0, 1);
		/* Clears the tab (24px at rest, 32px mid-drag) so it never covers the grid. */
		margin-bottom: 2rem;
	}

	.selection-strip-wrapper.is-dragging {
		transition: none;
	}

	.strip-inner {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		display: flex;
		flex-direction: column;
		border: 1px solid var(--color-surface-300);
		background: var(--color-surface-50);
		border-radius: 0 0 12px 12px;
		overflow: hidden;
		box-shadow: 0 12px 32px oklch(0.16 0.006 172 / 0.18);
		z-index: var(--z-dock-panel);
		transition: border-color 0.15s, box-shadow 0.15s;
	}

	.selection-strip-wrapper.is-closed .strip-inner {
		border-color: transparent;
		box-shadow: none;
	}

	.strip-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 0.75rem;
		border-bottom: 1px solid var(--color-surface-200);
		background: var(--color-surface-100);
		flex-shrink: 0;
	}

	.strip-title {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-surface-800);
	}

	.strip-count {
		font-size: 0.6875rem;
		font-weight: 500;
		/* surface-600, not -500: -500 on the -200 pill is 3.47:1 — below AA. */
		color: var(--color-surface-600);
		background: var(--color-surface-200);
		padding: 0.125rem 0.4rem;
		border-radius: 9999px;
		font-variant-numeric: tabular-nums;
	}

	.strip-close {
		padding: 0.25rem;
		border-radius: 0.375rem;
		color: var(--color-surface-600);
		transition: background-color 0.15s, color 0.15s;
	}

	.strip-close:hover {
		background: var(--color-surface-200);
		color: var(--color-surface-800);
	}

	.strip-close:focus-visible {
		outline: 2px solid var(--color-primary-600);
		outline-offset: 2px;
	}

	.strip-body {
		flex: 1;
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: 0.5rem;
		scrollbar-width: none;
	}

	.strip-body::-webkit-scrollbar {
		display: none;
	}

	.strip-empty {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
	}

	.thumb-grid {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.thumb-item {
		position: relative;
		flex-shrink: 0;
		border-radius: 0.375rem;
		overflow: hidden;
		border: 2px solid var(--color-primary-600);
		background: var(--color-surface-200);
		cursor: pointer;
		padding: 0;
		transition: transform 0.15s;
	}

	.thumb-item:hover {
		transform: scale(1.05);
	}

	.thumb-item:focus-visible {
		outline: 2px solid var(--color-primary-600);
		outline-offset: 2px;
	}

	.thumb-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	/* Always-dark scrim over a photo — pinned, never follows the inverted ramp. */
	.thumb-remove {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		background: oklch(0.28 0.1 28 / 0.62);
		color: oklch(0.99 0 0);
		opacity: 0;
		transition: opacity 0.15s;
		pointer-events: none;
	}

	.thumb-item:hover .thumb-remove,
	.thumb-item:focus-visible .thumb-remove {
		opacity: 1;
	}

	/* Peek tab for the horizontal dock; the handle hangs below the strip. 24px tall
	   at rest to clear the WCAG 2.2 target-size minimum. */
	.peek-tab-bottom {
		position: absolute;
		top: 100%;
		left: 50%;
		transform: translateX(-50%);
		height: 24px;
		width: 120px;
		background: var(--color-surface-50);
		border: 1px solid var(--color-surface-300);
		border-top: none;
		border-radius: 0 0 16px 16px;
		display: flex;
		align-items: flex-end;
		justify-content: center;
		padding-bottom: 6px;
		cursor: grab;
		touch-action: none;
		box-shadow: 0 6px 16px oklch(0.16 0.006 172 / 0.15);
		z-index: var(--z-dock-panel);
		transition: height 0.2s cubic-bezier(0.32, 0.72, 0, 1), background-color 0.15s;
	}

	.peek-tab-bottom:hover {
		height: 30px;
	}

	.peek-tab-bottom:focus-visible {
		outline: 2px solid var(--color-primary-600);
		outline-offset: 2px;
		height: 30px;
	}

	.selection-strip-wrapper.is-dragging .peek-tab-bottom {
		height: 32px;
	}

	.peek-tab-bottom:active,
	.selection-strip-wrapper.is-dragging .peek-tab-bottom {
		cursor: grabbing;
	}

	.peek-pill-horizontal {
		height: 4px;
		width: 48px;
		background: var(--color-primary-500);
		border-radius: 2px;
	}

	.peek-badge {
		position: absolute;
		bottom: -6px;
		left: -10px;
		background: var(--color-primary-600);
		color: var(--color-primary-contrast-light);
		font-size: 0.6rem;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
		padding: 2px 6px;
		border-radius: 999px;
		box-shadow: 0 2px 4px oklch(0.16 0.006 172 / 0.2);
	}
</style>
