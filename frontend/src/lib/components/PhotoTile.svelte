<script>
	let { photo, src = '', selectable = true, onToggle } = $props();
</script>

<button
	type="button"
	class="tile border-2 p-0.5 text-left"
	class:border-primary-500={photo.selected}
	class:border-transparent={!photo.selected}
	disabled={!selectable || !photo.exists}
	onclick={() => onToggle?.(photo)}
	data-testid={`tile-${photo.fbid}`}
>
	{#if photo.exists}
		<img class="block h-32 w-32 object-cover" loading="lazy" {src} alt={photo.fbid} />
	{:else}
		<div class="grid h-32 w-32 place-items-center text-xs opacity-60">missing file</div>
	{/if}
	<div class="break-all text-[0.7rem]">{photo.fbid}</div>
	{#if photo.caption}<div class="break-all text-[0.7rem] opacity-70">{photo.caption}</div>{/if}
</button>
