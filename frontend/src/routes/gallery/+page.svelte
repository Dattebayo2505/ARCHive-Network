<script>
	import { Toaster, createToaster } from '@skeletonlabs/skeleton-svelte';
	import { build, thumbUrl, toggle } from '$lib/api.js';
	import AlbumList from '$lib/components/AlbumList.svelte';
	import PhotoGrid from '$lib/components/PhotoGrid.svelte';
	import BuildSummary from '$lib/components/BuildSummary.svelte';

	let { data } = $props();
	let inventory = $state(data.inventory);
	let activeId = $state(inventory.albums[0]?.fb_album_id ?? null);
	let buildResult = $state(null);
	let building = $state(false);
	const toaster = createToaster();

	let activeAlbum = $derived(inventory.albums.find((a) => a.fb_album_id === activeId) ?? null);

	async function onToggle(photo) {
		if (!activeAlbum) return;
		const result = await toggle(activeAlbum.fb_album_id, photo.fbid);
		if (!result.ok && result.cap) {
			toaster.error({
				title: 'Album is full',
				description: `Max ${inventory.max_per_album} reached.`
			});
			return;
		}
		photo.selected = result.selected;
		activeAlbum.count_selected = result.count;
	}

	async function runBuild() {
		building = true;
		buildResult = await build();
		building = false;
	}
</script>

<div class="flex gap-4">
	<AlbumList
		albums={inventory.albums}
		nonAlbumCount={inventory.non_album.length}
		maxPerAlbum={inventory.max_per_album}
		{activeId}
		onSelect={(id) => (activeId = id)}
		onBuild={runBuild}
		{building}
	/>

	{#if activeAlbum}
		<PhotoGrid album={activeAlbum} thumb={thumbUrl} {onToggle} />
	{/if}
</div>

{#if buildResult}
	<BuildSummary result={buildResult} onClose={() => (buildResult = null)} />
{/if}

<Toaster {toaster} />
