<script>
	import { onMount, onDestroy } from 'svelte';
	import CarouselScrollbar from './CarouselScrollbar.svelte';
	import { dragScroll } from '$lib/dragScroll.js';

	let {
		album,
		thumb,
		preview,
		startIndex = 0,
		full = false,
		selectable = true,
		onToggle,
		onClose
	} = $props();

	let photos = $derived(album.photos);
	let index = $state(0);
	$effect(() => {
		index = Math.min(Math.max(startIndex, 0), album.photos.length - 1);
		requestAnimationFrame(() => scrollCurrent(false));
	});
	let current = $derived(photos[index]);

	// Filmstrip thumbs keep each photo's real proportions: fixed height, width from
	// the loaded image's natural ratio. Square until measured. (Deep-reactive proxy,
	// so assigning a key re-renders that thumb.)
	let stripRatio = $state({});
	function measureStrip(e, fbid) {
		const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
		if (w && h) {
			stripRatio[fbid] = `${w} / ${h}`;
			requestAnimationFrame(() => scrollCurrent(false));
		}
	}

	// The active photo can be removed (always) but only added while the album has
	// room — mirrors the grid's per-tile rule so the cap behaves the same everywhere.
	let isFull = $derived(album.max_per_album != null ? album.count_selected >= album.max_per_album : full);
	let blocked = $derived(isFull && current && !current.selected);

	let container;
	let scrollContainer = $state();
	let closeBtn = $state();
	let opener;

	function reducedMotion() {
		return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
	}

	// Hand-rolled ease-out scroll: native `scrollTo({behavior:'smooth'})` silently
	// no-ops in some engines, so we drive scrollLeft per frame instead. Honors
	// reduced-motion by jumping straight to the target.
	let scrollRaf = 0;
	function animateScroll(sc, to) {
		cancelAnimationFrame(scrollRaf);
		// rAF is paused in hidden tabs; jump so the strip is correct on return.
		if (reducedMotion() || document.hidden) {
			sc.scrollLeft = to;
			return;
		}
		const from = sc.scrollLeft;
		const dist = to - from;
		if (Math.abs(dist) < 1) return;
		const start = performance.now();
		const duration = 260;
		const easeOutQuart = (t) => 1 - Math.pow(1 - t, 4);
		const step = (now) => {
			const t = Math.min(1, (now - start) / duration);
			sc.scrollLeft = from + dist * easeOutQuart(t);
			if (t < 1) scrollRaf = requestAnimationFrame(step);
		};
		scrollRaf = requestAnimationFrame(step);
	}

	// Align the current thumbnail to the left edge of the filmstrip. Called from
	// every navigation path (arrows, filmstrip clicks, open) rather than a reactive
	// effect so the strip always tracks the selection.
	function scrollCurrent(smooth = true) {
		const el = container?.querySelectorAll('[data-strip]')[index];
		const sc = el?.parentElement;
		if (!el || !sc) return;
		// Delta from live rects → works regardless of offsetParent (the dialog is fixed).
		const elBox = el.getBoundingClientRect();
		const scBox = sc.getBoundingClientRect();
		const pad = 8; // small inset so it doesn't flush against the edge
		const target = sc.scrollLeft + (elBox.left - scBox.left) - pad;
		const clamped = Math.max(0, Math.min(target, sc.scrollWidth - sc.clientWidth));
		if (smooth) animateScroll(sc, clamped);
		else sc.scrollLeft = clamped;
	}

	function go(to) {
		const n = photos.length;
		index = ((to % n) + n) % n; // wrap both ends
		scrollCurrent();
	}

	function selectAt(i) {
		index = i;
		scrollCurrent();
	}

	function onKey(e) {
		if (e.key === 'Escape') {
			e.preventDefault();
			onClose();
		} else if (e.key === 'ArrowRight') {
			e.preventDefault();
			go(index + 1);
		} else if (e.key === 'ArrowLeft') {
			e.preventDefault();
			go(index - 1);
		} else if (e.key === 'Home') {
			e.preventDefault();
			go(0);
		} else if (e.key === 'End') {
			e.preventDefault();
			go(photos.length - 1);
		} else if (e.key === 'Tab') {
			trapTab(e);
		}
	}

	// Keep focus inside the dialog while it's open.
	function trapTab(e) {
		const f = container?.querySelectorAll(
			'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
		);
		if (!f || !f.length) return;
		const first = f[0];
		const last = f[f.length - 1];
		if (e.shiftKey && document.activeElement === first) {
			e.preventDefault();
			last.focus();
		} else if (!e.shiftKey && document.activeElement === last) {
			e.preventDefault();
			first.focus();
		}
	}

	onMount(() => {
		opener = document.activeElement;
		document.body.style.overflow = 'hidden';
		closeBtn?.focus();
	});

	onDestroy(() => {
		document.body.style.overflow = '';
		opener?.focus?.();
	});
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div
	bind:this={container}
	class="surface-fixed fixed inset-0 z-[60] flex flex-col bg-surface-950/80 backdrop-blur-sm"
	role="dialog"
	aria-modal="true"
	aria-label="Photo preview"
	tabindex="-1"
	onkeydown={onKey}
