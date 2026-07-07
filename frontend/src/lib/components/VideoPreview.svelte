<script>
	import { onMount, onDestroy } from 'svelte';
	import { videoUrl, videoThumbUrl, saveVideoThumbnail } from '$lib/api.js';
	import { captureFrame } from '$lib/videoThumbs.js';

	let { videos, startIndex = 0, thumbVersionMap = {}, onClose, onThumbnailChosen, onToggle } = $props();

	let index = $state(0);
	$effect(() => {
		index = Math.min(Math.max(startIndex, 0), videos.length - 1);
	});
	let video = $derived(videos[index]);

	let videoEl = $state();
	let videoH = $state(0);
	let videoW = $state(0);
	let closeBtn = $state();
	let saving = $state(false);
	let ready = $state(false); // a frame is decoded → capture is possible
	
	let stillVersion = $state(thumbVersionMap[video?.fbid] ?? 0);
	let stillSrc = $derived(`${videoThumbUrl(video?.fbid)}?v=${stillVersion}`);
	let hasStill = $state(true); // assume a default exists; onerror flips it off

	let container;
	let showCarousel = $state(true);
	
	onMount(() => {
		const saved = localStorage.getItem('streamlinify_video_carousel');
		if (saved !== null) {
			showCarousel = saved === 'true';
		}
	});

	function toggleCarousel() {
		showCarousel = !showCarousel;
		localStorage.setItem('streamlinify_video_carousel', showCarousel.toString());
		if (showCarousel) requestAnimationFrame(() => scrollCurrent(false));
	}

	let stripRatio = $state({});
	function measureStrip(e, fbid) {
		const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
		if (w && h) {
			stripRatio[fbid] = `${w} / ${h}`;
			requestAnimationFrame(() => scrollCurrent(false));
		}
	}

	function reducedMotion() {
		return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
	}

	let scrollRaf = 0;
	function animateScroll(sc, to) {
		cancelAnimationFrame(scrollRaf);
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

	function scrollCurrent(smooth = true) {
		if (!showCarousel) return;
		const el = container?.querySelectorAll('[data-strip]')[index];
		const sc = el?.parentElement;
		if (!el || !sc) return;
		const elBox = el.getBoundingClientRect();
		const scBox = sc.getBoundingClientRect();
		const pad = 8;
		const target = sc.scrollLeft + (elBox.left - scBox.left) - pad;
		const clamped = Math.max(0, Math.min(target, sc.scrollWidth - sc.clientWidth));
		if (smooth) animateScroll(sc, clamped);
		else sc.scrollLeft = clamped;
	}

	$effect(() => {
		index; // subscribe to index changes
		requestAnimationFrame(() => scrollCurrent(false));
	});

	$effect(() => {
		// When the video changes, update the still version from the map
		if (video) {
			stillVersion = thumbVersionMap[video.fbid] ?? 0;
			hasStill = true;
			ready = false;
		}
	});

	async function choose() {
		// Need a decoded frame; videoWidth stays 0 until one is ready.
		if (!videoEl || saving || !ready || !videoEl.videoWidth || !video) return;
		saving = true;
		try {
			const blob = await captureFrame(videoEl);
			const timestamp = videoEl.currentTime;
			const res = await saveVideoThumbnail(video.fbid, blob, false, timestamp);
			stillVersion += 1;
			hasStill = true;
			onThumbnailChosen?.(video.fbid, res.file_size_bytes, timestamp);
		} catch {
			/* frame not capturable yet — leave the current still in place */
		} finally {
			saving = false;
		}
	}

	function go(to) {
		const n = videos.length;
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
			go(videos.length - 1);
		}
	}

	let opener;
	$effect(() => {
		if (videoEl && video) {
			videoEl.crossOrigin = 'anonymous';
			videoEl.src = videoUrl(video.fbid);
		}
	});

	onMount(() => {
		opener = document.activeElement;
		document.body.style.overflow = 'hidden';
		closeBtn?.focus();
	});
	onDestroy(() => {
		document.body.style.overflow = '';
		opener?.focus?.();
	});

	function formatFBDate(isoString) {
		if (!isoString) return '';
		const date = new Date(isoString);
		return new Intl.DateTimeFormat('en-US', {
			timeZone: 'Asia/Manila',
			month: 'long',
			day: 'numeric',
			year: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
			hour12: true
		}).format(date).replace('\u202f', ' ');
	}

	function formatDuration(seconds) {
		if (seconds == null) return null;
		const m = Math.floor(seconds / 60);
		const s = Math.floor(seconds % 60).toString().padStart(2, '0');
		const ms = Math.floor((seconds % 1) * 1000).toString().padStart(3, '0');
		return m > 0 ? `${m}m ${s}s ${ms}ms` : `${s}s ${ms}ms`;
	}

	function seekTo(timestamp) {
		if (videoEl && timestamp != null) {
			videoEl.pause();
			videoEl.currentTime = timestamp;
		}
	}
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div
	bind:this={container}
	class="fixed inset-0 z-[60] flex flex-col bg-surface-950/80 backdrop-blur-sm"
	role="dialog"
	aria-modal="true"
	aria-label="Video thumbnail picker"
	tabindex="-1"
	onkeydown={onKey}
