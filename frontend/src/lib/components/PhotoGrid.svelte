<script>
	import PhotoTile from './PhotoTile.svelte';
	import { sizeMin } from '$lib/viewSizes.js';

	let { album, thumb, size = 'm', selectable = true, selectionEnabled = false, video = false, full = false, onToggle, onContextMenu, onDblClick } = $props();

	let isFull = $derived(album?.max_per_album != null ? album.count_selected >= album.max_per_album : full);
	let min = $derived(sizeMin(size));
</script>

<!-- Standard CSS Grid: Left-to-right flow. Images will fit into grid cells 
     and object-cover will handle any aspect ratio outliers, catering to the 3:2 majority. -->
<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax({min}, 1fr)); gap: 0.75rem;">
	{#each album.photos as photo (photo.fbid)}
		<!-- contextmenu lives on the wrapper, not the tile button, so right-click
		     still works on blocked (disabled) and missing tiles. -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="break-inside-avoid"
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
