<script>
	import PhotoTile from './PhotoTile.svelte';

	let { album, thumb, onToggle } = $props();
</script>

<section class="grid gap-2" style="grid-template-columns: repeat(auto-fill, 130px);">
	{#each album.photos as photo (photo.fbid)}
		<PhotoTile {photo} src={photo.exists ? thumb(photo.fbid) : ''} {onToggle} />
	{/each}
</section>
