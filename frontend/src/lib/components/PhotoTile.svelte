<script>
	let { photo, src = '', selectable = true, full = false, onToggle } = $props();

	// A tile the user can't act on right now: the album is full and this one
	// isn't already selected. Selected tiles stay clickable so they can be removed.
	let blocked = $derived(full && !photo.selected);
	let interactive = $derived(selectable && photo.exists && !blocked);

	// Shape the tile to the photo's real proportions. The cached thumbnail is already
	// scaled to the original aspect ratio (PIL fits the longest side), so the loaded
	// image's natural size *is* the original ratio. Square until it loads so the masonry
	// column reserves space instead of snapping from zero height.
	let ratio = $state('1 / 1');
	function measure(e) {
		const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
		if (w && h) ratio = `${w} / ${h}`;
	}
</script>

<button
	type="button"
	style="aspect-ratio: {ratio};"
	class="group relative block w-full overflow-hidden rounded-lg bg-surface-200 ring-1 ring-inset ring-surface-300 transition-[box-shadow,transform] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
	class:ring-2={photo.selected}
	class:!ring-primary-600={photo.selected}
	class:cursor-not-allowed={!interactive}
	class:opacity-55={blocked}
	disabled={!interactive}
	onclick={() => interactive && onToggle?.(photo)}
	data-testid={`tile-${photo.fbid}`}
	aria-pressed={photo.exists ? photo.selected : undefined}
	aria-label={photo.caption || photo.fbid}
	title={photo.caption || photo.fbid}
>
	{#if photo.exists}
		<img
			class="size-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
			loading="lazy"
			onload={measure}
			{src}
			alt={photo.caption || photo.fbid}
		/>

		{#if photo.archive_tag}
			<span
				class="pointer-events-none absolute left-2 top-2 rounded bg-surface-900/75 px-1.5 py-0.5 text-[0.6rem] font-semibold uppercase tracking-wide text-surface-50"
			>
				{photo.archive_tag}
			</span>
		{/if}

		<!-- Selected: green wash + check badge (non-color cue = the check icon) -->
		{#if photo.selected}
			<span class="pointer-events-none absolute inset-0 bg-primary-700/15"></span>
			<span
				class="pointer-events-none absolute right-2 top-2 grid size-6 place-items-center rounded-full bg-primary-700 text-primary-50 shadow"
				aria-hidden="true"
			>
				<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="3"
					stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
			</span>
		{:else if interactive}
			<!-- Affordance: empty ring appears on hover/focus -->
			<span
				class="pointer-events-none absolute right-2 top-2 size-6 rounded-full border-2 border-surface-50/90 opacity-0 shadow-sm transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
				aria-hidden="true"
			></span>
		{:else if blocked}
			<span
				class="pointer-events-none absolute right-2 top-2 grid size-6 place-items-center rounded-full bg-surface-900/70 text-surface-50"
				aria-hidden="true"
			>
				<svg viewBox="0 0 24 24" class="size-3.5" fill="none" stroke="currentColor" stroke-width="2.5"
					stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
			</span>
		{/if}

		<!-- Caption overlay -->
		{#if photo.caption}
			<span
				class="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-surface-950/80 to-transparent px-2 pb-1.5 pt-6"
			>
				<span class="line-clamp-2 text-left text-[0.7rem] leading-snug text-surface-50">{photo.caption}</span>
			</span>
		{/if}
	{:else}
		<span class="grid size-full place-items-center gap-1 p-2 text-center">
			<svg viewBox="0 0 24 24" class="mx-auto size-6 text-surface-400" fill="none" stroke="currentColor"
				stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15l-5-5L5 21" /><path d="M3 3l18 18M3 7v12a2 2 0 0 0 2 2h12" /><circle cx="9" cy="9" r="1.5" /></svg>
			<span class="text-[0.7rem] text-surface-500">missing file</span>
		</span>
	{/if}
</button>
