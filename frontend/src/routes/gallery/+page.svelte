<script>
	import { Toaster, createToaster } from '@skeletonlabs/skeleton-svelte';
	import { build, reveal, thumbUrl, previewUrl, toggle, videoThumbUrl, videoUrl, renameAlbum, resetAlbumName, archiveAlbum, unarchiveAlbum } from '$lib/api.js';
	import { prefetchAlbumThumbs, clearPrefetchCache } from '$lib/imageCache.js';
	import { seedMissingThumbnails, thumbnailMissing } from '$lib/videoThumbs.js';
	import { DEFAULT_SIZE, SIZE_STORAGE_KEY, VIEW_SIZES } from '$lib/viewSizes.js';
	import AlbumList from '$lib/components/AlbumList.svelte';
	import PhotoGrid from '$lib/components/PhotoGrid.svelte';
	import ViewControls from '$lib/components/ViewControls.svelte';
	import PhotoPreview from '$lib/components/PhotoPreview.svelte';
	import VideoPreview from '$lib/components/VideoPreview.svelte';
	import ContextMenu from '$lib/components/ContextMenu.svelte';
	import BuildSummary from '$lib/components/BuildSummary.svelte';
	import SelectionPanel from '$lib/components/SelectionPanel.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';

	let { data } = $props();
	let inventory = $state(data.inventory || {});
	let activeId = $state(inventory.albums?.[0]?.fb_album_id ?? null);
	let archive = $derived(inventory.archive ?? []);
	let showArchive = $derived(activeId === '__archive__');
	let videos = $derived(inventory.videos ?? []);
	let showVideos = $derived(activeId === '__videos__');
	let videoPreview = $state(null); // the video obj being picked, or null
	// Cache-bust key per video so a freshly-seeded/chosen still reloads in the grid.
	let thumbVersion = $state({});
	function videoTileSrc(fbid) {
		return `${videoThumbUrl(fbid)}?v=${thumbVersion[fbid] ?? 0}`;
	}
	let buildResult = $state(null);
	let building = $state(false);
	let gridSize = $state(DEFAULT_SIZE);
	let previewOpen = $state(false);
	let previewStart = $state(0);
	let menu = $state({ open: false, x: 0, y: 0, items: [] });
	let archiveConfirm = $state({ open: false, album: null });
	let unarchiveConfirm = $state({ open: false, album: null });
	let resetConfirm = $state({ open: false, album: null });
	let selectionOpen = $state(false);
	let albumWidth = $state(240);
	let albumDragging = $state(false);
	let editingAlbumId = $state(null);
	let descExpanded = $state(false);
	const toaster = createToaster();

	function formatFBDate(isoString) {
		if (!isoString) return '';
		const date = new Date(isoString);
		return new Intl.DateTimeFormat('en-US', {
			timeZone: 'Asia/Manila',
			month: 'long',
			day: 'numeric',
			year: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
			hour12: true
		}).format(date).replace('\u202f', ' '); // standardize space for AM/PM
	}

	$effect(() => {
		// track activeId to reset description expansion when switching albums
		if (activeId !== undefined) {
			descExpanded = false;
		}
	});

	// When an album is activated, eagerly prefetch all its thumbnails so that
	// switching back later loads images from the browser cache instantly.
	$effect(() => {
		if (showArchive && archive.length) {
			prefetchAlbumThumbs('__archive__', archive, thumbUrl);
		} else if (showVideos && videos.length) {
			prefetchAlbumThumbs('__videos__', videos, videoTileSrc);
		} else if (activeAlbum?.photos?.length) {
			prefetchAlbumThumbs(activeAlbum.fb_album_id, activeAlbum.photos, thumbUrl);
		}
	});

	function startAlbumResize(e) {
		e.preventDefault();
		albumDragging = true;
		const startX = e.clientX;
		const startW = albumWidth;

		function onMove(ev) {
			const delta = ev.clientX - startX;
			albumWidth = Math.max(140, Math.min(400, startW + delta));
		}
		function onUp() {
			albumDragging = false;
			window.removeEventListener('pointermove', onMove);
			window.removeEventListener('pointerup', onUp);
		}
		window.addEventListener('pointermove', onMove);
		window.addEventListener('pointerup', onUp);
	}

	// Remember the volunteer's chosen thumbnail density across visits.
	$effect(() => {
		const saved = localStorage.getItem(SIZE_STORAGE_KEY);
		if (saved && VIEW_SIZES.some((s) => s.id === saved)) gridSize = saved;
	});

	// On load, give every video a default first-frame still so the grid shows real
	// frames and every video is build-ready. Sequential + throttled via the util.
	$effect(() => {
		if (!videos.length) return;
		seedMissingThumbnails(videos, {
			videoSrc: videoUrl,
			needsSeed: (fbid) => thumbnailMissing(fbid),
			onSeeded: (fbid) => (thumbVersion = { ...thumbVersion, [fbid]: Date.now() })
		});
	});

	function setSize(id) {
		gridSize = id;
		localStorage.setItem(SIZE_STORAGE_KEY, id);
	}

	let allAlbumsList = $derived([...(inventory.albums ?? []), ...(inventory.archived_albums ?? [])]);
	let activeAlbum = $derived(allAlbumsList.find((a) => a.fb_album_id === activeId) ?? null);
	let isActiveArchived = $derived(inventory.archived_albums?.some(a => a.fb_album_id === activeId) ?? false);
	let activeCap = $derived(activeAlbum ? activeAlbum.max_per_album : null); // null = no limit
	let activeFull = $derived(
		activeAlbum && activeCap != null ? activeAlbum.count_selected >= activeCap : false
	);
	let totalSelected = $derived((inventory.albums ?? []).reduce((n, a) => n + a.count_selected, 0));

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

	/** Toggle a photo from the selection panel (always uses the active album). */
	async function onPanelToggle(photo) {
		if (!activeAlbum) return;
		const result = await toggle(activeAlbum.fb_album_id, photo.fbid);
		if (!result.ok && result.cap) return;
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

	function openVideoPreview(video) {
		videoPreview = video;
	}

	function onVideoChosen(fbid) {
		thumbVersion = { ...thumbVersion, [fbid]: Date.now() };
	}

	// Right-click a video → choose its thumbnail (replaces "Preview") or open its file.
	function openVideoMenu(video, e) {
		menu = {
			open: true,
			x: e.clientX,
			y: e.clientY,
			items: [
				{ label: 'Choose Thumbnail', icon: 'preview', onSelect: () => openVideoPreview(video) },
				{
					label: 'Show in File Explorer',
					icon: 'folder',
					disabled: !video.exists,
					hint: video.exists ? undefined : 'missing',
					onSelect: () => revealOnDisk({ photoFbid: video.fbid })
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

	// Right-click an album → rename, archive, or open its media folder on disk.
	function openAlbumMenu(album, e) {
		const isArchived = inventory.archived_albums?.some(a => a.fb_album_id === album.fb_album_id);
		menu = {
			open: true,
			x: e.clientX,
			y: e.clientY,
			items: [
				...(!isArchived ? [
					{
						label: 'Rename',
						icon: 'rename',
						subItems: [
							{
								label: 'Reset to default name',
								disabled: !album.original_name || album.original_name === album.name,
								onSelect: () => {
									if (album.original_name && album.original_name !== album.name) {
										resetConfirm = { open: true, album };
									}
								}
							}
						],
						onSelect: () => {
							editingAlbumId = album.fb_album_id;
						}
					},
					{
						label: 'Add to Archive',
						icon: 'archive',
						onSelect: () => {
							archiveConfirm = { open: true, album };
						}
					}
				] : [
					{
						label: 'Unarchive',
						icon: 'archive',
						onSelect: () => {
							unarchiveConfirm = { open: true, album };
						}
					}
				]),
				{
					label: 'Show in File Explorer',
					icon: 'folder',
					onSelect: () => revealOnDisk({ albumFbid: album.fb_album_id })
				}
			]
		};
	}
</script>

<div class="flex gap-5 lg:h-full lg:min-h-0">
	<!-- Left rail: the album list scrolls on its own; build + counts stay pinned below it. -->
	<aside class="relative flex shrink-0 flex-col lg:min-h-0" style="width: {albumWidth}px;">
		<div
			class="rounded-xl border border-surface-300 bg-surface-50 p-2 shadow-sm lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain"
		>
			<AlbumList
				albums={inventory.albums}
				archivedAlbums={inventory.archived_albums}
				nonAlbumCount={inventory.non_album.length}
				archiveCount={archive.length}
				videosCount={videos.length}
				{activeId}
				editingId={editingAlbumId}
				onSelect={(id) => { activeId = id; editingAlbumId = null; }}
				onContextMenu={openAlbumMenu}
				onRename={async (album, newName) => {
					const result = await renameAlbum(album.fb_album_id, newName);
					if (result.ok) {
						album.name = result.name;
					} else {
						toaster.error({ title: 'Rename failed', description: result.error });
					}
					editingAlbumId = null;
				}}
				onCancelRename={() => (editingAlbumId = null)}
				onStartRename={(id) => (editingAlbumId = id)}
			/>
		</div>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="album-resize-handle"
			class:active={albumDragging}
			onpointerdown={startAlbumResize}
		></div>

		<button
			class="mt-3 flex w-full shrink-0 items-center justify-center gap-2 rounded-xl bg-primary-700 px-4 py-3 font-semibold text-primary-50 shadow-sm transition-colors hover:bg-primary-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-progress disabled:opacity-70"
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
		<p class="mt-2 shrink-0 px-1 text-center text-xs text-surface-500">
			{totalSelected} selected · {inventory.non_album.length} auto-kept
		</p>
	</aside>

	<!-- Right pane: active album OR the read-only archive. Header stays put; only the
	     photo grid below it scrolls (and only when the pointer is over the grid). -->
	<section class="flex min-w-0 flex-1 flex-col lg:min-h-0">
		{#if showArchive}
			<header class="mb-2 shrink-0 pt-1 pb-1">
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
				<div class="lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain">
					<PhotoGrid
						album={{ name: 'Archive', photos: archive }}
						thumb={thumbUrl}
						size={gridSize}
						selectable={false}
						onContextMenu={openArchiveMenu}
					/>
				</div>
			{/if}
		{:else if showVideos}
			<header class="mb-2 shrink-0 pt-1 pb-1">
				<div class="flex min-w-0 items-baseline gap-3">
					<h1 class="truncate text-xl font-semibold tracking-tight text-surface-900">Videos</h1>
					<p class="shrink-0 text-sm font-medium tabular-nums text-surface-500">
						{videos.length} · always kept
					</p>
				</div>
				<p class="mt-2 text-sm text-surface-500">
					Videos aren’t imported — a still frame replaces each one. Click a video to play it and
					choose the frame, or right-click for “Choose Thumbnail”. A first frame is picked by default.
				</p>
			</header>

			{#if videos.length}
				<div class="lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain">
					<PhotoGrid
						album={{ name: 'Videos', photos: videos }}
						thumb={videoTileSrc}
						size={gridSize}
						selectable={false}
						video
						onToggle={openVideoPreview}
						onContextMenu={openVideoMenu}
					/>
				</div>
			{/if}
		{:else if activeAlbum}
			<!-- Toolbar: the album, its fill state, and the view + preview controls sit above
			     the grid and never scroll — only the grid below scrolls. -->
			<header class="mb-2 shrink-0 pt-1 pb-1">
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
					<div class="flex items-center gap-1">
					<ViewControls
						size={gridSize}
						onSize={setSize}
						onOpenPreview={() => openPreviewAt(0)}
						previewDisabled={activeAlbum.photos.length === 0}
					/>
					<button
						type="button"
						class="ml-1 inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
						class:bg-primary-100={selectionOpen}
						class:text-primary-800={selectionOpen}
						class:text-surface-600={!selectionOpen}
						class:hover:bg-surface-200={!selectionOpen}
						onclick={() => (selectionOpen = !selectionOpen)}
						title={selectionOpen ? 'Hide selection panel' : 'Show selection panel'}
						aria-pressed={selectionOpen}
					>
						<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
						{totalSelected}
					</button>
				</div>
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
				{#if activeAlbum.post_timestamp}
					<p class="mt-2 text-xs font-medium text-surface-500 uppercase tracking-wide">
						Date posted on FB: {formatFBDate(activeAlbum.post_timestamp)}
					</p>
				{/if}
				{#if activeAlbum.description}
					{@const isLongDesc = activeAlbum.description.length > 120 || activeAlbum.description.split('\n').length > 2}
					<div class="mt-1.5 text-xs text-surface-600 border-l-2 border-surface-300 pl-2.5 py-0.5">
						<p class="whitespace-pre-wrap break-words leading-relaxed" class:line-clamp-2={isLongDesc && !descExpanded}>
							{activeAlbum.description}
						</p>
						{#if isLongDesc}
							{#if !descExpanded}
								<button type="button" class="mt-0.5 font-medium text-primary-600 hover:text-primary-700 hover:underline" onclick={() => (descExpanded = true)}>
									Read more
								</button>
							{:else}
								<button type="button" class="mt-0.5 font-medium text-primary-600 hover:text-primary-700 hover:underline" onclick={() => (descExpanded = false)}>
									See less
								</button>
							{/if}
						{/if}
					</div>
				{/if}
			</header>

			<div class="lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain">
				<PhotoGrid
					album={activeAlbum}
					thumb={thumbUrl}
					full={activeFull}
					size={gridSize}
					{onToggle}
					onContextMenu={openPhotoMenu}
					selectable={!isActiveArchived}
				/>
			</div>
		{:else}
			<div
				class="grid place-items-center rounded-xl border border-dashed border-surface-300 bg-surface-50 px-6 py-16 text-center"
			>
				<p class="font-medium text-surface-700">No named albums in this export</p>
				<p class="mt-1 text-sm text-surface-500">
					All {inventory.non_album?.length ?? 0} photos are non-album and will be kept automatically.
				</p>
			</div>
		{/if}
	</section>

	<!-- Right rail: selection panel (collapsible + resizable) -->
	<SelectionPanel
		album={activeAlbum}
		open={selectionOpen}
		onClose={() => (selectionOpen = false)}
		onToggle={onPanelToggle}
	/>
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
		selectable={!isActiveArchived}
		startIndex={previewStart}
		{onToggle}
		onClose={() => (previewOpen = false)}
	/>
{/if}

{#if videoPreview}
	<VideoPreview
		video={videoPreview}
		onThumbnailChosen={onVideoChosen}
		onClose={() => (videoPreview = null)}
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

<ConfirmDialog
	open={archiveConfirm.open}
	title="Archive album"
	message={archiveConfirm.album
		? `Are you sure you wish to archive the album "${archiveConfirm.album.name}"? All ${archiveConfirm.album.photos.length} photo(s) will be excluded from the build.`
		: ''}
	confirmLabel="Yes"
	cancelLabel="No"
	onCancel={() => (archiveConfirm = { open: false, album: null })}
	onConfirm={async () => {
		const album = archiveConfirm.album;
		archiveConfirm = { open: false, album: null };
		if (!album) return;
		const result = await archiveAlbum(album.fb_album_id);
		if (result.ok) {
			inventory.albums = inventory.albums.filter(
				(a) => a.fb_album_id !== album.fb_album_id
			);
			inventory.archived_albums = [...(inventory.archived_albums ?? []), album];
			activeId = inventory.albums[0]?.fb_album_id ?? '__archive__';
			toaster.success({
				title: 'Album archived',
				description: `${result.moved} photo(s) moved to the archive.`
			});
		} else {
			toaster.error({ title: 'Archive failed', description: result.error });
		}
	}}
/>

<ConfirmDialog
	open={unarchiveConfirm.open}
	title="Unarchive album"
	message={unarchiveConfirm.album
		? `Are you sure you wish to unarchive the album "${unarchiveConfirm.album.name}"? It will be included in the build again.`
		: ''}
	confirmLabel="Yes"
	cancelLabel="No"
	onCancel={() => (unarchiveConfirm = { open: false, album: null })}
	onConfirm={async () => {
		const album = unarchiveConfirm.album;
		unarchiveConfirm = { open: false, album: null };
		if (!album) return;
		const result = await unarchiveAlbum(album.fb_album_id);
		if (result.ok) {
			inventory.archived_albums = inventory.archived_albums.filter(
				(a) => a.fb_album_id !== album.fb_album_id
			);
			inventory.albums = [...inventory.albums, album];
			activeId = album.fb_album_id;
			toaster.success({
				title: 'Album unarchived',
				description: `${result.moved} photo(s) restored.`
			});
		} else {
			toaster.error({ title: 'Unarchive failed', description: result.error });
		}
	}}
/>

<ConfirmDialog
	open={resetConfirm.open}
	title="Reset album name"
	message={resetConfirm.album
		? `Are you sure you want to reset "${resetConfirm.album.name}" to its original default name "${resetConfirm.album.original_name}"?`
		: ''}
	confirmLabel="Yes, reset it"
	cancelLabel="Cancel"
	onCancel={() => (resetConfirm = { open: false, album: null })}
	onConfirm={async () => {
		const album = resetConfirm.album;
		resetConfirm = { open: false, album: null };
		if (!album) return;
		const result = await resetAlbumName(album.fb_album_id);
		if (result.ok) {
			album.name = result.name;
			toaster.success({ title: 'Name reset', description: `Album is now named "${result.name}"` });
		} else {
			toaster.error({ title: 'Reset failed', description: result.error });
		}
	}}
/>

<Toaster {toaster}></Toaster>

<style>
	.album-resize-handle {
		position: absolute;
		right: -4px;
		top: 0;
		bottom: 0;
		width: 8px;
		cursor: col-resize;
		z-index: 10;
		border-radius: 4px;
		transition: background-color 0.15s;
	}

	.album-resize-handle:hover {
		background-color: rgba(27, 94, 32, 0.15);
	}

	.album-resize-handle.active {
		background-color: rgba(27, 94, 32, 0.2);
	}
</style>
