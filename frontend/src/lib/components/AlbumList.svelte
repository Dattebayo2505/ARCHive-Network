<script>
	let { albums, nonAlbumCount, maxPerAlbum, activeId, onSelect, onBuild, building } = $props();
</script>

<nav class="w-56 shrink-0 space-y-1">
	{#each albums as a}
		<button
			type="button"
			class="block w-full p-1 text-left"
			class:font-bold={a.fb_album_id === activeId}
			class:text-error-500={a.count_selected >= maxPerAlbum}
			onclick={() => onSelect(a.fb_album_id)}
		>
			{a.name} ({a.count_selected}/{maxPerAlbum})
		</button>
	{/each}
	<hr class="hr" />
	<span class="text-sm opacity-70">Non-album ({nonAlbumCount} kept)</span>
	<hr class="hr" />
	<button class="btn preset-filled w-full" type="button" onclick={onBuild} disabled={building}>
		{building ? 'Building…' : 'Build ready folder ▸'}
	</button>
</nav>
