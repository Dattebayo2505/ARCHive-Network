<script>
	import { Toaster, createToaster } from '@skeletonlabs/skeleton-svelte';
	import { build, reveal, thumbUrl, previewUrl, toggle } from '$lib/api.js';
	import { DEFAULT_SIZE, SIZE_STORAGE_KEY, VIEW_SIZES } from '$lib/viewSizes.js';
	import AlbumList from '$lib/components/AlbumList.svelte';
	import PhotoGrid from '$lib/components/PhotoGrid.svelte';
	import ViewControls from '$lib/components/ViewControls.svelte';
	import PhotoPreview from '$lib/components/PhotoPreview.svelte';
	import ContextMenu from '$lib/components/ContextMenu.svelte';
	import BuildSummary from '$lib/components/BuildSummary.svelte';

	let { data } = $props();
	let inventory = $state(data.inventory);
	let activeId = $state(inventory.albums[0]?.fb_album_id ?? null);
	let archive = $derived(inventory.archive ?? []);
	let showArchive = $derived(activeId === '__archive__');
	let buildResult = $state(null);
	let building = $state(false);
	let gridSize = $state(DEFAULT_SIZE);
	let previewOpen = $state(false);
	let previewStart = $state(0);
	let menu = $state({ open: false, x: 0, y: 0, items: [] });
	const toaster = createToaster();

	// Remember the volunteer's chosen thumbnail density across visits.
	$effect(() => {
		const saved = localStorage.getItem(SIZE_STORAGE_KEY);
		if (saved && VIEW_SIZES.some((s) => s.id === saved)) gridSize = saved;
	});

	function setSize(id) {
		gridSize = id;
		localStorage.setItem(SIZE_STORAGE_KEY, id);
	}

	let activeAlbum = $derived(inventory.albums.find((a) => a.fb_album_id === activeId) ?? null);
	let activeCap = $derived(activeAlbum ? activeAlbum.max_per_album : null); // null = no limit
	let activeFull = $derived(
		activeAlbum && activeCap != null ? activeAlbum.count_selected >= activeCap : false
	);
	let totalSelected = $derived(inventory.albums.reduce((n, a) => n + a.count_selected, 0));

	async function onToggle(photo) {
		if (!activeAlbum) return;
		const result = await toggle(activeAlbum.fb_album_id, photo.fbid);
		if (!result.ok && result.cap) {
			toaster.error({
				title: 'Album is full',
				description: `Keep up to ${inventory.max_per_album} photos per album. Remove one to swap.`
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

	function openPreviewAt(index) {
		previewStart = Math.max(0, index);
		previewOpen = true;
	}

	async function revealOnDisk(target) {
		const result = await reveal(target);
		if (!result.ok) {
			toaster.error({ title: "Couldn't open the file manager", description: result.error });
		}
	}

	// Right-click a photo → preview it or jump to its file on disk.
	function openPhotoMenu(photo, e) {
		if (!activeAlbum) return;
		const index = activeAlbum.photos.findIndex((p) => p.fbid === photo.fbid);
		menu = {
			open: true,
			x: e.clientX,
			y: e.clientY,
			items: [
				{ label: 'Preview', icon: 'preview', onSelect: () => openPreviewAt(index) },
				{
					label: 'Show in File Explorer',
					icon: 'folder',
					disabled: !photo.exists,
					hint: photo.exists ? undefined : 'missing',
					onSelect: () => revealOnDisk({ photoFbid: photo.fbid })
				}
			]
		};
	}

	// Right-click an archived photo → preview it (read-only) or open its file.
	function openArchiveMenu(photo, e) {
		const index = archive.findIndex((p) => p.fbid === photo.fbid);
		menu = {
			open: true,
			x: e.clientX,
			y: e.clientY,
			items: [
				{ label: 'Preview', icon: 'preview', onSelect: () => openPreviewAt(index) },
				{
					label: 'Show in File Explorer',
					icon: 'folder',
					disabled: !photo.exists,
					hint: photo.exists ? undefined : 'missing',
					onSelect: () => revealOnDisk({ photoFbid: photo.fbid })
				}
			]
		};
	}

	// Right-click an album → open its media folder on disk.
	function openAlbumMenu(album, e) {
		menu = {
			open: true,
			x: e.clientX,
			y: e.clientY,
			items: [
				{
					label: 'Show in File Explorer',
					icon: 'folder',
					onSelect: () => revealOnDisk({ albumFbid: album.fb_album_id })
				}
			]
		};
	}
</script>

<div class="grid gap-5 lg:grid-cols-[15rem_1fr]">
	<!-- Left rail: album navigation + build (sticky so it follows the scroll) -->
	<aside class="lg:sticky lg:top-[5.25rem] lg:self-start">
		<div class="rounded-xl border border-surface-300 bg-surface-50 p-2 shadow-sm">
			<AlbumList
				albums={inventory.albums}
				nonAlbumCount={inventory.non_album.length}
				archiveCount={archive.length}
				{activeId}
				onSelect={(id) => (activeId = id)}
				onContextMenu={openAlbumMenu}
			/>
		</div>

		<button
			class="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-primary-700 px-4 py-3 font-semibold text-primary-50 shadow-sm transition-colors hover:bg-primary-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-progress disabled:opacity-70"
			type="button"
			onclick={runBuild}
			disabled={building}
		>
			{#if building}
				<span
					class="size-4 animate-spin rounded-full border-2 border-primary-200 border-t-primary-50"
					aria-hidden="true"
				></span>
				Building…
			{:else}
				<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="1.75"
					stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4" /></svg>
				Build ready folder
			{/if}
		</button>
		<p class="mt-2 px-1 text-center text-xs text-surface-500">
			{totalSelected} selected · {inventory.non_album.length} auto-kept
		</p>
	</aside>

	<!-- Right pane: active album OR the read-only archive -->
	<section class="min-w-0">
		{#if showArchive}
			<header
				class="sticky top-[5.25rem] z-20 mb-4 bg-surface-100 pt-1 pb-3 before:pointer-events-none before:absolute before:inset-x-0 before:bottom-full before:h-24 before:bg-surface-100 before:content-['']"
			>
				<div class="flex min-w-0 items-baseline gap-3">
					<h1 class="truncate text-xl font-semibold tracking-tight text-surface-900">Archive</h1>
					<p class="shrink-0 text-sm font-medium tabular-nums text-surface-500">
						{archive.length} set aside
					</p>
				</div>
				<p class="mt-2 text-sm text-surface-500">
					Photos posted with a news caption (BREAKING, LOOK, …) from Mobile uploads &amp; Photos.
					These are excluded from the build. Right-click to preview or open the file.
				</p>
			</header>

			{#if archive.length}
				<PhotoGrid
					album={{ name: 'Archive', photos: archive }}
					thumb={thumbUrl}
					size={gridSize}
					selectable={false}
					onContextMenu={openArchiveMenu}
				/>
			{/if}
		{:else if activeAlbum}
			<!-- Sticky toolbar: the album, its fill state, and the view + preview
			     controls stay pinned under the app bar so they never scroll away.
			     The ::before mask hides photos scrolling through the gap to the bar. -->
			<header
				class="sticky top-[5.25rem] z-20 mb-4 bg-surface-100 pt-1 pb-3 before:pointer-events-none before:absolute before:inset-x-0 before:bottom-full before:h-24 before:bg-surface-100 before:content-['']"
			>
				<div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
					<div class="flex min-w-0 items-baseline gap-3">
						<h1 class="truncate text-xl font-semibold tracking-tight text-surface-900">
							{activeAlbum.name}
						</h1>
						<p
							class="shrink-0 text-sm font-medium tabular-nums"
							class:text-warning-700={activeFull}
							class:text-surface-500={!activeFull}
						>
							{#if activeCap != null}
								{activeAlbum.count_selected} / {activeCap} selected
							{:else}
								{activeAlbum.count_selected} selected · no limit
							{/if}
						</p>
					</div>
					<ViewControls
						size={gridSize}
						onSize={setSize}
						onOpenPreview={() => openPreviewAt(0)}
						previewDisabled={activeAlbum.photos.length === 0}
					/>
				</div>
				<!-- Fill bar (capped albums only) -->
				{#if activeCap != null}
					<div class="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-200">
						<div
							class="h-full rounded-full transition-[width] duration-300"
							class:bg-warning-500={activeFull}
							class:bg-primary-600={!activeFull}
							style="width: {(activeAlbum.count_selected / activeCap) * 100}%"
						></div>
					</div>
				{/if}
				<p class="mt-2 text-sm text-surface-500">
					{#if activeCap == null}
						Click photos to keep as many as you want from this album. Right-click a photo for more.
					{:else if activeFull}
						This album is full. Remove a photo to choose a different one.
					{:else}
						Click photos to keep up to {activeCap} from this album. Right-click a photo for more.
					{/if}
				</p>
			</header>

			<PhotoGrid
				album={activeAlbum}
				thumb={thumbUrl}
				full={activeFull}
				size={gridSize}
				{onToggle}
				onContextMenu={openPhotoMenu}
			/>
		{:else}
			<div
				class="grid place-items-center rounded-xl border border-dashed border-surface-300 bg-surface-50 px-6 py-16 text-center"
			>
				<p class="font-medium text-surface-700">No named albums in this export</p>
				<p class="mt-1 text-sm text-surface-500">
					All {inventory.non_album.length} photos are non-album and will be kept automatically.
				</p>
			</div>
		{/if}
	</section>
</div>

{#if previewOpen && showArchive && archive.length}
	<PhotoPreview
		album={{ name: 'Archive', photos: archive }}
		thumb={thumbUrl}
		preview={previewUrl}
		selectable={false}
		startIndex={previewStart}
		onToggle={() => {}}
		onClose={() => (previewOpen = false)}
	/>
{:else if previewOpen && activeAlbum && activeAlbum.photos.length}
	<PhotoPreview
		album={activeAlbum}
		thumb={thumbUrl}
		preview={previewUrl}
		full={activeFull}
		startIndex={previewStart}
		{onToggle}
		onClose={() => (previewOpen = false)}
	/>
{/if}

<ContextMenu
	open={menu.open}
	x={menu.x}
	y={menu.y}
	items={menu.items}
	onClose={() => (menu = { ...menu, open: false })}
/>

{#if buildResult}
	<BuildSummary result={buildResult} onClose={() => (buildResult = null)} />
{/if}

<Toaster {toaster}></Toaster>