>
	<!-- Top bar: which photo, keep state, keep/remove + close -->
	<div class="flex items-center gap-3 px-4 py-3 text-surface-50 sm:px-6">
		<div class="min-w-0">
			<p class="truncate text-sm font-medium" title={current?.caption || current?.fbid}>
				{current?.caption || current?.fbid}
			</p>
			<p class="text-xs text-surface-300 tabular-nums">
				{index + 1} of {photos.length} · {album.name}
			</p>
		</div>

		<div class="ml-auto flex items-center gap-2">
			{#if selectable && current?.exists}
				{#if current.selected}
					<button
						type="button"
						class="flex h-9 items-center gap-1.5 rounded-lg border border-surface-300 bg-surface-50 px-3 text-sm font-semibold text-surface-900 shadow-sm transition-colors hover:bg-surface-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-surface-50"
						disabled={!isFull}
						onclick={() => onToggle(current)}
					>
						<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
						Deselect
					</button>
				{/if}

				<button
					type="button"
					class="flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-semibold shadow-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300 disabled:cursor-not-allowed disabled:opacity-100"
					class:bg-primary-600={current.selected && !isFull}
					class:text-primary-50={current.selected || isFull}
					class:hover:bg-primary-500={current.selected && !isFull}
					class:bg-warning-600={isFull}
					class:bg-surface-50={!current.selected && !isFull}
					class:text-surface-900={!current.selected && !isFull}
					class:hover:bg-surface-200={!current.selected && !isFull}
					disabled={isFull}
					onclick={() => onToggle(current)}
				>
					{#if isFull}
						<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2.25"
							stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
						Album full
					{:else if current.selected}
						<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2.5"
							stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
						Kept
					{:else}
						<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2"
							stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
						Keep
					{/if}
				</button>
			{/if}

			<button
				bind:this={closeBtn}
				type="button"
				class="grid size-9 place-items-center rounded-lg text-surface-100 transition-colors hover:bg-surface-50/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300"
				onclick={onClose}
				aria-label="Close preview"
			>
				<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2"
					stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" /></svg>
			</button>
		</div>
	</div>

	<!-- Stage: big image, flanked by prev/next. Click the dim margin to close. -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="relative flex min-h-0 flex-1 items-center justify-center px-2 sm:px-16"
		onclick={(e) => e.target === e.currentTarget && onClose()}
	>
		<button
			type="button"
			class="absolute left-2 z-10 grid size-10 place-items-center rounded-full bg-surface-950/40 text-surface-50 transition-colors hover:bg-surface-950/70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300 sm:size-11"
			onclick={() => go(index - 1)}
			aria-label="Previous photo"
		>
			<svg viewBox="0 0 24 24" class="size-6" fill="none" stroke="currentColor" stroke-width="2"
				stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg>
		</button>

		{#if current?.exists}
			<img
				class="max-h-full max-w-full rounded-lg object-contain shadow-2xl"
				src={preview(current.fbid)}
				alt={current.caption || current.fbid}
			/>
		{:else}
			<div class="grid place-items-center gap-2 text-surface-400">
				<svg viewBox="0 0 24 24" class="size-12" fill="none" stroke="currentColor" stroke-width="1.5"
					stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15l-5-5L5 21" /><path d="M3 3l18 18M3 7v12a2 2 0 0 0 2 2h12" /><circle cx="9" cy="9" r="1.5" /></svg>
				<span class="text-sm">This file is missing from the export</span>
			</div>
		{/if}

		<button
			type="button"
			class="absolute right-2 z-10 grid size-10 place-items-center rounded-full bg-surface-950/40 text-surface-50 transition-colors hover:bg-surface-950/70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300 sm:size-11"
			onclick={() => go(index + 1)}
			aria-label="Next photo"
		>
			<svg viewBox="0 0 24 24" class="size-6" fill="none" stroke="currentColor" stroke-width="2"
				stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>
		</button>
	</div>

	<!-- Filmstrip carousel: fixed-height thumbs keep each photo's aspect ratio; the
	     current one is ringed in green and centred. -->
	<div class="px-4 pt-2 pb-3 sm:px-6">
		<div class="mx-auto max-w-5xl">
			<div use:dragScroll bind:this={scrollContainer} class="flex gap-2 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden select-none"
				class:overflow-x-auto={photos.length >= 8}
				class:overflow-hidden={photos.length < 8}
				class:justify-center={photos.length < 10}>
				{#each photos as photo, i (photo.fbid)}
					{@const isCurrent = i === index}
					<button
						data-strip
						type="button"
						tabindex="-1"
						style="aspect-ratio: {stripRatio[photo.fbid] ?? '1 / 1'};"
						class="relative h-16 shrink-0 overflow-hidden rounded-md bg-surface-800 ring-1 ring-inset transition-[box-shadow] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300 sm:h-20"
						class:ring-2={isCurrent}
						class:!ring-primary-400={isCurrent}
						class:ring-surface-50={!isCurrent}
						class:opacity-55={!isCurrent}
						onclick={() => selectAt(i)}
						aria-label={`Show ${photo.caption || photo.fbid}`}
						aria-current={isCurrent ? 'true' : undefined}
					>
						{#if photo.exists}
							<img class="size-full object-cover" loading="lazy" onload={(e) => measureStrip(e, photo.fbid)} src={thumb(photo.fbid)} alt="" />
							{#if photo.selected}
								<span
									class="absolute right-1 top-1 grid size-4 place-items-center rounded-full bg-primary-600 text-primary-50 shadow"
									aria-hidden="true"
								>
									<svg viewBox="0 0 24 24" class="size-2.5" fill="none" stroke="currentColor" stroke-width="3.5"
										stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
								</span>
							{/if}
						{:else}
							<span class="grid size-full place-items-center text-surface-500">
								<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="1.75"
									stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15l-5-5L5 21" /><path d="M3 3l18 18M3 7v12a2 2 0 0 0 2 2h12" /></svg>
							</span>
						{/if}
					</button>
				{/each}
			</div>

			<div class="mt-2">
				<CarouselScrollbar container={scrollContainer} />
			</div>

			<p class="mt-1.5 text-center text-xs text-surface-400">
				<kbd class="font-sans">←</kbd> <kbd class="font-sans">→</kbd> to browse · <kbd class="font-sans">Esc</kbd> to close
			</p>
		</div>
	</div>
</div>
