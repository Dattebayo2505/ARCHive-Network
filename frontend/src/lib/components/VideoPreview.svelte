<script>
	import { onMount, onDestroy } from 'svelte';
	import { videoUrl, videoThumbUrl, saveVideoThumbnail } from '$lib/api.js';
	import { captureFrame } from '$lib/videoThumbs.js';

	let { video, version = 0, onClose, onThumbnailChosen, onToggle } = $props();

	let videoEl = $state();
	let videoH = $state(0);
	let videoW = $state(0);
	let closeBtn = $state();
	let saving = $state(false);
	let ready = $state(false); // a frame is decoded → capture is possible
	// Bust the <img> cache after we save a new still so the panel updates.
	let stillVersion = $state(version);
	let stillSrc = $derived(`${videoThumbUrl(video.fbid)}?v=${stillVersion}`);
	let hasStill = $state(true); // assume a default exists; onerror flips it off

	async function choose() {
		// Need a decoded frame; videoWidth stays 0 until one is ready.
		if (!videoEl || saving || !ready || !videoEl.videoWidth) return;
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

	function onKey(e) {
		if (e.key === 'Escape') {
			e.preventDefault();
			onClose();
		}
	}

	let opener;
	onMount(() => {
		opener = document.activeElement;
		document.body.style.overflow = 'hidden';
		closeBtn?.focus();
		// Set crossOrigin BEFORE src so the media loads in CORS mode — otherwise the
		// frame taints the canvas and toBlob yields null (Chrome reports taint via a
		// null callback, not a throw). Mirrors the working seed path in videoThumbs.js.
		if (videoEl) {
			videoEl.crossOrigin = 'anonymous';
			videoEl.src = videoUrl(video.fbid);
		}
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
	class="fixed inset-0 z-[60] flex flex-col bg-surface-950/80 backdrop-blur-sm"
	role="dialog"
	aria-modal="true"
	aria-label="Video thumbnail picker"
	tabindex="-1"
	onkeydown={onKey}
>
	<div class="flex items-center gap-3 px-4 py-3 text-surface-50 sm:px-6">
		<div class="min-w-0">
			<p class="truncate text-sm font-medium" title={video.caption || video.fbid}>
				{video.caption || video.fbid}
			</p>
			<p class="text-xs text-surface-300">
				Play, then choose the frame to keep {#if video?.creation_at} &middot; {formatFBDate(video.creation_at)}{/if}
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
		class="relative flex min-h-0 flex-1 items-center justify-center gap-6 px-4 sm:px-12"
		onclick={(e) => e.target === e.currentTarget && onClose()}
	>
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

	<p class="px-4 pb-3 pt-1 text-center text-xs text-surface-400">
		<kbd class="font-sans">Esc</kbd> to close
	</p>
</div>
