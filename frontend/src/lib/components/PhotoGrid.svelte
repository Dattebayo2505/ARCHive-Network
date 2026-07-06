<script>
	import PhotoTile from './PhotoTile.svelte';
	import { sizeMin } from '$lib/viewSizes.js';

	let { album, thumb, full = false, size = 'm', selectable = true, video = false, onToggle, onContextMenu } = $props();

	let min = $derived(sizeMin(size));
</script>

<!-- Masonry columns: tiles keep their true aspect ratio and still tile without
     gaps. The view-size control sets the column width, so density still works. -->
<div style="columns: {min}; column-gap: 0.75rem;">
	{#each album.photos as photo (photo.fbid)}
		<!-- contextmenu lives on the wrapper, not the tile button, so right-click
		     still works on blocked (disabled) and missing tiles. -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="mb-3 break-inside-avoid"
			oncontextmenu={(e) => {
				e.preventDefault();
				onContextMenu?.(photo, e);
			}}
		>
			<PhotoTile {photo} src={photo.exists ? thumb(photo.fbid) : ''} {full} {selectable} {video} {onToggle} />
		</div>
	{/each}
</div>
