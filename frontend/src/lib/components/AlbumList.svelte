<script>
	let { albums, nonAlbumCount, maxPerAlbum, activeId, onSelect, onContextMenu } = $props();
</script>

<nav aria-label="Albums" class="flex flex-col gap-1">
	<p class="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-surface-500">
		Albums <span class="font-normal text-surface-400">· {albums.length}</span>
	</p>

	{#each albums as a (a.fb_album_id)}
		{@const full = a.count_selected >= maxPerAlbum}
		{@const active = a.fb_album_id === activeId}
		<button
			type="button"
			class="flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
			class:bg-primary-100={active}
			class:text-primary-900={active}
			class:font-semibold={active}
			class:text-surface-700={!active}
			class:hover:bg-surface-200={!active}
			onclick={() => onSelect(a.fb_album_id)}
			oncontextmenu={(e) => {
				e.preventDefault();
				onContextMenu?.(a, e);
			}}
			aria-current={active ? 'true' : undefined}
		>
			<span class="truncate">{a.name}</span>
			<span
				class="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums"
				class:bg-warning-200={full}
				class:text-warning-900={full}
				class:bg-primary-200={!full && a.count_selected > 0}
				class:text-primary-900={!full && a.count_selected > 0}
				class:bg-surface-200={a.count_selected === 0}
				class:text-surface-600={a.count_selected === 0}
				title={full ? 'Album is full' : `${a.count_selected} of ${maxPerAlbum} selected`}
			>
				{#if full}
					<svg viewBox="0 0 24 24" class="size-3" fill="none" stroke="currentColor" stroke-width="2.5"
						stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
				{/if}
				{a.count_selected}/{maxPerAlbum}
			</span>
		</button>
	{/each}

	<div class="my-1 h-px bg-surface-300"></div>

	<div
		class="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-surface-500"
		title="All non-album photos are kept automatically and can't be deselected."
	>
		<svg viewBox="0 0 24 24" class="size-4 shrink-0 text-surface-400" fill="none" stroke="currentColor"
			stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
		<span>Auto-kept</span>
		<span class="ml-auto shrink-0 tabular-nums text-surface-400">{nonAlbumCount}</span>
	</div>
</nav>
