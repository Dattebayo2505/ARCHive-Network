<script>
	import { thumbUrl } from '$lib/api.js';
	import { kineticScroll } from '$lib/kineticScroll.js';

	let { album = null, onToggle, onDblClick, onDockDragStart, open = $bindable(false) } = $props();

	// Resize range per DESIGN.md § Selection Panel. `panelWidth` is never written
	// below MIN_WIDTH, so dragging the panel shut can't shrink the panel you get
	// back when you reopen it.
	const MIN_WIDTH = 200;
	const MAX_WIDTH = 600;
	const CLOSE_AT = 100; // release narrower than this and the panel closes
	const HOLD_MS = 400; // press-and-hold on the tab detaches the dock
	const DBLCLICK_MS = 200; // wait this long before a click counts as "remove"

	let panelWidth = $state(280);
	let dragWidth = $state(null);
	let dragging = $state(false);
	let wasDragged = $state(false);

	let effectiveWidth = $derived(dragging && dragWidth !== null ? dragWidth : open ? panelWidth : 0);

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
		const startX = e.clientX;
		const startY = e.clientY;
		const startWidth = effectiveWidth;

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

		// Coalesce pointermove into a single layout write per frame — otherwise every
		// move event reflows a container full of <img> elements.
		function apply() {
			frame = 0;
			if (pending === null) return;
			const deltaX = pending.x - startX;
			const deltaY = pending.y - startY;
			pending = null;
			if (Math.abs(deltaX) > 5 || Math.abs(deltaY) > 5) {
				wasDragged = true;
				clearTimeout(holdTimeout);
			}
			const next = Math.min(MAX_WIDTH, startWidth - deltaX);
			dragWidth = Math.max(0, next);
			if (next >= MIN_WIDTH) panelWidth = next;
		}

		function onMove(ev) {
			pending = { x: ev.clientX, y: ev.clientY };
			if (!frame) frame = requestAnimationFrame(apply);
		}

		function onUp() {
			apply();
			dragging = false;
			if (wasDragged) open = dragWidth >= CLOSE_AT;
			dragWidth = null;
			cleanup();
			setTimeout(() => (wasDragged = false), 0);
		}

		function onCancel() {
			dragging = false;
			dragWidth = null;
			cleanup();
			setTimeout(() => (wasDragged = false), 0);
		}

		window.addEventListener('pointermove', onMove);
		window.addEventListener('pointerup', onUp);
		window.addEventListener('pointercancel', onCancel);
	}

	// The tab is the only resize affordance, so it has to be resizable from the
	// keyboard too. Left widens because the panel is anchored to the right edge.
	function onTabKey(e) {
		const step = e.shiftKey ? 48 : 16;
		let next = null;
		if (e.key === 'ArrowLeft') next = panelWidth + step;
		else if (e.key === 'ArrowRight') next = panelWidth - step;
		else if (e.key === 'Home') next = MIN_WIDTH;
		else if (e.key === 'End') next = MAX_WIDTH;
		if (next === null) return;
		e.preventDefault();
		open = true;
		panelWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, next));
	}

	// A click removes the photo, which unmounts the tile — so a dblclick would never
	// land. Hold the removal for one dblclick window to let "open the preview" win.
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
	let colWidth = $derived(Math.max(80, Math.floor((panelWidth - 24) / 2)));
	let ratios = $state({});
	function measure(fbid, e) {
		const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
		if (w && h) ratios[fbid] = `${w} / ${h}`;
	}
</script>

