<script>
	let { photo, src = '', selectable = true, selectionEnabled = false, full = false, video = false, onToggle } = $props();

	// A tile the user can't act on right now: the album is full and this one
	// isn't already selected. Selected tiles stay clickable so they can be removed.
	let blocked = $derived(full && !photo.selected);
	let interactive = $derived(selectable && photo.exists && !blocked);
	let imgError = $state(false);

	// Tiles use a uniform 3:2 aspect ratio: the grid layout reads best with even
	// heights, and object-cover absorbs any off-ratio outliers. (This replaced an
	// earlier per-image masonry that measured naturalWidth/Height.)
</script>

<button
	type="button"
	style="aspect-ratio: 3 / 2;"
	class="group relative block w-full overflow-hidden rounded-lg bg-surface-200 ring-1 ring-inset ring-surface-300 transition-[box-shadow,transform] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
	class:ring-2={photo.selected}
	class:!ring-primary-600={photo.selected}
	aria-disabled={!interactive ? 'true' : undefined}
	onclick={() => interactive && selectionEnabled && onToggle?.(photo)}
	data-testid={`tile-${photo.fbid}`}
	aria-pressed={photo.exists ? photo.selected : undefined}
	aria-label={photo.caption || photo.fbid}
	title={photo.caption || photo.fbid}
>
	{#if photo.exists}
		{#if !imgError}
			<img
				class="size-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
				loading="lazy"
				onerror={() => (imgError = true)}
				{src}
				alt={photo.caption || photo.fbid}
			/>
		{:else}
			<span class="grid size-full place-items-center bg-surface-200 text-surface-400">
				<svg viewBox="0 0 24 24" class="size-8" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
			</span>
		{/if}

		{#if photo.archive_tag || (video && photo.video_thumb_tag)}
			{@const tag = photo.archive_tag || photo.video_thumb_tag}
			{@const isApplied = tag === 'APPLIED'}
			{@const isAuto = tag === 'AUTO'}
			<span
				class="pointer-events-none absolute left-2 top-2 rounded px-1.5 py-0.5 text-[0.6rem] font-semibold uppercase tracking-wide {isApplied ? 'bg-primary-900/75 text-primary-50' : isAuto ? 'bg-warning-900/75 text-warning-50' : 'bg-black/65 text-white'}"
			>
				{tag}
			</span>
		{/if}

		{#if photo.selected}
			<span class="pointer-events-none absolute inset-0 bg-primary-700/15"></span>
			<span
				class="pointer-events-none absolute right-2 top-2 grid size-6 place-items-center rounded-full bg-primary-700 text-primary-50 shadow"
				aria-hidden="true"
			>
				<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="3"
					stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
			</span>
		{:else if interactive && selectionEnabled}
			<!-- Affordance: empty ring always present when selection enabled -->
			<span
				class="pointer-events-none absolute right-2 top-2 size-6 rounded-full border-2 border-white/90 shadow-sm"
				aria-hidden="true"
			></span>
		{:else if blocked && selectionEnabled}
			<span
				class="pointer-events-none absolute right-2 top-2 grid size-6 place-items-center rounded-full bg-surface-900/70 text-surface-50"
				aria-hidden="true"
			>
				<svg viewBox="0 0 24 24" class="size-3.5" fill="none" stroke="currentColor" stroke-width="2.5"
					stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
			</span>
		{/if}

		{#if video}
			<span
				data-testid={`video-badge-${photo.fbid}`}
				class="pointer-events-none absolute inset-0 grid place-items-center"
				aria-hidden="true"
			>
				<span class="grid size-11 place-items-center rounded-full bg-black/55 text-white shadow-lg transition-transform group-hover:scale-110">
					<svg viewBox="0 0 24 24" class="size-6" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
				</span>
			</span>
		{/if}

		<!-- Caption overlay -->
		{#if photo.caption}
			<span
				class="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-2 pb-1.5 pt-6"
			>
				<span class="line-clamp-2 text-left text-[0.7rem] leading-snug text-white">{photo.caption}</span>
			</span>
		{/if}
	{:else}
		<span class="grid size-full place-items-center gap-1 p-2 text-center">
			<svg viewBox="0 0 24 24" class="mx-auto size-6 text-surface-400" fill="none" stroke="currentColor"
				stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15l-5-5L5 21" /><path d="M3 3l18 18M3 7v12a2 2 0 0 0 2 2h12" /><circle cx="9" cy="9" r="1.5" /></svg>
			<span class="text-[0.7rem] text-surface-600">missing file</span>
		</span>
	{/if}
</button>
