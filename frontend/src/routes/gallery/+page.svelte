<script>
	import { untrack } from 'svelte';
	import { Toaster, createToaster } from '@skeletonlabs/skeleton-svelte';
	import { build, reveal, thumbUrl, previewUrl, toggle, deselectAll, videoThumbUrl, videoUrl, renameAlbum, resetAlbumName, archiveAlbum, unarchiveAlbum, increaseLimit, undoIncreaseLimit } from '$lib/api.js';
	import { prefetchAlbumThumbs, clearPrefetchCache } from '$lib/imageCache.js';
	import { seedMissingThumbnails, thumbnailMissing } from '$lib/videoThumbs.js';
	import { DEFAULT_SIZE, SIZE_STORAGE_KEY, VIEW_SIZES } from '$lib/viewSizes.js';
	import AlbumList from '$lib/components/AlbumList.svelte';
	import PhotoGrid from '$lib/components/PhotoGrid.svelte';
	import ViewControls from '$lib/components/ViewControls.svelte';
	import PhotoPreview from '$lib/components/PhotoPreview.svelte';
	import VideoPreview from '$lib/components/VideoPreview.svelte';
	import CarouselScrollbar from '$lib/components/CarouselScrollbar.svelte';
	import ContextMenu from '$lib/components/ContextMenu.svelte';
	import BuildSummary from '$lib/components/BuildSummary.svelte';
	import SelectionPanel from '$lib/components/SelectionPanel.svelte';
	import SelectionStrip from '$lib/components/SelectionStrip.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import BuildConfirmDialog from '$lib/components/BuildConfirmDialog.svelte';
	import { dragScrollY } from '$lib/dragScrollY.js';

	let { data } = $props();
	let inventory = $state(untrack(() => data.inventory || {}));
	let activeId = $state(untrack(() => inventory.albums?.[0]?.fb_album_id ?? null));

	$effect(() => {
		if (data.inventory) {
			inventory = data.inventory;
		}
	});
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
	let increaseLimitConfirm = $state({ open: false, album: null });
	let undoLimitConfirm = $state({ open: false, album: null });
	let buildConfirm = $state(false);
	let selectionEnabled = $state(false);
	let albumOpen = $state(true);
	let albumWidth = $state(240);
	let albumDragging = $state(false);
	let albumScrollTop = $state(0);
	let expandedScrollEl = $state(null);
	let collapsedScrollEl = $state(null);

	let dockPosition = $state('right'); // 'right' or 'header'
	let isDockDragging = $state(false);
	let ghostPos = $state({ x: 0, y: 0 });
	let hoverZone = $state(null); // drop zone under the ghost while dragging, or null
	let panelOpen = $state(false);
	let dockStatus = $state(''); // announced to screen readers on dock changes

	const DOCK_LABEL = { right: 'to the right rail', header: 'above the photos' };

	function handleDockDragStart(e) {
		isDockDragging = true;
		hoverZone = null;
		ghostPos = { x: e.clientX, y: e.clientY };
		dockStatus = 'Moving the selection panel. Drop it on a highlighted zone.';

		let frame = 0;
		let pending = null;

		function cleanup() {
			cancelAnimationFrame(frame);
			frame = 0;
			window.removeEventListener('pointermove', onMove);
			window.removeEventListener('pointerup', onUp);
			window.removeEventListener('pointercancel', onCancel);
		}

		function apply() {
			frame = 0;
			if (pending) ghostPos = pending;
			pending = null;
			// Hit-test with JS rather than :hover — touch drags keep events targeted
			// at the tab (implicit pointer capture), so :hover would never fire there.
			const zone = document
				.elementFromPoint(ghostPos.x, ghostPos.y)
				?.closest('[data-drop-zone]');
			hoverZone = zone ? zone.getAttribute('data-drop-zone') : null;
		}

		function onMove(ev) {
			pending = { x: ev.clientX, y: ev.clientY };
			if (!frame) frame = requestAnimationFrame(apply);
		}

		function onUp(ev) {
			isDockDragging = false;
			hoverZone = null;
			const dropZone = document.elementFromPoint(ev.clientX, ev.clientY)?.closest('[data-drop-zone]');
			if (dropZone) dockPosition = dropZone.getAttribute('data-drop-zone');
			dockStatus = `Selection panel docked to ${DOCK_LABEL[dockPosition]}.`;
			cleanup();
		}

		function onCancel() {
			isDockDragging = false;
			hoverZone = null;
			dockStatus = 'Move cancelled.';
			cleanup();
		}

		window.addEventListener('pointermove', onMove);
		window.addEventListener('pointerup', onUp);
		window.addEventListener('pointercancel', onCancel);
	}

	function toggleDock() {
		dockPosition = dockPosition === 'right' ? 'header' : 'right';
		dockStatus = `Selection panel docked to ${DOCK_LABEL[dockPosition]}.`;
	}

	$effect(() => {
		if (albumOpen && expandedScrollEl && expandedScrollEl.scrollTop !== albumScrollTop) {
			expandedScrollEl.scrollTop = albumScrollTop;
		}
		if (!albumOpen && collapsedScrollEl && collapsedScrollEl.scrollTop !== albumScrollTop) {
			collapsedScrollEl.scrollTop = albumScrollTop;
		}
	});

	let editingAlbumId = $state(null);
	let descExpanded = $state(false);
	const toaster = createToaster();

	let gridContainer = $state();
	let lastActiveId = $state(untrack(() => activeId));

	$effect(() => {
		if (activeId !== lastActiveId) {
			lastActiveId = activeId;
			selectionEnabled = false;
			if (gridContainer) {
				gridContainer.scrollTop = 0;
			}
		}
	});

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
		let startX = e.clientX;
		let startW = albumOpen ? albumWidth : 36;

		function onMove(ev) {
			const delta = ev.clientX - startX;
			let newW = startW + delta;

			if (!albumOpen) {
				if (delta > 15) {
					albumOpen = true;
					startX = ev.clientX;
					startW = 140;
					albumWidth = startW;
				}
			} else {
				if (newW < 110) {
					albumOpen = false;
					startX = ev.clientX;
					startW = 36;
				} else {
					albumWidth = Math.max(140, Math.min(400, newW));
				}
			}
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
			onSeeded: (fbid, sizeBytes, timestamp) => {
				thumbVersion = { ...thumbVersion, [fbid]: Date.now() };
				const v = videos.find((x) => x.fbid === fbid);
				if (v) {
					v.video_thumb_tag = 'AUTO';
					if (sizeBytes !== undefined) v.file_size_bytes = sizeBytes;
					if (timestamp !== undefined) v.thumb_timestamp = timestamp;
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
	let albumsToBuild = $derived((inventory.albums ?? []).filter((a) => a.count_selected > 0));
	let totalSelectedVideos = $derived((inventory.videos ?? []).filter((v) => v.selected).length);
	let albumsTotal = $derived((inventory.albums ?? []).length);
	let albumsNoPicks = $derived(albumsTotal - albumsToBuild.length);
	let albumsPickedPct = $derived(albumsTotal ? (albumsToBuild.length / albumsTotal) * 100 : 0);

	// The surface the selection dock mirrors, whichever category is showing. Without
	// this the dock vanishes on Videos/Archive and can't be recovered.
	let panelAlbum = $derived(
		activeAlbum
			? activeAlbum
			: showVideos
				? { name: 'Videos', photos: videos }
				: showArchive
					? { name: 'Archive', photos: archive }
					: null
	);

	// The drag ghost gathers the current surface's picks into a fanned stack under
	// the cursor. Resting fan pose + scattered start pose + stagger, per card.
	const GHOST_FAN = [
		{ fx: -12, fy: 5, fr: -9, sx: -64, sy: -14, sr: -22, d: 0 },
		{ fx: 12, fy: 5, fr: 8, sx: 64, sy: -14, sr: 22, d: 45 },
		{ fx: -5, fy: -2, fr: -4, sx: -44, sy: 30, sr: 14, d: 90 },
		{ fx: 0, fy: 0, fr: 3, sx: 44, sy: 30, sr: -12, d: 135 }
	];
	let dockGhostSelected = $derived(panelAlbum ? panelAlbum.photos.filter((p) => p.selected) : []);
	let ghostCards = $derived(
		(dockGhostSelected.length
			? dockGhostSelected.slice(0, GHOST_FAN.length)
			: [null, null, null]
		).map((photo, i) => ({ key: photo ? photo.fbid : `placeholder-${i}`, photo, ...GHOST_FAN[i] }))
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

	/**
	 * Toggle a photo from whichever surface the selection dock is mirroring. The
	 * dock also serves the Videos category, where there is no `activeAlbum` — the
	 * album path would silently no-op there.
	 */
	async function onPanelToggle(photo) {
		if (showVideos) return onVideoToggle(photo);
		if (!activeAlbum) return; // archive is read-only
		const result = await toggle(activeAlbum.fb_album_id, photo.fbid);
		if (!result.ok && result.cap) return;
		photo.selected = result.selected;
		activeAlbum.count_selected = result.count;
	}

	/** Open the full-screen preview for a tile double-clicked inside the dock. */
	function onPanelDblClick(photo) {
		const arr = activeAlbum ? activeAlbum.photos : showVideos ? videos : archive;
		const index = arr.findIndex((p) => p.fbid === photo.fbid);
		if (index !== -1) openPreviewAt(index);
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

	function onVideoChosen(fbid, sizeBytes, timestamp) {
		thumbVersion = { ...thumbVersion, [fbid]: Date.now() };
		const v = videos.find((x) => x.fbid === fbid);
		if (v) {
			v.video_thumb_tag = 'APPLIED';
			if (sizeBytes !== undefined) v.file_size_bytes = sizeBytes;
			if (timestamp !== undefined) v.thumb_timestamp = timestamp;
		}
	}

	// Right-click a video → choose its thumbnail (replaces "Preview") or open its file.
	function openVideoMenu(video, e) {
		const index = videos.findIndex((v) => v.fbid === video.fbid);
		menu = {
			open: true,
			x: e.clientX,
			y: e.clientY,
			items: [
				{ label: 'Choose Thumbnail', icon: 'preview', onSelect: () => openPreviewAt(index) },
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
					},
					...(album.max_per_album != null && !album.limit_bypassed && album.photos?.length > 10 ? [{
						label: 'Increase Image Limit',
						icon: 'unlock',
						onSelect: () => {
							increaseLimitConfirm = { open: true, album };
						}
					}] : []),
					...(album.limit_bypassed ? [{
						label: 'Undo Image Increase',
						icon: 'lock',
						onSelect: () => {
							undoLimitConfirm = { open: true, album };
						}
					}] : [])
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

<!--
	The top ("header") dock. Rendered from every category header via {@render}, so
	switching to Videos or Archive while docked here doesn't strand the panel with
	no control to bring it back.
-->
{#snippet topDock()}
	{#if isDockDragging && dockPosition !== 'header'}
		<div
			data-drop-zone="header"
			aria-hidden="true"
			class="dock-dropzone mt-4 flex items-center justify-center rounded-2xl border-2 border-dashed border-surface-400 bg-surface-50/80 px-6 py-4"
			class:dock-dropzone-hover={hoverZone === 'header'}
		>
			<svg viewBox="0 0 24 24" class="size-8 text-surface-500" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 22H4a2 2 0 0 1-2-2V6" /><path d="m22 13-1.296-1.296a2.41 2.41 0 0 0-3.408 0L11 18" /><circle cx="12" cy="8" r="2" /><rect width="16" height="16" x="6" y="2" rx="2" /></svg>
		</div>
	{/if}

	{#if !isDockDragging && dockPosition === 'header'}
		<SelectionStrip
			album={panelAlbum}
			bind:open={panelOpen}
			onToggle={onPanelToggle}
			onDockDragStart={handleDockDragStart}
			onDblClick={onPanelDblClick}
		/>
	{/if}
{/snippet}

<!-- Controls that follow the dock wherever it lives: show/hide, and move. -->
{#snippet dockControls()}
	<button
		type="button"
		class="dock-btn"
		class:bg-primary-100={panelOpen}
		class:text-primary-900={panelOpen}
		onclick={() => (panelOpen = !panelOpen)}
		title={panelOpen ? 'Hide selection panel' : 'Show selection panel'}
		aria-pressed={panelOpen}
		aria-label={panelOpen ? 'Hide selection panel' : 'Show selection panel'}
	>
		<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 22H4a2 2 0 0 1-2-2V6" /><path d="m22 13-1.296-1.296a2.41 2.41 0 0 0-3.408 0L11 18" /><circle cx="12" cy="8" r="2" /><rect width="16" height="16" x="6" y="2" rx="2" /></svg>
	</button>
	<button
		type="button"
		class="dock-btn"
		onclick={toggleDock}
		title={dockPosition === 'right' ? 'Move panel above the photos' : 'Move panel to the right rail'}
		aria-label={dockPosition === 'right'
			? 'Move selection panel above the photos'
			: 'Move selection panel to the right rail'}
	>
		{#if dockPosition === 'right'}
			<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18" /></svg>
		{:else}
			<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M15 3v18" /></svg>
		{/if}
	</button>
{/snippet}

<p class="sr-only" role="status" aria-live="polite">{dockStatus}</p>

<div class="flex lg:h-full lg:min-h-0 relative overflow-hidden">
	<!-- Left rail: the album list scrolls on its own; build + counts stay pinned below it. -->
	{#if albumOpen}
		<aside class="album-sidebar mr-5" style="width: {albumWidth}px;">
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

			<!-- Workspace progress: the sidebar's answer to "what's left?" -->
			<div class="album-progress" role="status">
				<div class="album-progress-track" aria-hidden="true">
					<div class="album-progress-fill" style="width: {albumsPickedPct}%"></div>
				</div>
				<span class="album-progress-label tabular-nums">
					{albumsToBuild.length} of {albumsTotal} albums have picks
				</span>
			</div>

			<div
				use:dragScrollY
				bind:this={expandedScrollEl}
				onscroll={(e) => { albumScrollTop = e.currentTarget.scrollTop; }}
				class="rounded-xl border border-surface-300 bg-surface-50 shadow-sm lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
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
					onGroupContextMenu={(groupName, isCollapsed, toggleFn, e) => {
						menu = {
							open: true,
							x: e.clientX,
							y: e.clientY,
							items: [
								{
									label: isCollapsed ? 'Expand Group' : 'Collapse Group',
									icon: 'folder',
									onSelect: toggleFn
								}
							]
						};
					}}
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

			<div class="mt-3 flex flex-col gap-0.5 px-1 text-center text-xs text-surface-600">
				<span class="font-medium tabular-nums">
					{totalSelected} photos · {totalSelectedVideos} videos · ~{totalSelectedMB}MB will be copied
				</span>
				{#if albumsNoPicks > 0}
					<span class="tabular-nums">
						{albumsNoPicks} {albumsNoPicks === 1 ? 'album has' : 'albums have'} no picks yet
					</span>
				{/if}
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
		<aside
			class="album-sidebar-collapsed relative mr-5"
			bind:this={collapsedScrollEl}
			onscroll={(e) => { albumScrollTop = e.currentTarget.scrollTop; }}
		>
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class="album-resize-handle"
				class:active={albumDragging}
				onpointerdown={startAlbumResize}
			></div>

			<div class="album-expand-wrapper">
				<button
					type="button"
					class="album-expand-btn"
					onclick={() => (albumOpen = true)}
					aria-label="Expand album sidebar"
					title="Show albums"
				>
					<svg viewBox="0 0 24 24" class="size-3.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m13 17 5-5-5-5" /><path d="m6 17 5-5-5-5" /></svg>
				</button>
			</div>

			<div class="rail-divider" style="height: 1px; background: var(--color-surface-300, #d4d4d4);"></div>

			<!-- Workspace progress token: albums with picks / total. Clicking expands the list. -->
			<button
				type="button"
				class="rail-progress-btn"
				onclick={() => (albumOpen = true)}
				title="{albumsToBuild.length} of {albumsTotal} albums have picks — show albums"
				aria-label="{albumsToBuild.length} of {albumsTotal} albums have picks. Expand album sidebar."
			>
				<svg viewBox="0 0 28 28" class="size-6" aria-hidden="true">
					<circle cx="14" cy="14" r="11" fill="none" class="rail-progress-track" stroke-width="3.5" />
					<circle
						cx="14" cy="14" r="11" fill="none"
						class="rail-progress-arc"
						stroke-width="3.5"
						stroke-linecap="round"
						stroke-dasharray={2 * Math.PI * 11}
						stroke-dashoffset={2 * Math.PI * 11 * (1 - albumsPickedPct / 100)}
						transform="rotate(-90 14 14)"
					/>
				</svg>
				<span class="rail-progress-count tabular-nums">
					{albumsToBuild.length}<span class="rail-progress-total">/{albumsTotal}</span>
				</span>
			</button>

			{#if videos.length > 0}
				<div class="rail-divider"></div>
				<button
					type="button"
					class="rail-icon-btn"
					class:bg-primary-100={activeId === '__videos__'}
					class:text-primary-900={activeId === '__videos__'}
					class:font-semibold={activeId === '__videos__'}
					class:text-surface-700={activeId !== '__videos__'}
					class:hover:bg-surface-200={activeId !== '__videos__'}
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
					class:bg-primary-100={activeId === '__archive__'}
					class:text-primary-900={activeId === '__archive__'}
					class:font-semibold={activeId === '__archive__'}
					class:text-surface-700={activeId !== '__archive__'}
					class:hover:bg-surface-200={activeId !== '__archive__'}
					onclick={() => { activeId = '__archive__'; editingAlbumId = null; }}
					ondblclick={() => (albumOpen = true)}
					title="Archive"
				>
					<svg viewBox="0 0 24 24" class="size-3.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="4" rx="1" /><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4" /></svg>
				</button>
			{/if}

			<!-- The primary action stays reachable while collapsed. -->
			<div class="rail-build-wrapper">
				<button
					type="button"
					class="rail-build-btn"
					onclick={() => (buildConfirm = true)}
					disabled={building}
					title={building ? 'Building…' : 'Build ready folder'}
					aria-label={building ? 'Building ready folder' : 'Build ready folder'}
				>
					{#if building}
						<span
							class="size-3.5 animate-spin rounded-full border-2 border-primary-200 border-t-primary-50"
							aria-hidden="true"
						></span>
					{:else}
						<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="1.75"
							stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4" /></svg>
					{/if}
				</button>
			</div>
		</aside>
	{/if}

	<!-- Right pane: active album OR the read-only archive. Header stays put; only the
	     photo grid below it scrolls (and only when the pointer is over the grid). -->
	<section class="flex min-w-0 flex-1 flex-col lg:min-h-0 mr-5">
		{#if showArchive}
			<header class="mb-2 shrink-0 pt-1 pb-1">
				<div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
					<div class="flex min-w-0 items-baseline gap-3">
						<h1 class="truncate text-xl font-semibold tracking-tight text-surface-900">Archive</h1>
						<p class="shrink-0 text-sm font-medium tabular-nums text-surface-600">
							{archive.length} set aside
						</p>
					</div>
					<div class="flex items-center gap-1">
						<ViewControls size={gridSize} onSize={setSize} />
						{@render dockControls()}
					</div>
				</div>
				<p class="mt-2 text-sm text-surface-600">
					Photos posted with a news caption (BREAKING, LOOK, …) from Mobile uploads &amp; Photos.
					These are excluded from the build. Right-click to preview or open the file.
				</p>
				{@render topDock()}
			</header>

			{#if archive.length}
				<div class="flex min-h-0 flex-1 gap-2 pl-1">
					<div class="py-2 shrink-0">
						<CarouselScrollbar container={gridContainer} vertical={true} />
					</div>
					<div bind:this={gridContainer} class="flex-1 overflow-y-auto overscroll-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
						<PhotoGrid
							album={{ name: 'Archive', photos: archive }}
							thumb={thumbUrl}
							preview={previewUrl}
							size={gridSize}
							selectable={false}
							selectionEnabled={false}
							onContextMenu={openArchiveMenu}
							onDblClick={(photo) => {
								const index = archive.findIndex((p) => p.fbid === photo.fbid);
								if (index !== -1) openPreviewAt(index);
							}}
						/>
					</div>
				</div>
			{/if}
		{:else if showVideos}
			<header class="mb-2 shrink-0 pt-1 pb-1">
				<div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
					<div class="flex min-w-0 items-center gap-3">
						<h1 class="truncate text-xl font-semibold tracking-tight text-surface-900">Videos</h1>
						<div class="flex shrink-0 items-center gap-2">
							<p class="text-sm font-medium tabular-nums text-surface-600">
								{videos.filter((v) => v.selected).length} / {videos.length} selected
							</p>
							{#if videos.some((v) => v.selected)}
								<button
									type="button"
									class="flex h-[38px] items-center gap-1.5 rounded-lg border border-surface-300 bg-surface-50 px-2.5 text-xs font-medium text-surface-700 transition-colors hover:bg-surface-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
									onclick={onDeselectAll}
								>
									<svg viewBox="0 0 24 24" class="size-3.5 text-surface-500" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
									Deselect All
								</button>
							{/if}
						</div>
					</div>
					<div class="flex items-center gap-1">
						<ViewControls size={gridSize} onSize={setSize} />
						{@render dockControls()}
					</div>
				</div>
				<p class="mt-2 text-sm text-surface-600">
					Videos are kept as thumbnails. Click a video to play it and
					choose the frame, or right-click for “Choose Thumbnail”. They are not auto-kept.
					<br>
					<span class="inline-block rounded bg-warning-900/75 px-1.5 py-0.5 text-[0.6rem] font-semibold text-warning-50">AUTO</span>
					automatically generated from the first frame.
					<br>
					<span class="inline-block rounded bg-primary-900/75 px-1.5 py-0.5 text-[0.6rem] font-semibold text-primary-50">APPLIED</span>
					hand-picked by you.
				</p>
				{@render topDock()}
			</header>

			{#if videos.length}
				<div class="flex min-h-0 flex-1 gap-2 pl-1">
					<div class="py-2 shrink-0">
						<CarouselScrollbar container={gridContainer} vertical={true} />
					</div>
					<div bind:this={gridContainer} class="flex-1 overflow-y-auto overscroll-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
						<PhotoGrid
							album={{ name: 'Videos', photos: videos }}
							thumb={videoTileSrc}
							size={gridSize}
							selectable={true}
							selectionEnabled={true}
							video
							onToggle={onVideoToggle}
							onContextMenu={openVideoMenu}
							onDblClick={(video) => {
								const index = videos.findIndex((v) => v.fbid === video.fbid);
								if (index !== -1) openPreviewAt(index);
							}}
						/>
					</div>
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
								class:text-warning-700={(activeFull && !activeAlbum?.limit_bypassed) || (activeAlbum?.limit_bypassed && activeAlbum.count_selected >= 10 && !activeFull)}
								class:text-error-700={activeFull && activeAlbum?.limit_bypassed}
								class:text-surface-600={!activeFull && !(activeAlbum?.limit_bypassed && activeAlbum.count_selected >= 10)}
							>
								{#if activeCap != null}
									{activeAlbum.count_selected} / {activeCap} selected
								{:else}
									{activeAlbum.count_selected} selected · no limit
								{/if}
							</p>
						</div>
					</div>
					<div class="flex items-center gap-1">
						<ViewControls size={gridSize} onSize={setSize} />
						{@render dockControls()}
					</div>
				</div>

				<!-- Fill bar (capped albums only): how full this album is, at a glance. -->
				{#if activeCap != null}
					<div class="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-200">
						<div
							class="h-full rounded-full transition-[width] duration-300"
							class:bg-warning-500={(activeFull && !activeAlbum?.limit_bypassed) || (activeAlbum?.limit_bypassed && activeAlbum.count_selected >= 10 && !activeFull)}
							class:bg-error-500={activeFull && activeAlbum?.limit_bypassed}
							class:bg-primary-600={!activeFull && !(activeAlbum?.limit_bypassed && activeAlbum.count_selected >= 10)}
							style="width: {(activeAlbum.count_selected / activeCap) * 100}%"
						></div>
					</div>
				{/if}

				{#if activeAlbum.post_timestamp}
					<p class="mt-2 text-xs font-medium text-surface-600 uppercase tracking-wide">
						Date posted on FB: {formatFBDate(activeAlbum.post_timestamp)}
					</p>
				{/if}

				<div class="mt-3 mb-1 flex items-center gap-2">
					<button
						type="button"
						class="flex h-[38px] items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 {selectionEnabled ? 'bg-green-100 border-green-300 text-green-800 shadow-inner' : 'border-surface-300 bg-surface-50 text-surface-700 hover:bg-surface-100'}"
						onclick={() => (selectionEnabled = !selectionEnabled)}
					>
						<svg viewBox="0 0 24 24" class="size-3.5 {selectionEnabled ? 'text-green-700' : 'text-surface-500'}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7" /><path d="m9 11 3 3L22 4" /></svg>
						Enable Selection
					</button>

					{#if activeAlbum.count_selected > 0}
						<button
							type="button"
							class="flex h-[38px] items-center gap-1.5 rounded-lg border border-surface-300 bg-surface-50 px-2.5 text-xs font-medium text-surface-700 transition-colors hover:bg-surface-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
							onclick={onDeselectAll}
						>
							<svg viewBox="0 0 24 24" class="size-3.5 text-surface-500" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
							Deselect All
						</button>
					{/if}
				</div>
				{#if activeAlbum.description}
					{@const isLongDesc = activeAlbum.description.length > 120 || activeAlbum.description.split('\n').length > 2}
					<!-- When the selection strip is docked open right below, the caption squares
					     its bottom corners so the two read as one attached block. -->
					<div
						class="mt-1.5 rounded-md bg-surface-200 px-2.5 py-1.5 text-xs text-surface-600 transition-[border-radius] duration-200"
						class:rounded-b-none={!isDockDragging && dockPosition === 'header' && panelOpen}
					>
						<p class="whitespace-pre-wrap break-words leading-relaxed" class:line-clamp-2={isLongDesc && !descExpanded}>
							{activeAlbum.description}
						</p>
						{#if isLongDesc}
							{#if !descExpanded}
								<button type="button" class="mt-0.5 font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300 dark:hover:text-primary-200 hover:underline" onclick={() => (descExpanded = true)}>
									Read more
								</button>
							{:else}
								<button type="button" class="mt-0.5 font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300 dark:hover:text-primary-200 hover:underline" onclick={() => (descExpanded = false)}>
									See less
								</button>
							{/if}
						{/if}
					</div>
				{/if}

				{@render topDock()}
			</header>

			<div class="flex min-h-0 flex-1 gap-2 pl-1">
				<div class="py-2 shrink-0">
					<CarouselScrollbar container={gridContainer} vertical={true} />
				</div>
				<div bind:this={gridContainer} class="flex-1 overflow-y-auto overscroll-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
					<PhotoGrid
						album={activeAlbum}
						thumb={thumbUrl}
						preview={previewUrl}
						size={gridSize}
						{onToggle}
						onContextMenu={openPhotoMenu}
						onDblClick={(photo) => {
							if (selectionEnabled) return;
							const index = activeAlbum.photos.findIndex((p) => p.fbid === photo.fbid);
							if (index !== -1) openPreviewAt(index);
						}}
						selectable={!isActiveArchived}
						selectionEnabled={selectionEnabled}
						full={activeFull}
					/>
				</div>
			</div>
		{:else}
			<div
				class="grid place-items-center rounded-xl border border-dashed border-surface-300 bg-surface-50 px-6 py-16 text-center"
			>
				<p class="font-medium text-surface-700">No albums in this export</p>
			</div>
		{/if}
	</section>

	{#if isDockDragging}
		{#if dockPosition !== 'right'}
			<div
				data-drop-zone="right"
				aria-hidden="true"
				class="dock-dropzone my-2 mr-5 flex w-64 shrink-0 items-center justify-center rounded-2xl border-2 border-dashed border-surface-400 bg-surface-50/80"
				class:dock-dropzone-hover={hoverZone === 'right'}
			>
				<svg viewBox="0 0 24 24" class="size-8 text-surface-500" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 22H4a2 2 0 0 1-2-2V6" /><path d="m22 13-1.296-1.296a2.41 2.41 0 0 0-3.408 0L11 18" /><circle cx="12" cy="8" r="2" /><rect width="16" height="16" x="6" y="2" rx="2" /></svg>
			</div>
		{/if}

		<div class="drag-ghost-layer pointer-events-none fixed inset-0">
			<div class="ghost-stack absolute" style="left: {ghostPos.x}px; top: {ghostPos.y}px;">
				{#each ghostCards as card, i (card.key)}
					<div
						class="ghost-card"
						style="--fan-x: {card.fx}px; --fan-y: {card.fy}px; --fan-r: {card.fr}deg; --scatter-x: {card.sx}px; --scatter-y: {card.sy}px; --scatter-r: {card.sr}deg; --gather-delay: {card.d}ms; z-index: {i};"
					>
						{#if card.photo}
							<img src={thumbUrl(card.photo.fbid)} alt="" draggable="false" />
						{:else}
							<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="18" height="18" x="3" y="3" rx="2" /><circle cx="9" cy="9" r="2" /><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" /></svg>
						{/if}
					</div>
				{/each}
				{#if dockGhostSelected.length > 0}
					<span class="ghost-badge">{dockGhostSelected.length}</span>
				{/if}
			</div>
		</div>
	{/if}

	{#if !isDockDragging && dockPosition === 'right'}
		<SelectionPanel
			album={panelAlbum}
			bind:open={panelOpen}
			onToggle={onPanelToggle}
			onDockDragStart={handleDockDragStart}
			onDblClick={onPanelDblClick}
		/>
	{/if}
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
{:else if previewOpen && showVideos && videos.length}
	<VideoPreview
		{videos}
		startIndex={previewStart}
		thumbVersionMap={thumbVersion}
		onThumbnailChosen={onVideoChosen}
		onToggle={onVideoToggle}
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

<BuildConfirmDialog
	open={buildConfirm}
	{albumsToBuild}
	defaultMax={inventory.max_per_album ?? 10}
	totalImages={totalSelected}
	totalVideos={totalSelectedVideos}
	totalMB={totalSelectedMB}
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

<ConfirmDialog
	open={increaseLimitConfirm.open}
	title="Increase Image Limit"
	message={increaseLimitConfirm.album
		? `Are you sure you want to increase the image limit for "${increaseLimitConfirm.album.name}"? This will allow you to select up to 15 images.`
		: ''}
	confirmLabel="Yes, increase limit"
	cancelLabel="Cancel"
	onCancel={() => (increaseLimitConfirm = { open: false, album: null })}
	onConfirm={async () => {
		const album = increaseLimitConfirm.album;
		increaseLimitConfirm = { open: false, album: null };
		if (!album) return;
		const res = await increaseLimit(album.fb_album_id);
		if (res.ok) {
			album.max_per_album = res.max_per_album;
			album.limit_bypassed = true;
			toaster.success({ title: 'Success', description: 'Image limit increased.' });
		} else {
			toaster.error({ title: 'Failed', description: res.error });
		}
	}}
/>

<ConfirmDialog
	open={undoLimitConfirm.open}
	title="Undo Image Increase"
	message={undoLimitConfirm.album
		? `Are you sure you want to revert the image limit for "${undoLimitConfirm.album.name}"? This will return the limit to 10 and keep only the first 10 selected images.`
		: ''}
	confirmLabel="Yes, undo increase"
	cancelLabel="Cancel"
	onCancel={() => (undoLimitConfirm = { open: false, album: null })}
	onConfirm={async () => {
		const album = undoLimitConfirm.album;
		undoLimitConfirm = { open: false, album: null };
		if (!album) return;
		const res = await undoIncreaseLimit(album.fb_album_id);
		if (res.ok) {
			album.max_per_album = res.max_per_album;
			album.count_selected = res.count;
			album.limit_bypassed = false;
			const deselected = new Set(res.deselected || []);
			for (const p of album.photos) {
				if (deselected.has(p.fbid)) {
					p.selected = false;
				}
			}
			toaster.success({ title: 'Success', description: 'Image limit reverted.' });
		} else {
			toaster.error({ title: 'Failed', description: res.error });
		}
	}}
/>

<Toaster {toaster}></Toaster>

<style>
	/* --- Selection dock chrome --- */
	.dock-btn {
		display: grid;
		place-items: center;
		margin-left: 0.25rem;
		padding: 0.5rem;
		border-radius: 0.5rem;
		border: none;
		background: none;
		color: var(--color-surface-600);
		cursor: pointer;
		transition: background-color 0.15s, color 0.15s;
	}

	.dock-btn:hover {
		background: var(--color-surface-200);
		color: var(--color-surface-800);
	}

	.dock-btn:focus-visible {
		outline: 2px solid var(--color-primary-600);
		outline-offset: 2px;
	}

	.dock-dropzone {
		position: relative;
		z-index: var(--z-dock-dropzone);
		transition: border-color 0.15s, background-color 0.15s;
	}

	/* The zone under the dragged ghost lights up green-soft — the same drag-over
	   vocabulary as the ingest dropzone (primary-500 border, primary-100 fill). */
	.dock-dropzone-hover {
		border-color: var(--color-primary-500);
		background-color: var(--color-primary-100);
	}

	.dock-dropzone-hover svg {
		color: var(--color-primary-600);
	}

	.drag-ghost-layer {
		z-index: var(--z-drag-ghost);
	}

	/* The cursor-following ghost: the picks gather into a fanned stack, like photos
	   being scooped up to carry. Motion conveys state ("you're holding the
	   selection"), so it runs once at pickup — the stack itself just follows. */
	.ghost-stack {
		transform: translate(-50%, -50%);
	}

	.ghost-card {
		position: absolute;
		left: -28px;
		top: -28px;
		width: 56px;
		height: 56px;
		display: grid;
		place-items: center;
		overflow: hidden;
		border-radius: 0.5rem;
		border: 2px solid var(--color-surface-50);
		background: var(--color-surface-200);
		color: var(--color-surface-500);
		box-shadow: 0 6px 16px oklch(0.16 0.006 172 / 0.28);
		transform: translate(var(--fan-x), var(--fan-y)) rotate(var(--fan-r));
		animation: ghost-gather 0.28s cubic-bezier(0.22, 1, 0.36, 1) both;
		animation-delay: var(--gather-delay);
	}

	.ghost-card img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	@keyframes ghost-gather {
		from {
			opacity: 0;
			transform: translate(var(--scatter-x), var(--scatter-y)) rotate(var(--scatter-r)) scale(1.08);
		}
		to {
			opacity: 1;
			transform: translate(var(--fan-x), var(--fan-y)) rotate(var(--fan-r));
		}
	}

	.ghost-badge {
		position: absolute;
		left: 22px;
		top: -38px;
		z-index: 10;
		background: var(--color-primary-600);
		color: var(--color-primary-contrast-light);
		font-size: 0.6875rem;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
		padding: 2px 7px;
		border-radius: 999px;
		box-shadow: 0 2px 4px oklch(0.16 0.006 172 / 0.2);
		animation: ghost-badge-pop 0.2s cubic-bezier(0.22, 1, 0.36, 1) 0.18s both;
	}

	@keyframes ghost-badge-pop {
		from {
			opacity: 0;
			transform: scale(0.5);
		}
		to {
			opacity: 1;
			transform: scale(1);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.ghost-card,
		.ghost-badge {
			animation: none;
		}
	}

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

	.album-progress {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		padding: 0 0.25rem 0.625rem;
		flex-shrink: 0;
	}

	.album-progress-track {
		height: 4px;
		border-radius: 9999px;
		background: var(--color-surface-300);
		overflow: hidden;
	}

	.album-progress-fill {
		height: 100%;
		border-radius: 9999px;
		background: var(--color-primary-600);
		transition: width 300ms cubic-bezier(0.25, 1, 0.5, 1);
	}

	.album-progress-label {
		font-size: 0.75rem;
		color: var(--color-surface-600);
	}

	@media (prefers-reduced-motion: reduce) {
		.album-progress-fill {
			transition: none;
		}
	}

	/* --- Album sidebar (collapsed icon rail) --- */
	.album-sidebar-collapsed {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		padding-bottom: 0.375rem;
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

	.album-expand-wrapper {
		position: sticky;
		top: 0;
		z-index: 10;
		background: var(--color-surface-50, #fafafa);
		padding-top: 0.375rem;
		width: 100%;
		display: flex;
		justify-content: center;
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
		height: 0.5px;
		background: var(--color-surface-400, #a3a3a3);
		flex-shrink: 0;
		margin: 0.125rem 0;
	}

	.rail-progress-btn {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		width: 28px;
		padding: 0.375rem 0;
		margin: 0.125rem 0;
		border-radius: 0.375rem;
		border: none;
		background: transparent;
		cursor: pointer;
		flex-shrink: 0;
		transition: background-color 0.15s;
	}

	.rail-progress-btn:hover {
		background: var(--color-surface-200);
	}

	.rail-progress-track {
		stroke: var(--color-surface-300);
	}

	.rail-progress-arc {
		stroke: var(--color-primary-600);
		transition: stroke-dashoffset 300ms cubic-bezier(0.25, 1, 0.5, 1);
	}

	.rail-progress-count {
		font-size: 0.625rem;
		font-weight: 600;
		line-height: 1;
		color: var(--color-surface-700);
	}

	.rail-progress-total {
		font-weight: 400;
		color: var(--color-surface-600);
	}

	.rail-build-wrapper {
		position: sticky;
		bottom: 0;
		z-index: 10;
		margin-top: auto;
		width: 100%;
		display: flex;
		justify-content: center;
		padding-top: 0.375rem;
		background: var(--color-surface-50);
	}

	.rail-build-btn {
		display: grid;
		place-items: center;
		width: 28px;
		height: 28px;
		border-radius: 0.5rem;
		border: none;
		background: var(--color-primary-700);
		color: var(--color-primary-50);
		box-shadow: 0 1px 2px oklch(0.23 0.007 171 / 0.06);
		cursor: pointer;
		flex-shrink: 0;
		transition: background-color 0.15s;
	}

	.rail-build-btn:hover:not(:disabled) {
		background: var(--color-primary-800);
	}

	.rail-build-btn:disabled {
		opacity: 0.7;
		cursor: progress;
	}

	.rail-build-btn:focus-visible,
	.rail-progress-btn:focus-visible {
		outline: 2px solid var(--color-primary-600);
		outline-offset: 2px;
	}

	@media (prefers-reduced-motion: reduce) {
		.rail-progress-arc {
			transition: none;
		}
	}

	.rail-icon-btn {
		width: 28px;
		height: 28px;
		display: grid;
		place-items: center;
		border-radius: 0.375rem;
		transition: all 0.15s;
		cursor: pointer;
		border: none;
		background: transparent;
		padding: 0;
		flex-shrink: 0;
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
		background-color: oklch(0.5 0.12 159 / 0.15); /* primary-600 */
	}

	.album-resize-handle.active {
		background-color: oklch(0.5 0.12 159 / 0.2); /* primary-600 */
	}
</style>