<aside class="selection-panel-wrapper" class:is-dragging={dragging} style="width: {effectiveWidth}px;">
	<div class="panel-absolute-container" style="width: {panelWidth}px;">
		<button
			type="button"
			class="peek-tab"
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
			<div class="peek-pill"></div>
			{#if !open && selected.length > 0}
				<span class="peek-badge">{selected.length}</span>
			{/if}
		</button>

		<div class="panel-inner">
			<div class="panel-header">
				<h2 class="panel-title">
					<svg viewBox="0 0 24 24" class="size-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
					Selected
					<span class="panel-count">{selected.length}</span>
				</h2>
				<button
					type="button"
					class="panel-close"
					onclick={() => (open = false)}
					aria-label="Close selection panel"
					title="Close panel"
				>
					<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
				</button>
			</div>

			<div class="panel-body" use:kineticScroll>
				{#if selected.length === 0}
					<div class="panel-empty">
						<svg viewBox="0 0 24 24" class="size-8 text-surface-400" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="m21 15-5-5L5 21" /></svg>
						<p class="mt-2 text-sm text-surface-600">No photos selected yet</p>
						<p class="mt-0.5 text-xs text-surface-600">Click photos in the grid to select them</p>
					</div>
				{:else}
					<div class="thumb-grid" style="columns: {colWidth}px; column-gap: 0.375rem;">
						{#each selected as photo (photo.fbid)}
							<button
								type="button"
								class="thumb-item"
								class:thumb-missing={!photo.exists}
								style="aspect-ratio: {ratios[photo.fbid] || '1 / 1'};"
								title={photo.caption || photo.fbid}
								aria-label="Remove {photo.caption || photo.fbid} from selection"
								onclick={() => onThumbClick(photo)}
								ondblclick={(e) => onThumbDblClick(photo, e)}
							>
								{#if photo.exists}
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
								{:else}
									<svg viewBox="0 0 24 24" class="size-4 text-surface-400" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15l-5-5L5 21" /><path d="M3 3l18 18M3 7v12a2 2 0 0 0 2 2h12" /><circle cx="9" cy="9" r="1.5" /></svg>
								{/if}
							</button>
						{/each}
					</div>
				{/if}
			</div>
		</div>
	</div>
</aside>

<style>
	/* Every colour here is a surface/primary token, so dark mode arrives for free
	   via the inverted ramp in app.css. Do not add `.dark` overrides: under `.dark`
	   surface-800 is light ink, not a dark background. */
	.selection-panel-wrapper {
		position: relative;
		height: 100%;
		flex-shrink: 0;
		transition: width 0.25s cubic-bezier(0.32, 0.72, 0, 1);
	}

	.selection-panel-wrapper.is-dragging {
		transition: none;
	}

	.panel-absolute-container {
		position: absolute;
		left: -5px;
		top: 0;
		bottom: 0;
		display: flex;
		z-index: var(--z-dock-panel);
		/* Own stacking context so the tab can paint behind the panel without a
		   negative z-index escaping into the page. */
		isolation: isolate;
	}

	.peek-tab {
		position: absolute;
		left: 0;
		top: 50%;
		transform: translate(-20px, -50%);
		width: 32px;
		height: 120px;
		background: var(--color-surface-50);
		border: 1px solid var(--color-surface-300);
		border-right: none;
		border-radius: 16px 0 0 16px;
		display: flex;
		align-items: center;
		justify-content: flex-start;
		padding-left: 6px;
		cursor: grab;
		touch-action: none;
		box-shadow: -2px 0 8px oklch(0.16 0.006 172 / 0.15);
		z-index: 0;
		transition: transform 0.2s cubic-bezier(0.32, 0.72, 0, 1), background-color 0.15s;
	}

	.peek-tab:hover {
		transform: translate(-25px, -50%);
	}

	.peek-tab:focus-visible {
		outline: 2px solid var(--color-primary-600);
		outline-offset: 2px;
		transform: translate(-22px, -50%);
	}

	.selection-panel-wrapper.is-dragging .peek-tab {
		transform: translate(-32px, -50%);
	}

	.peek-tab:active,
	.selection-panel-wrapper.is-dragging .peek-tab {
		cursor: grabbing;
	}

	.peek-pill {
		width: 4px;
		height: 48px;
		background: var(--color-primary-500);
		border-radius: 2px;
	}

	.peek-badge {
		position: absolute;
		top: -8px;
		left: -4px;
		background: var(--color-primary-600);
		color: var(--color-primary-contrast-light);
		font-size: 0.6rem;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
		padding: 2px 6px;
		border-radius: 999px;
		box-shadow: 0 2px 4px oklch(0.16 0.006 172 / 0.2);
	}

	.panel-inner {
		position: relative;
		z-index: 1;
		display: flex;
		flex-direction: column;
		width: 100%;
		height: 100%;
		border-left: 1px solid var(--color-surface-300);
		background: var(--color-surface-50);
		border-radius: 16px 0 0 16px;
		overflow: hidden;
		/* DESIGN.md § Elevation "Float", mirrored to cast leftward over the grid. */
		box-shadow: -12px 0 32px oklch(0.16 0.006 172 / 0.18);
	}

	.panel-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		padding: 0.75rem 0.75rem 0.5rem;
		border-bottom: 1px solid var(--color-surface-200);
		flex-shrink: 0;
	}

	.panel-title {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-surface-800);
		letter-spacing: -0.01em;
	}

	.panel-count {
		font-size: 0.6875rem;
		font-weight: 500;
		/* surface-600, not -500: -500 on the -200 pill is 3.47:1 — below AA. */
		color: var(--color-surface-600);
		background: var(--color-surface-200);
		padding: 0.125rem 0.4rem;
		border-radius: 9999px;
		font-variant-numeric: tabular-nums;
	}

	.panel-close {
		display: grid;
		place-items: center;
		padding: 0.25rem;
		border-radius: 0.375rem;
		color: var(--color-surface-600);
		transition: background-color 0.15s, color 0.15s;
		cursor: pointer;
		border: none;
		background: none;
	}

	.panel-close:hover {
		background: var(--color-surface-200);
		color: var(--color-surface-800);
	}

	.panel-close:focus-visible {
		outline: 2px solid var(--color-primary-600);
		outline-offset: 2px;
	}

	.panel-body {
		flex: 1;
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: 0.5rem 0.75rem 0.75rem;
		scrollbar-width: none;
	}

	.panel-body::-webkit-scrollbar {
		display: none;
	}

	.panel-empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		text-align: center;
		padding: 2rem 1rem;
	}

	.thumb-item {
		position: relative;
		display: block;
		width: 100%;
		margin-bottom: 0.375rem;
		break-inside: avoid;
		border-radius: 0.5rem;
		overflow: hidden;
		border: 2px solid var(--color-primary-600);
		background: var(--color-surface-200);
		cursor: pointer;
		padding: 0;
		transition: transform 0.15s;
	}

	.thumb-item:hover {
		transform: scale(1.03);
	}

	.thumb-item:focus-visible {
		outline: 2px solid var(--color-primary-600);
		outline-offset: 2px;
	}

	.thumb-missing {
		display: grid;
		place-items: center;
		border-color: var(--color-surface-300);
	}

	.thumb-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	/* An always-dark scrim over a photo: pinned, never follows the inverted ramp.
	   Carries the error hue so "remove" reads at the moment of intent, without
	   spending red on the tile at rest. */
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
</style>
