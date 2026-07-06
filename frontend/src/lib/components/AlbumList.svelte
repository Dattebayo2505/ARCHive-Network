<script>
	import { tick } from 'svelte';

	let {
		albums, nonAlbumCount, archiveCount = 0, videosCount = 0,
		activeId, onSelect, onContextMenu,
		editingId = null, onRename, onCancelRename, onStartRename
	} = $props();

	let editValue = $state('');
	let inputEl = $state();
	let rowEls = $state({});
	let editPos = $state({ top: 0, left: 0, width: 0 });

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

<nav aria-label="Albums" class="flex flex-col gap-1">
	<p class="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-surface-500">
		Albums <span class="font-normal text-surface-400">· {albums.length}</span>
	</p>

	{#each albums as a, i (a.fb_album_id)}
		{#if a.origin && a.origin !== albums[i - 1]?.origin}
			<p class="px-2 pb-0.5 pt-2 text-[0.65rem] font-semibold uppercase tracking-wide text-surface-400">
				{a.origin}
			</p>
		{/if}
		{@const capped = a.max_per_album != null}
		{@const full = capped && a.count_selected >= a.max_per_album}
		{@const active = a.fb_album_id === activeId}
		{@const editing = a.fb_album_id === editingId}
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
				<span
					class="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums"
					class:opacity-0={editing}
					class:bg-warning-200={full}
					class:text-warning-900={full}
					class:bg-primary-200={!full && a.count_selected > 0}
					class:text-primary-900={!full && a.count_selected > 0}
					class:bg-surface-200={a.count_selected === 0}
					class:text-surface-600={a.count_selected === 0}
					title={capped
						? full
							? 'Album is full'
							: `${a.count_selected} of ${a.max_per_album} selected`
						: `${a.count_selected} selected · no limit`}
				>
					{#if full}
						<svg viewBox="0 0 24 24" class="size-3" fill="none" stroke="currentColor" stroke-width="2.5"
							stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
					{/if}
					{#if capped}{a.count_selected}/{a.max_per_album}{:else}{a.count_selected}{/if}
				</span>
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
					<span
						class="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums"
						class:bg-warning-200={full}
						class:text-warning-900={full}
						class:bg-primary-200={!full && a.count_selected > 0}
						class:text-primary-900={!full && a.count_selected > 0}
						class:bg-surface-200={a.count_selected === 0}
						class:text-surface-600={a.count_selected === 0}
					>
						{#if capped}{a.count_selected}/{a.max_per_album}{:else}{a.count_selected}{/if}
					</span>
				</div>
			{/if}
			{#if capped}
				<div
					class="absolute bottom-0 left-0 h-[3px] transition-[width] duration-300"
					style="width: {progressPct}%; background-color: #1b5e20;"
					aria-hidden="true"
				></div>
			{/if}
		</div>
	{/each}

	{#if videosCount > 0}
		{@const active = activeId === '__videos__'}
		<div class="my-1 h-px bg-surface-300"></div>
		<button
			type="button"
			class="flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
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
			<span class="ml-auto shrink-0 rounded-full bg-surface-200 px-2 py-0.5 text-xs font-medium tabular-nums text-surface-600">{videosCount}</span>
		</button>
	{/if}

	{#if archiveCount > 0}
		{@const active = activeId === '__archive__'}
		<div class="my-1 h-px bg-surface-300"></div>
		<button
			type="button"
			class="flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
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

	<div class="my-1 h-px bg-surface-300"></div>

	<div
		class="flex items-center gap-2 rounded-lg px-2.5 py-2 text-xs text-surface-500"
		title="All non-album photos are kept automatically and can't be deselected."
	>
		<svg viewBox="0 0 24 24" class="size-4 shrink-0 text-surface-400" fill="none" stroke="currentColor"
			stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
		<span>Auto-kept</span>
		<span class="ml-auto shrink-0 tabular-nums text-surface-400">{nonAlbumCount}</span>
	</div>
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
