<script>
	import { Toaster, createToaster } from '@skeletonlabs/skeleton-svelte';
	import { build, reveal, thumbUrl, previewUrl, toggle, deselectAll, videoThumbUrl, videoUrl, renameAlbum, resetAlbumName, archiveAlbum, unarchiveAlbum } from '$lib/api.js';
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
	let buildConfirm = $state(false);
	let selectionOpen = $state(false);
	let albumOpen = $state(true);
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
			onSeeded: (fbid, sizeBytes) => {
				thumbVersion = { ...thumbVersion, [fbid]: Date.now() };
				const v = videos.find((x) => x.fbid === fbid);
				if (v) {
					v.video_thumb_tag = 'AUTO';
					if (sizeBytes !== undefined) v.file_size_bytes = sizeBytes;
				}
			}
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
	let totalSelectedMB = $derived(
		(
			((inventory.albums ?? []).flatMap((a) => (a.photos ?? []).filter((p) => p.selected)).reduce((sum, p) => sum + (p.file_size_bytes || 0), 0) +
			(inventory.videos ?? []).filter((v) => v.selected).reduce((sum, v) => sum + (v.file_size_bytes || 0), 0))
		/ (1024 * 1024)).toFixed(2)
	);

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

	async function onVideoToggle(video) {
		const result = await toggle('__videos__', video.fbid);
		if (!result.ok) return;
		video.selected = result.selected;
	}

	async function onDeselectAll() {
		if (showVideos) {
			const result = await deselectAll('__videos__');
			if (result.ok) {
				for (const video of videos) {
					video.selected = false;
				}
			}
		} else if (activeAlbum) {
			const result = await deselectAll(activeAlbum.fb_album_id);
			if (result.ok) {
				activeAlbum.count_selected = 0;
				for (const photo of activeAlbum.photos) {
					photo.selected = false;
				}
			}
		}
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

	function onVideoChosen(fbid, sizeBytes) {
		thumbVersion = { ...thumbVersion, [fbid]: Date.now() };
		const v = videos.find((x) => x.fbid === fbid);
		if (v) {
			v.video_thumb_tag = 'APPLIED';
			if (sizeBytes !== undefined) v.file_size_bytes = sizeBytes;
		}
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
							albumOpen = true;
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
	{#if albumOpen}
		<aside class="album-sidebar" style="width: {albumWidth}px;">
			<!-- Sidebar header with collapse button -->
			<div class="album-sidebar-header">
				<span class="album-sidebar-title">
					<svg viewBox="0 0 24 24" class="size-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /></svg>
					Albums
				</span>
				<button
					type="button"
					class="album-sidebar-collapse"
					onclick={() => (albumOpen = false)}
					aria-label="Collapse album sidebar"
					title="Collapse sidebar"
				>
					<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m11 17-5-5 5-5" /><path d="m18 17-5-5 5-5" /></svg>
				</button>
			</div>

			<div
				class="rounded-xl border border-surface-300 bg-surface-50 p-2 shadow-sm lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain"
			>
				<AlbumList
					albums={inventory.albums}
					archivedAlbums={inventory.archived_albums}
					archiveCount={archive.length}
					videosCount={videos.length}
					videosSelectedCount={videos.filter(v => v.selected).length}
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

			<div class="mt-3 flex flex-col px-1 text-center text-xs font-medium text-surface-600">
				{totalSelected} images | {videos.filter(v => v.selected).length} videos | ~{totalSelectedMB}MB
			</div>
			<button
				class="mt-2 flex w-full shrink-0 items-center justify-center gap-2 rounded-xl bg-primary-700 px-4 py-3 font-semibold text-primary-50 shadow-sm transition-colors hover:bg-primary-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-progress disabled:opacity-70"
				type="button"
				onclick={() => (buildConfirm = true)}
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
		</aside>
	{:else}
		<!-- Collapsed album rail: thin icon strip with album shortcodes -->
		<aside class="album-sidebar-collapsed">
			<button
				type="button"
				class="album-expand-btn"
				onclick={() => (albumOpen = true)}
				aria-label="Expand album sidebar"
				title="Show albums"
			>
				<svg viewBox="0 0 24 24" class="size-3.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m13 17 5-5-5-5" /><path d="m6 17 5-5-5-5" /></svg>
			</button>

			<div class="rail-divider" style="height: 1px; background: var(--color-surface-300, #d4d4d4);"></div>

			<!-- Regular albums with group dividers -->
			{#each inventory.albums as a, i (a.fb_album_id)}
				{@const group = a.origin || 'Main Albums'}
				{@const prevGroup = i > 0 ? (inventory.albums[i - 1].origin || 'Main Albums') : null}
				{#if i > 0 && group !== prevGroup}
					<div class="rail-divider"></div>
				{:else if i > 0}
					<div class="rail-dot"></div>
				{/if}
				<button
					type="button"
					class="rail-album-btn"
					class:rail-active={a.fb_album_id === activeId}
					onclick={() => { activeId = a.fb_album_id; editingAlbumId = null; }}
					ondblclick={() => (albumOpen = true)}
					oncontextmenu={(e) => { e.preventDefault(); openAlbumMenu(a, e); }}
					title={a.name}
				>A{i + 1}</button>
			{/each}

			{#if videos.length > 0}
				<div class="rail-divider"></div>
				<button
					type="button"
					class="rail-icon-btn"
					class:rail-active={activeId === '__videos__'}
					onclick={() => { activeId = '__videos__'; editingAlbumId = null; }}
					ondblclick={() => (albumOpen = true)}
					title="Videos"
				>
					<svg viewBox="0 0 24 24" class="size-3.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="14" height="14" rx="2" /><path d="m16 10 6-3v10l-6-3z" /></svg>
				</button>
			{/if}

			{#if archive.length > 0}
				<div class="rail-divider"></div>
				<button
					type="button"
					class="rail-icon-btn"
					class:rail-active={activeId === '__archive__'}
					onclick={() => { activeId = '__archive__'; editingAlbumId = null; }}
					ondblclick={() => (albumOpen = true)}
					title="Archive"
				>
					<svg viewBox="0 0 24 24" class="size-3.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="4" rx="1" /><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4" /></svg>
				</button>
			{/if}

			{#if inventory.archived_albums && inventory.archived_albums.length > 0}
				<div class="rail-divider"></div>
				{#each inventory.archived_albums as a, i (a.fb_album_id)}
					{#if i > 0}
						<div class="rail-dot"></div>
					{/if}
					<button
						type="button"
						class="rail-album-btn rail-archived"
						class:rail-active={a.fb_album_id === activeId}
						onclick={() => { activeId = a.fb_album_id; editingAlbumId = null; }}
						ondblclick={() => (albumOpen = true)}
						oncontextmenu={(e) => { e.preventDefault(); openAlbumMenu(a, e); }}
						title={a.name}
					>{a.name.length > 3 ? a.name.slice(0, 3) : a.name}</button>
				{/each}
			{/if}
		</aside>
	{/if}

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
						onDblClick={(photo) => {
							const index = archive.findIndex((p) => p.fbid === photo.fbid);
							if (index !== -1) openPreviewAt(index);
						}}
					/>
				</div>
			{/if}
		{:else if showVideos}
			<header class="mb-2 shrink-0 pt-1 pb-1">
				<div class="flex min-w-0 items-center gap-3">
					<h1 class="truncate text-xl font-semibold tracking-tight text-surface-900">Videos</h1>
					<div class="flex shrink-0 items-center gap-2">
						<p class="text-sm font-medium tabular-nums text-surface-500">
							{videos.filter((v) => v.selected).length} / {videos.length} selected
						</p>
						{#if videos.some((v) => v.selected)}
							<button
								type="button"
								class="flex items-center gap-1.5 rounded-lg border border-surface-300 bg-surface-50 px-2.5 py-1 text-xs font-medium text-surface-700 transition-colors hover:bg-surface-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
								onclick={onDeselectAll}
							>
								<svg viewBox="0 0 24 24" class="size-3.5 text-surface-500" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
								Deselect All
							</button>
						{/if}
					</div>
				</div>
				<p class="mt-2 text-sm text-surface-500">
					Videos aren’t imported — a still frame replaces each one. Click a video to play it and
					choose the frame, or right-click for “Choose Thumbnail”. They are not auto-kept.
					<br>
					<span class="inline-block rounded bg-warning-900/75 px-1.5 py-0.5 text-[0.6rem] font-semibold text-warning-50">AUTO</span>
					automatically generated from the first frame.
					<br>
					<span class="inline-block rounded bg-primary-900/75 px-1.5 py-0.5 text-[0.6rem] font-semibold text-primary-50">APPLIED</span>
					hand-picked by you.
				</p>
			</header>

			{#if videos.length}
				<div class="lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain">
					<PhotoGrid
						album={{ name: 'Videos', photos: videos }}
						thumb={videoTileSrc}
						size={gridSize}
						selectable={true}
						video
						onToggle={onVideoToggle}
						onContextMenu={openVideoMenu}
						onDblClick={(video) => openVideoPreview(video)}
					/>
				</div>
			{/if}
		{:else if activeAlbum}
			<!-- Toolbar: the album, its fill state, and the view + preview controls sit above
			     the grid and never scroll — only the grid below scrolls. -->
			<header class="mb-2 shrink-0 pt-1 pb-1">
				<div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
					<div class="flex min-w-0 items-center gap-3">
						<h1 class="truncate text-xl font-semibold tracking-tight text-surface-900">
							{activeAlbum.name}
						</h1>
						<div class="flex shrink-0 items-center gap-2">
							<p
								class="text-sm font-medium tabular-nums"
								class:text-warning-700={activeFull}
								class:text-surface-500={!activeFull}
							>
								{#if activeCap != null}
									{activeAlbum.count_selected} / {activeCap} selected
								{:else}
									{activeAlbum.count_selected} selected · no limit
								{/if}
							</p>
							{#if activeAlbum.count_selected > 0}
								<button
									type="button"
									class="flex items-center gap-1.5 rounded-lg border border-surface-300 bg-surface-50 px-2.5 py-1 text-xs font-medium text-surface-700 transition-colors hover:bg-surface-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
									onclick={onDeselectAll}
								>
									<svg viewBox="0 0 24 24" class="size-3.5 text-surface-500" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
									Deselect All
								</button>
							{/if}
						</div>
					</div>
					<div class="flex items-center gap-1">
					<ViewControls
						size={gridSize}
						onSize={setSize}
					/>
					<button
						type="button"
						class="ml-1 inline-flex items-center justify-center rounded-lg p-2 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
						class:bg-primary-100={selectionOpen}
						class:text-primary-800={selectionOpen}
						class:text-surface-600={!selectionOpen}
						class:hover:bg-surface-200={!selectionOpen}
						onclick={() => (selectionOpen = !selectionOpen)}
						title={selectionOpen ? 'Hide selection panel' : 'Show selection panel'}
						aria-pressed={selectionOpen}
					>
						<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 22H4a2 2 0 0 1-2-2V6"/><path d="m22 13-1.296-1.296a2.41 2.41 0 0 0-3.408 0L11 18"/><circle cx="12" cy="8" r="2"/><rect width="16" height="16" x="6" y="2" rx="2"/></svg>
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
					onDblClick={(photo) => {
						const index = activeAlbum.photos.findIndex((p) => p.fbid === photo.fbid);
						if (index !== -1) openPreviewAt(index);
					}}
					selectable={!isActiveArchived}
				/>
			</div>
		{:else}
			<div
				class="grid place-items-center rounded-xl border border-dashed border-surface-300 bg-surface-50 px-6 py-16 text-center"
			>
				<p class="font-medium text-surface-700">No albums in this export</p>
			</div>
		{/if}
	</section>

	<!-- Right rail: selection panel (collapsible + resizable) -->
	<SelectionPanel
		album={activeAlbum}
		open={selectionOpen}
		onClose={() => (selectionOpen = false)}
		onToggle={onPanelToggle}
		onDblClick={(photo) => {
			const index = activeAlbum.photos.findIndex((p) => p.fbid === photo.fbid);
			if (index !== -1) openPreviewAt(index);
		}}
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
		version={thumbVersion[videoPreview.fbid] ?? 0}
		onThumbnailChosen={onVideoChosen}
		onToggle={onVideoToggle}
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
	open={buildConfirm}
	title="Build ready folder"
	message="Are you sure you want to build the ready folder? This will process and copy all selected photos and videos to the ready directory."
	confirmLabel="Yes, build it"
	cancelLabel="Cancel"
	onCancel={() => (buildConfirm = false)}
	onConfirm={async () => {
		buildConfirm = false;
		await runBuild();
	}}
/>

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
			const newAlbums = [...inventory.albums];
			const origin = album.origin || 'Main Albums';
			let insertIdx = newAlbums.findIndex(a => (a.origin || 'Main Albums') === origin);
			if (insertIdx !== -1) {
				while (insertIdx < newAlbums.length && (newAlbums[insertIdx].origin || 'Main Albums') === origin) {
					insertIdx++;
				}
				newAlbums.splice(insertIdx, 0, album);
			} else {
				newAlbums.push(album);
			}
			inventory.albums = newAlbums;
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
	/* --- Album sidebar (expanded) --- */
	.album-sidebar {
		position: relative;
		display: flex;
		flex-shrink: 0;
		flex-direction: column;
		min-height: 0;
	}

	@media (min-width: 1024px) {
		.album-sidebar {
			min-height: 0;
		}
	}

	.album-sidebar-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		padding-bottom: 0.375rem;
		margin-bottom: 0.25rem;
		flex-shrink: 0;
	}

	.album-sidebar-title {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-surface-700, #404040);
		letter-spacing: -0.01em;
	}

	.album-sidebar-collapse {
		display: grid;
		place-items: center;
		padding: 0.25rem;
		border-radius: 0.375rem;
		color: var(--color-surface-500, #737373);
		transition: all 0.15s;
		cursor: pointer;
		border: none;
		background: none;
	}

	.album-sidebar-collapse:hover {
		background: var(--color-surface-200, #e5e5e5);
		color: var(--color-surface-700, #404040);
	}

	/* --- Album sidebar (collapsed icon rail) --- */
	.album-sidebar-collapsed {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		padding: 0.375rem 0;
		flex-shrink: 0;
		width: 36px;
		border-radius: 0.75rem;
		background: var(--color-surface-50, #fafafa);
		border: 1px solid var(--color-surface-300, #d4d4d4);
		overflow-y: auto;
		overscroll-behavior: contain;
		scrollbar-width: none; /* Firefox */
		-ms-overflow-style: none; /* IE/Edge */
	}

	.album-sidebar-collapsed::-webkit-scrollbar {
		display: none; /* Chrome/Safari */
	}

	@media (min-width: 1024px) {
		.album-sidebar-collapsed {
			max-height: 100%;
		}
	}

	.album-expand-btn {
		display: grid;
		place-items: center;
		padding: 0.25rem;
		border-radius: 0.375rem;
		color: var(--color-surface-500, #737373);
		transition: all 0.15s;
		cursor: pointer;
		border: none;
		background: none;
		flex-shrink: 0;
	}

	.album-expand-btn:hover {
		background: var(--color-surface-200, #e5e5e5);
		color: var(--color-surface-700, #404040);
	}

	.rail-divider {
		width: 100%;
		height: 3px;
		background: var(--color-surface-400, #a3a3a3);
		flex-shrink: 0;
		margin: 0.125rem 0;
	}

	.rail-dot {
		width: 12px;
		height: 1px;
		background: var(--color-surface-300, #d4d4d4);
		flex-shrink: 0;
	}

	.rail-album-btn {
		width: 28px;
		height: 28px;
		display: grid;
		place-items: center;
		border-radius: 0.375rem;
		font-size: 0.6875rem;
		font-weight: 700;
		letter-spacing: -0.01em;
		color: var(--color-surface-600, #525252);
		transition: all 0.15s;
		cursor: pointer;
		border: none;
		background: none;
		padding: 0;
		line-height: 1;
		flex-shrink: 0;
	}

	.rail-album-btn:hover {
		background: var(--color-surface-200, #e5e5e5);
		color: var(--color-surface-800, #262626);
	}

	.rail-album-btn.rail-active {
		background: var(--color-primary-100, #dcfce7);
		color: var(--color-primary-900, #14532d);
	}

	.rail-archived {
		font-size: 0.625rem;
		font-weight: 600;
		opacity: 0.7;
	}

	.rail-archived.rail-active {
		opacity: 1;
	}

	.rail-icon-btn {
		width: 28px;
		height: 28px;
		display: grid;
		place-items: center;
		border-radius: 0.375rem;
		color: var(--color-surface-500, #737373);
		transition: all 0.15s;
		cursor: pointer;
		border: none;
		background: none;
		padding: 0;
		flex-shrink: 0;
	}

	.rail-icon-btn:hover {
		background: var(--color-surface-200, #e5e5e5);
		color: var(--color-surface-700, #404040);
	}

	.rail-icon-btn.rail-active {
		background: var(--color-primary-100, #dcfce7);
		color: var(--color-primary-900, #14532d);
	}

	/* --- Album resize handle --- */
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
