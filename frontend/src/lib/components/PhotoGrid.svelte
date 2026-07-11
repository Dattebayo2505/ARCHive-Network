<script>
	import PhotoTile from './PhotoTile.svelte';
	import { sizeCols } from '$lib/viewSizes.js';
	import { holdPeek } from '$lib/holdPeek.js';
	import { fade, scale } from 'svelte/transition';
	import { quartOut } from 'svelte/easing';

	let { album, thumb, preview, size = 'm', selectable = true, selectionEnabled = false, video = false, full = false, onToggle, onContextMenu, onDblClick } = $props();

	let isFull = $derived(album?.max_per_album != null ? album.count_selected >= album.max_per_album : full);
	let cols = $derived(Math.round(sizeCols(size)));

	// Hold-to-peek: a transient blown-up look at a photo while the mouse is held.
	// Purely visual — never mutates selection — so it's enabled on blocked and
	// read-only (archive) tiles too. Videos have their own preview flow.
	let peek = $state(null); // { photo, src }

	function startPeek(photo) {
		peek = { photo, src: thumb(photo.fbid) };
		// The scaled-up thumb shows instantly; swap in the full-res image once it
		// lands, unless the peek was released (or moved on) in the meantime.
		// (Compare by fbid: `peek.photo` is a deep-reactive proxy, never `===` the raw photo.)
		if (preview) {
			const fullSrc = preview(photo.fbid);
			const img = new Image();
			img.onload = () => {
				if (peek?.photo.fbid === photo.fbid) peek.src = fullSrc;
			};
			img.src = fullSrc;
		}
	}

	// Resolved once: a throw inside transition options aborts the outro and
	// strands the overlay in the DOM, so keep that path trivially safe.
	const noMotion =
		typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

	// Hidden tabs freeze the WAAPI timeline, so a timed outro would never finish
	// and the overlay would stick until the tab is visible again — jump instead
	// (same rule PhotoPreview applies to its filmstrip scroll).
	function peekDuration(base) {
		return noMotion || document.hidden ? 0 : base;
	}
</script>

<svelte:window onkeydown={(e) => peek && e.key === 'Escape' && (peek = null)} />

<!-- Standard CSS Grid: Left-to-right flow. Images will fit into grid cells
     and object-cover will handle any aspect ratio outliers, catering to the 3:2 majority. -->
<div style="display: grid; grid-template-columns: repeat({cols}, 1fr); gap: 0.75rem;">
	{#each album.photos as photo (photo.fbid)}
		<!-- contextmenu lives on the wrapper, not the tile button, so right-click
		     still works on blocked (disabled) and missing tiles. -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="break-inside-avoid"
			use:holdPeek={{
				enabled: !video && photo.exists,
				onStart: () => startPeek(photo),
				onEnd: () => (peek = null)
			}}
			oncontextmenu={(e) => {
				e.preventDefault();
				onContextMenu?.(photo, e);
			}}
			ondblclick={(e) => {
				e.preventDefault();
				onDblClick?.(photo, e);
			}}
		>
			<PhotoTile {photo} src={photo.exists ? thumb(photo.fbid) : ''} {selectable} {selectionEnabled} full={isFull} {video} {onToggle} />
		</div>
	{/each}
</div>

<!-- Peek overlay: shown only while the hold is active, gone on release. It is
     pointer-events-none so the release lands on the tile underneath, and the
     scrim is pinned bg-black/* (always-dark over photos, per the design system). -->
{#if peek}
	<div
		class="pointer-events-none fixed inset-0 z-50 grid place-items-center bg-black/40 p-6 backdrop-blur-sm"
		transition:fade={{ duration: peekDuration(140) }}
		aria-hidden="true"
		data-testid="peek-overlay"
	>
		<img
			class="max-h-[67vh] max-w-[67vw] rounded-lg object-contain shadow-2xl"
			in:scale={{ duration: peekDuration(180), start: 0.92, opacity: 0.4, easing: quartOut }}
			src={peek.src}
			alt={peek.photo.caption || peek.photo.fbid}
		/>
	</div>
{/if}
