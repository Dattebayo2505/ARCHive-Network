<script>
	import { tick } from 'svelte';
	import { devMode } from '$lib/devmode.svelte.js';

	let {
		albums, archivedAlbums = [], archiveCount = 0, videosCount = 0, videosSelectedCount = 0,
		activeId, onSelect, onContextMenu, onGroupContextMenu,
		editingId = null, onRename, onCancelRename, onStartRename
	} = $props();

	let editValue = $state('');
	let inputEl = $state();
	let rowEls = $state({});
	let editPos = $state({ top: 0, left: 0, width: 0 });

	let collapsedGroups = $state(new Set());

	let visibleGroups = $derived.by(() => {
		const groups = [];
		for (const a of albums) {
			const g = a.origin || 'Main Albums';
			if (!groups.includes(g)) groups.push(g);
		}
		if (videosCount > 0) groups.push('__videos__');
		if (archiveCount > 0) groups.push('__archive__');
		if (archivedAlbums && archivedAlbums.length > 0) groups.push('Archived Albums');
		// The Dev Mode pane is a sticky group like the others, so it must join this list or the
		// sticky offsets of everything above it drift.
		if (devMode.enabled) groups.push('__dev__');
		return groups;
	});

	function smoothScroll(element, target, duration) {
		const start = element.scrollTop;
		const distance = target - start;
		const startTime = performance.now();

		function step(currentTime) {
			const progress = Math.min((currentTime - startTime) / duration, 1);
			const ease = 1 - Math.pow(1 - progress, 4); // ease-out quart for a fast "spring" look
			element.scrollTop = start + distance * ease;
			if (progress < 1) requestAnimationFrame(step);
		}
		requestAnimationFrame(step);
	}

	function snapTo(e, gIndex, firstId) {
		let targetItem;
		let offset = 0;

		if (firstId && rowEls[firstId]) {
			targetItem = rowEls[firstId];
			offset = (gIndex + 1) * 32;
			onSelect(firstId);
		} else {
			targetItem = e.currentTarget;
			offset = gIndex * 32;
		}

		const scroller = targetItem.closest('.lg\\:overflow-y-auto');
		if (scroller) {
			const scrollerRect = scroller.getBoundingClientRect();
			const itemRect = targetItem.getBoundingClientRect();
			const targetScroll = scroller.scrollTop + (itemRect.top - scrollerRect.top) - offset;
			smoothScroll(scroller, targetScroll, 300); // 300ms snappy animation
		} else {
			targetItem.style.scrollMarginTop = `${offset}px`;
			targetItem.scrollIntoView({ behavior: 'auto', block: 'start' });
		}
	}

	function toggleGroup(group) {
		const next = new Set(collapsedGroups);
		if (next.has(group)) {
			next.delete(group);
		} else {
			next.add(group);
		}
		collapsedGroups = next;
	}

	// When editingId changes to a valid album, seed the input value and auto-focus.
	$effect(() => {
		if (editingId) {
			const album = albums.find((a) => a.fb_album_id === editingId);
			if (album) {
				editValue = album.name;
				tick().then(() => {
					const el = rowEls[editingId];
					if (el) {
						const rect = el.getBoundingClientRect();
						editPos = { top: rect.top, left: rect.left, width: rect.width };
					}
					inputEl?.focus();
					inputEl?.select();
				});
			}
			
			const onScroll = () => {
				const current = albums.find((a) => a.fb_album_id === editingId);
				if (current) commitRename(current);
			};
			window.addEventListener('scroll', onScroll, true);
			window.addEventListener('resize', onScroll);
			return () => {
				window.removeEventListener('scroll', onScroll, true);
				window.removeEventListener('resize', onScroll);
			};
		}
	});

	function commitRename(album) {
		const trimmed = editValue.trim();
		if (trimmed && trimmed !== album.name) {
			onRename?.(album, trimmed);
		} else {
			onCancelRename?.();
		}
	}

	function cancelRename() {
		onCancelRename?.();
	}

	function onInputKeydown(e, album) {
		if (e.key === 'Enter') {
			e.preventDefault();
			commitRename(album);
		} else if (e.key === 'Escape') {
			e.preventDefault();
			cancelRename();
		}
	}
