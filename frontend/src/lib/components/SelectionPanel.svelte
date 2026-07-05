<script>
	import { thumbUrl } from '$lib/api.js';

	let { album = null, open = false, onClose, onToggle } = $props();

	// --- Resizing via drag handle ---
	let panelWidth = $state(280);
	let dragging = $state(false);

	function startResize(e) {
		e.preventDefault();
		dragging = true;
		const startX = e.clientX;
		const startW = panelWidth;

		function onMove(ev) {
			// Dragging left → larger panel (since panel is on the right)
			const delta = startX - ev.clientX;
			panelWidth = Math.max(200, Math.min(600, startW + delta));
		}
		function onUp() {
			dragging = false;
			window.removeEventListener('pointermove', onMove);
			window.removeEventListener('pointerup', onUp);
		}
		window.addEventListener('pointermove', onMove);
		window.addEventListener('pointerup', onUp);
	}

	// Selected photos in the current album only.
	let selected = $derived(album ? album.photos.filter((p) => p.selected) : []);

	// Column width for the masonry layout — dynamically derived from the panel
	// width so thumbnails resize as the user drags the handle.
	// Subtract padding (0.75rem × 2 ≈ 24px) then target ~2 columns at default.
	let colWidth = $derived(Math.max(80, Math.floor((panelWidth - 24) / 2)));

	// Track each photo's measured aspect ratio by fbid.
	let ratios = $state({});
	function measure(fbid, e) {
		const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
		if (w && h) ratios[fbid] = `${w} / ${h}`;
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<aside
		class="selection-panel"
		style="width: {panelWidth}px; min-width: {panelWidth}px;"
	>
		<!-- Drag handle (left edge) -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="resize-handle"
			class:resize-active={dragging}
			onpointerdown={startResize}
		></div>

		<div class="panel-inner">
			<!-- Header -->
			<div class="panel-header">
				<h2 class="panel-title">
					<svg viewBox="0 0 24 24" class="size-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
					Selected
					<span class="panel-count">{selected.length}</span>
				</h2>
				<button
					type="button"
					class="panel-close"
					onclick={onClose}
					aria-label="Close selection panel"
					title="Close panel"
				>
					<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
				</button>
			</div>

			<!-- Scrollable body (vertical) -->
			<div class="panel-body">
				{#if selected.length === 0}
					<div class="panel-empty">
						<svg viewBox="0 0 24 24" class="size-8 text-surface-300" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="m21 15-5-5L5 21" /></svg>
						<p class="mt-2 text-sm text-surface-500">No photos selected yet</p>
						<p class="mt-0.5 text-xs text-surface-400">Click photos in the grid to select them</p>
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
								onclick={() => onToggle?.(photo)}
							>
								{#if photo.exists}
									<img
										class="thumb-img"
										src={thumbUrl(photo.fbid)}
										alt={photo.caption || photo.fbid}
										loading="lazy"
										onload={(e) => measure(photo.fbid, e)}
									/>
									<!-- Remove badge on hover -->
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
	</aside>
{/if}

<style>
	.selection-panel {
		display: flex;
		position: relative;
		flex-shrink: 0;
		height: 100%;
	}

	.resize-handle {
		position: absolute;
		left: -4px;
		top: 0;
		bottom: 0;
		width: 8px;
		cursor: col-resize;
		z-index: 10;
		transition: background-color 0.15s;
		border-radius: 4px;
	}

	.resize-handle:hover,
	.resize-active {
		background-color: rgba(27, 94, 32, 0.18);
	}

	.panel-inner {
		display: flex;
		flex-direction: column;
		width: 100%;
		min-height: 0;
		border-left: 1px solid var(--color-surface-300, #d4d4d4);
		background: var(--color-surface-50, #fafafa);
		border-radius: 0.75rem;
		overflow: hidden;
	}

	.panel-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		padding: 0.75rem 0.75rem 0.5rem;
		border-bottom: 1px solid var(--color-surface-200, #e5e5e5);
		flex-shrink: 0;
	}

	.panel-title {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-surface-800, #262626);
		letter-spacing: -0.01em;
	}

	.panel-count {
		font-size: 0.6875rem;
		font-weight: 500;
		color: var(--color-surface-500, #737373);
		background: var(--color-surface-200, #e5e5e5);
		padding: 0.125rem 0.4rem;
		border-radius: 9999px;
		font-variant-numeric: tabular-nums;
	}

	.panel-close {
		display: grid;
		place-items: center;
		padding: 0.25rem;
		border-radius: 0.375rem;
		color: var(--color-surface-500, #737373);
		transition: all 0.15s;
		cursor: pointer;
		border: none;
		background: none;
	}

	.panel-close:hover {
		background: var(--color-surface-200, #e5e5e5);
		color: var(--color-surface-700, #404040);
	}

	.panel-body {
		flex: 1;
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: 0.5rem 0.75rem 0.75rem;
	}

	.panel-empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		text-align: center;
		padding: 2rem 1rem;
	}

	/* Masonry columns: tiles keep their true aspect ratio (measured on load)
	   and tile without gaps, just like the main PhotoGrid. Column width is set
	   inline from the computed `colWidth` so it responds to panel resizing. */
	.thumb-grid {
		/* columns + column-gap set via inline style */
	}

	.thumb-item {
		position: relative;
		display: block;
		width: 100%;
		margin-bottom: 0.375rem;
		break-inside: avoid;
		border-radius: 0.5rem;
		overflow: hidden;
		border: 2px solid var(--color-primary-600, #1b5e20);
		background: var(--color-surface-200, #e5e5e5);
		cursor: pointer;
		padding: 0;
		transition: border-color 0.15s, transform 0.15s;
	}

	.thumb-item:hover {
		border-color: var(--color-error-500, #ef4444);
		transform: scale(1.03);
	}

	.thumb-missing {
		display: grid;
		place-items: center;
		border-color: var(--color-surface-300, #d4d4d4);
	}

	.thumb-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	.thumb-remove {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		background: rgba(0, 0, 0, 0.55);
		color: white;
		opacity: 0;
		transition: opacity 0.15s;
		pointer-events: none;
	}

	.thumb-item:hover .thumb-remove {
		opacity: 1;
	}
</style>