>
	<div class="flex items-center gap-3 px-4 py-3 text-surface-50 sm:px-6">
		<div class="min-w-0">
			<p class="truncate text-sm font-medium" title={video?.caption || video?.fbid}>
				{video?.caption || video?.fbid}
			</p>
			<p class="text-xs text-surface-300 tabular-nums">
				{index + 1} of {videos.length} · Play, then choose the frame to keep {#if video?.creation_at} &middot; {formatFBDate(video.creation_at)}{/if}
			</p>
		</div>
		<div class="ml-auto flex items-center gap-2">
			<button
				type="button"
				class="flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-semibold shadow-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300 shrink-0"
				class:bg-primary-600={video.selected}
				class:text-primary-50={video.selected}
				class:hover:bg-primary-500={video.selected}
				class:bg-surface-50={!video.selected}
				class:text-surface-900={!video.selected}
				class:hover:bg-surface-200={!video.selected}
				onclick={() => onToggle?.(video)}
			>
				{#if video.selected}
					<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2.5"
						stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
					Kept
				{:else}
					<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2"
						stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
					Keep
				{/if}
			</button>
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

	<!-- Stage: video left, chosen still right (vertically centred, 30% smaller). -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="relative flex min-h-0 flex-1 items-center justify-center px-2 sm:px-16"
		onclick={(e) => e.target === e.currentTarget && onClose()}
	>
		<button
			type="button"
			class="absolute left-2 z-10 grid size-10 place-items-center rounded-full bg-black/60 text-white backdrop-blur-sm transition-colors hover:bg-black/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300 sm:size-11"
			onclick={() => go(index - 1)}
			aria-label="Previous video"
		>
			<svg viewBox="0 0 24 24" class="size-6" fill="none" stroke="currentColor" stroke-width="2"
				stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg>
		</button>

		<!-- The stage interior wraps the video and thumb panel to group them -->
		<div class="flex h-full w-full min-h-0 min-w-0 items-center justify-center gap-6" style="max-height: 100%; max-width: 100%;">
			<!-- svelte-ignore a11y_media_has_caption -->
			<video
			bind:this={videoEl}
			bind:clientHeight={videoH}
			bind:clientWidth={videoW}
			class="max-h-full max-w-[55%] rounded-lg shadow-2xl"
			controls
			onloadeddata={() => (ready = true)}
		></video>

		<div class="flex items-center" style="height: {videoH}px;">
			{#if hasStill}
				<figure class="flex flex-col items-center gap-2">
					<img
						class="rounded-lg object-contain shadow-xl ring-1 ring-surface-50/20"
						style="max-height: {videoH * 0.7}px; max-width: {videoW * 0.7}px;"
						src={stillSrc}
						alt="Chosen thumbnail"
						onerror={() => (hasStill = false)}
					/>
					<figcaption class="text-sm text-surface-300">
						Chosen thumbnail {#if video.thumb_timestamp != null} at <button type="button" class="text-primary-400 font-medium hover:text-primary-300 hover:underline" onclick={() => seekTo(video.thumb_timestamp)}>{formatDuration(video.thumb_timestamp)}</button>{/if}
					</figcaption>
					<button
						type="button"
						class="mt-2 flex h-9 items-center gap-1.5 rounded-lg bg-primary-600 px-3 text-sm font-semibold text-primary-50 shadow-sm transition-colors hover:bg-primary-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300 disabled:opacity-70"
						onclick={choose}
						disabled={saving || !ready}
					>
						<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2"
							stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="9" cy="9" r="2" /><path d="m21 15-5-5L5 21" /></svg>
						{saving ? 'Saving…' : ready ? 'Choose Thumbnail' : 'Loading…'}
					</button>
				</figure>
			{:else}
				<div class="flex flex-col items-center gap-3">
					<p class="max-w-[10rem] text-center text-xs text-surface-400">
						No thumbnail yet — play to a frame and click “Choose Thumbnail”.
					</p>
					<button
						type="button"
						class="flex h-9 items-center gap-1.5 rounded-lg bg-primary-600 px-3 text-sm font-semibold text-primary-50 shadow-sm transition-colors hover:bg-primary-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300 disabled:opacity-70"
						onclick={choose}
						disabled={saving || !ready}
					>
						<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2"
							stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="9" cy="9" r="2" /><path d="m21 15-5-5L5 21" /></svg>
						{saving ? 'Saving…' : ready ? 'Choose Thumbnail' : 'Loading…'}
					</button>
				</div>
			{/if}
		</div>
		</div>

		<button
			type="button"
			class="absolute right-2 z-10 grid size-10 place-items-center rounded-full bg-black/60 text-white backdrop-blur-sm transition-colors hover:bg-black/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300 sm:size-11"
			onclick={() => go(index + 1)}
			aria-label="Next video"
		>
			<svg viewBox="0 0 24 24" class="size-6" fill="none" stroke="currentColor" stroke-width="2"
				stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>
		</button>
	</div>

	<!-- Filmstrip carousel -->
	<div class="px-4 pb-3 pt-1 sm:px-6">
		<div class="mb-1 flex justify-center">
			<button
				type="button"
				class="grid size-8 place-items-center rounded-full bg-black/20 text-white backdrop-blur-sm transition-colors hover:bg-black/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300"
				onclick={toggleCarousel}
				aria-label={showCarousel ? 'Hide carousel' : 'Show carousel'}
			>
				{#if showCarousel}
					<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
				{:else}
					<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m18 15-6-6-6 6"/></svg>
				{/if}
			</button>
		</div>

		<div class="mx-auto max-w-3xl">
			{#if showCarousel}
				<div class="flex gap-2 overflow-x-auto pb-2 pt-1 [scrollbar-width:thin]">
					{#each videos as v, i (v.fbid)}
						{@const isCurrent = i === index}
						{@const thumbSrc = `${videoThumbUrl(v.fbid)}?v=${thumbVersionMap[v.fbid] ?? 0}`}
						<button
							data-strip
							type="button"
							tabindex="-1"
							style="aspect-ratio: {stripRatio[v.fbid] ?? '1 / 1'};"
							class="relative h-16 shrink-0 overflow-hidden rounded-md bg-surface-800 ring-1 ring-inset transition-[box-shadow] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-300 sm:h-20"
							class:ring-2={isCurrent}
							class:!ring-primary-400={isCurrent}
							class:ring-surface-50={!isCurrent}
							class:opacity-55={!isCurrent}
							onclick={() => selectAt(i)}
							aria-label={`Show ${v.caption || v.fbid}`}
							aria-current={isCurrent ? 'true' : undefined}
						>
							<img class="size-full object-cover" loading="lazy" onload={(e) => measureStrip(e, v.fbid)} src={thumbSrc} alt="" />
							{#if v.selected}
								<span
									class="absolute right-1 top-1 grid size-4 place-items-center rounded-full bg-primary-600 text-primary-50 shadow"
									aria-hidden="true"
								>
									<svg viewBox="0 0 24 24" class="size-2.5" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
								</span>
							{/if}
						</button>
					{/each}
				</div>
			{/if}

			<p class="mt-1 text-center text-xs text-surface-400">
				<kbd class="font-sans">←</kbd> <kbd class="font-sans">→</kbd> to browse · <kbd class="font-sans">Esc</kbd> to close
			</p>
		</div>
	</div>
</div>