</script>

{#snippet albumItem(a, i, isArchived = false)}
	{@const capped = a.max_per_album != null}
	{@const full = capped && a.count_selected >= a.max_per_album}
	{@const active = a.fb_album_id === activeId}
	{@const editing = a.fb_album_id === editingId}
	{@const bypassedFull = full && a.limit_bypassed}
	{@const progressPct = capped ? Math.min((a.count_selected / a.max_per_album) * 100, 100) : 0}
	<div class="relative overflow-hidden rounded-lg">
		<button
			bind:this={rowEls[a.fb_album_id]}
			type="button"
			class="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
			class:bg-primary-100={active || editing}
			class:text-primary-900={active || editing}
			class:font-semibold={active || editing}
			class:text-surface-700={!active && !editing}
			class:hover:bg-surface-200={!active && !editing}
			onclick={() => onSelect(a.fb_album_id)}
			ondblclick={() => onStartRename?.(a.fb_album_id)}
			oncontextmenu={(e) => {
				e.preventDefault();
				onContextMenu?.(a, e);
			}}
			aria-current={active ? 'true' : undefined}
		>
			<span class="truncate" class:opacity-0={editing}>{a.name}</span>
			{#if !isArchived}
			<span
				class="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums"
				class:opacity-0={editing}
				class:bg-warning-200={(full && !bypassedFull) || (a.limit_bypassed && a.count_selected >= 10 && !full)}
				class:text-warning-900={(full && !bypassedFull) || (a.limit_bypassed && a.count_selected >= 10 && !full)}
				class:bg-error-200={bypassedFull}
				class:text-error-900={bypassedFull}
				class:bg-primary-200={!full && a.count_selected > 0 && !(a.limit_bypassed && a.count_selected >= 10)}
				class:text-primary-900={!full && a.count_selected > 0 && !(a.limit_bypassed && a.count_selected >= 10)}
				class:bg-surface-200={a.count_selected === 0}
				class:text-surface-600={a.count_selected === 0}
				title={capped
					? full
						? bypassedFull
							? 'Album is full'
							: `Complete — at the ${a.max_per_album}-photo cap`
						: `${a.count_selected} of ${a.max_per_album} selected`
					: `${a.count_selected} selected · no limit`}
			>
				{#if full}
					{#if bypassedFull}
						<svg viewBox="0 0 24 24" class="size-3" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="1" y="11" width="14" height="11" rx="2" /><path d="M4 11V7a4 4 0 0 1 8 0v4" /><rect x="9" y="11" width="14" height="11" rx="2" /><path d="M12 11V7a4 4 0 0 1 8 0v4" /></svg>
					{:else}
						<svg viewBox="0 0 24 24" class="size-3" fill="none" stroke="currentColor" stroke-width="2.5"
							stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
					{/if}
				{/if}
				{#if capped}{a.count_selected}/{a.max_per_album}{:else}{a.count_selected}{/if}
			</span>
			{/if}
		</button>
		{#if editing}
			<div
				class="fixed z-[100] flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs bg-primary-100 text-primary-900 shadow-xl border border-primary-700"
				style="top: {editPos.top}px; left: {editPos.left}px; min-width: {editPos.width}px; max-width: 90vw;"
			>
				<!-- svelte-ignore a11y_autofocus -->
				<input
					bind:this={inputEl}
					bind:value={editValue}
					type="text"
					class="album-rename-input"
					onkeydown={(e) => onInputKeydown(e, a)}
					onblur={() => commitRename(a)}
					aria-label="Rename album"
				/>
			</div>
		{/if}
		{#if capped && !isArchived}
			<div
				class="absolute bottom-0 left-0 h-[3px] transition-[width] duration-300"
				class:bg-warning-500={(full && !bypassedFull) || (a.limit_bypassed && a.count_selected >= 10 && !full)}
				class:bg-error-500={bypassedFull}
				class:bg-primary-600={!full && !(a.limit_bypassed && a.count_selected >= 10)}
				style="width: {progressPct}%"
			></div>
		{/if}
	</div>
{/snippet}

<nav aria-label="Albums" class="flex flex-col gap-1 p-2">
	<p class="font-display px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-surface-600">
		Albums <span class="font-normal text-surface-600">· {albums.length}</span>
	</p>

	{#each albums as a, i (a.fb_album_id)}
		{@const groupName = a.origin || 'Main Albums'}
		{@const prevGroupName = i > 0 ? (albums[i - 1].origin || 'Main Albums') : null}
		{#if groupName !== prevGroupName}
			{@const gIndex = visibleGroups.indexOf(groupName)}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class="sticky z-10 bg-surface-50 flex w-full items-center justify-between pl-2 pr-1 text-left rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 group hover:bg-surface-100 transition-colors h-[32px] select-none"
				style="top: {gIndex * 32}px; bottom: {(visibleGroups.length - 1 - gIndex) * 32}px;"
				ondblclick={(e) => snapTo(e, gIndex, a.fb_album_id)}
				oncontextmenu={(e) => {
					e.preventDefault();
					onGroupContextMenu?.(groupName, collapsedGroups.has(groupName), () => toggleGroup(groupName), e);
				}}
			>
				<span class="font-display text-[0.65rem] font-semibold uppercase tracking-wide text-surface-400 group-hover:text-surface-600 transition-colors flex-1 cursor-pointer">
					{groupName}
				</span>
				<button 
					type="button"
					class="p-1 rounded text-surface-400 hover:bg-surface-200 hover:text-surface-600 transition-colors outline-none focus-visible:ring-2 focus-visible:ring-primary-600"
					onclick={(e) => { e.stopPropagation(); toggleGroup(groupName); }}
					aria-expanded={!collapsedGroups.has(groupName)}
					title={collapsedGroups.has(groupName) ? "Expand" : "Collapse"}
				>
					<svg viewBox="0 0 24 24" class="size-3.5 transition-transform duration-200" class:-rotate-90={collapsedGroups.has(groupName)} fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<polyline points="6 9 12 15 18 9"></polyline>
					</svg>
				</button>
			</div>
		{/if}
		{#if !collapsedGroups.has(groupName)}
			{@render albumItem(a, i)}
		{/if}
	{/each}

	{#if videosCount > 0}
		{@const active = activeId === '__videos__'}
		{@const gIndex = visibleGroups.indexOf('__videos__')}
		<div class="my-1 h-px bg-surface-300"></div>
		<button
			type="button"
			class="sticky z-10 flex items-center gap-2 rounded-lg px-2.5 text-left text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 h-[32px]"
			style="top: {gIndex * 32}px; bottom: {(visibleGroups.length - 1 - gIndex) * 32}px;"
			class:bg-surface-50={!active}
			class:bg-primary-100={active}
			class:text-primary-900={active}
			class:font-semibold={active}
			class:text-surface-700={!active}
			class:hover:bg-surface-200={!active}
			onclick={() => onSelect('__videos__')}
			aria-current={active ? 'true' : undefined}
			title="Videos are always kept — pick a still frame to represent each one."
		>
			<svg viewBox="0 0 24 24" class="size-4 shrink-0" fill="none" stroke="currentColor"
				stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="5" width="14" height="14" rx="2" /><path d="m16 10 6-3v10l-6-3z" /></svg>
			<span class="truncate">Videos</span>
			<span class="ml-auto shrink-0 rounded-full bg-surface-200 px-2 py-0.5 text-xs font-medium tabular-nums text-surface-600">{videosSelectedCount}</span>
		</button>
	{/if}

	{#if archiveCount > 0}
		{@const active = activeId === '__archive__'}
		{@const gIndex = visibleGroups.indexOf('__archive__')}
		<div class="my-1 h-px bg-surface-300"></div>
		<button
			type="button"
			class="sticky z-10 flex items-center gap-2 rounded-lg px-2.5 text-left text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 h-[32px]"
			style="top: {gIndex * 32}px; bottom: {(visibleGroups.length - 1 - gIndex) * 32}px;"
			class:bg-surface-50={!active}
			class:bg-primary-100={active}
			class:text-primary-900={active}
			class:font-semibold={active}
			class:text-surface-700={!active}
			class:hover:bg-surface-200={!active}
			onclick={() => onSelect('__archive__')}
			aria-current={active ? 'true' : undefined}
			title="News-caption photos set aside — excluded from the build."
		>
			<svg viewBox="0 0 24 24" class="size-4 shrink-0" fill="none" stroke="currentColor"
				stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="4" rx="1" /><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4" /></svg>
			<span class="truncate">Archive</span>
			<span class="ml-auto shrink-0 rounded-full bg-surface-200 px-2 py-0.5 text-xs font-medium tabular-nums text-surface-600">{archiveCount}</span>
		</button>
	{/if}


	{#if archivedAlbums && archivedAlbums.length > 0}
		{@const groupName = 'Archived Albums'}
		{@const gIndex = visibleGroups.indexOf('Archived Albums')}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="sticky z-10 bg-surface-50 flex w-full items-center justify-between pl-2 pr-1 text-left rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 group hover:bg-surface-100 transition-colors h-[32px] select-none"
			style="top: {gIndex * 32}px; bottom: {(visibleGroups.length - 1 - gIndex) * 32}px;"
			ondblclick={(e) => snapTo(e, gIndex, archivedAlbums[0]?.fb_album_id)}
			oncontextmenu={(e) => {
				e.preventDefault();
				onGroupContextMenu?.(groupName, collapsedGroups.has(groupName), () => toggleGroup(groupName), e);
			}}
		>
			<span class="font-display text-[0.65rem] font-semibold uppercase tracking-wide text-surface-400 group-hover:text-surface-600 transition-colors flex-1 cursor-pointer">
				{groupName}
			</span>
			<button 
				type="button"
				class="p-1 rounded text-surface-400 hover:bg-surface-200 hover:text-surface-600 transition-colors outline-none focus-visible:ring-2 focus-visible:ring-primary-600"
				onclick={(e) => { e.stopPropagation(); toggleGroup(groupName); }}
				aria-expanded={!collapsedGroups.has(groupName)}
				title={collapsedGroups.has(groupName) ? "Expand" : "Collapse"}
			>
				<svg viewBox="0 0 24 24" class="size-3.5 transition-transform duration-200" class:-rotate-90={collapsedGroups.has(groupName)} fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
					<polyline points="6 9 12 15 18 9"></polyline>
				</svg>
			</button>
		</div>
		{#if !collapsedGroups.has(groupName)}
			{#each archivedAlbums as a, i (a.fb_album_id)}
				{@render albumItem(a, i, true)}
			{/each}
		{/if}
	{/if}

	{#if devMode.enabled}
		{@const active = activeId === '__dev__'}
		{@const gIndex = visibleGroups.indexOf('__dev__')}
		<div class="my-1 h-px bg-surface-300"></div>
		<button
			type="button"
			class="sticky z-10 flex h-[32px] items-center gap-2 rounded-lg px-2.5 text-left text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
			style="top: {gIndex * 32}px; bottom: {(visibleGroups.length - 1 - gIndex) * 32}px;"
			class:bg-surface-50={!active}
			class:bg-primary-100={active}
			class:text-primary-900={active}
			class:font-semibold={active}
			class:text-surface-700={!active}
			class:hover:bg-surface-200={!active}
			onclick={() => onSelect('__dev__')}
			aria-current={active ? 'true' : undefined}
			title="Load this build into PostgreSQL and inspect the rows."
		>
			<svg
				viewBox="0 0 24 24"
				class="size-4 shrink-0"
				fill="none"
				stroke="currentColor"
				stroke-width="1.75"
				stroke-linecap="round"
				stroke-linejoin="round"
				aria-hidden="true"
			>
				<ellipse cx="12" cy="5" rx="8" ry="3" />
				<path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3" />
			</svg>
			<span class="truncate">Dev Mode</span>
		</button>
	{/if}

</nav>

<style>
	.album-rename-input {
		flex: 1;
		min-width: 0;
		background: transparent;
		border: none;
		border-radius: 0;
		outline: none;
		font: inherit;
		font-size: inherit;
		line-height: inherit;
		color: inherit;
		padding: 0;
		field-sizing: content;
	}
</style>
