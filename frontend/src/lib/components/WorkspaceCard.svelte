<script>
	import { onMount } from 'svelte';
	import { getWorkspaceStats } from '$lib/api.js';
	import { formatSize } from '$lib/stats.js';

	let { ws, onOpen, onRemove, onStatLoad, viewMode = 'list' } = $props();

	let confirming = $state(false);
	let superConfirming = $state(false);
	let stats = $state(null);
	let loadingStats = $state(true);

	onMount(async () => {
		stats = await getWorkspaceStats(ws.id);
		loadingStats = false;
		if (onStatLoad && stats) onStatLoad(ws.id, stats);
	});

	function fmtDateRange(start, end) {
		if (!start || !end) return '';
		const opts = { month: 'short', day: 'numeric', year: 'numeric' };
		const s = new Intl.DateTimeFormat('en-US', opts).format(new Date(start * 1000));
		const e = new Intl.DateTimeFormat('en-US', opts).format(new Date(end * 1000));
		return s === e ? s : `${s} – ${e}`;
	}

	function fmtOpened(ts) {
		if (!ts) return '';
		try {
			return new Intl.DateTimeFormat('en-US', {
				month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
			}).format(new Date(ts * 1000));
		} catch {
			return '';
		}
	}
</script>

{#if viewMode === 'list'}
	<li class="group relative flex flex-col overflow-hidden rounded-xl border border-surface-300 bg-surface-50 shadow-sm transition-all hover:border-surface-400 hover:shadow-md">
		<button
			type="button"
			class="flex flex-1 flex-col items-start p-4 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
			onclick={() => onOpen(ws.id)}
		>
			<p class="truncate font-semibold text-surface-900 w-full pr-8">{ws.display_name}</p>

			{#if ws.last_opened_ts}
				<p class="mt-0.5 text-xs text-surface-500">
					Opened {fmtOpened(ws.last_opened_ts)}
				</p>
			{/if}

			<div class="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-xs text-surface-600">
				{#if loadingStats}
					<div class="h-4 w-16 animate-pulse rounded bg-surface-200"></div>
					<div class="h-4 w-16 animate-pulse rounded bg-surface-200"></div>
				{:else if stats}
					{#if stats.dateStart && stats.dateEnd}
						<div class="flex items-center gap-1.5" title="Date range">
							<svg viewBox="0 0 24 24" class="size-3.5 shrink-0 text-surface-400" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>
							{fmtDateRange(stats.dateStart, stats.dateEnd)}
						</div>
					{/if}
					<div class="flex items-center gap-1.5" title="Total albums">
						<svg viewBox="0 0 24 24" class="size-3.5 shrink-0 text-surface-400" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><path d="M3 9h18M9 21V9"/></svg>
						{stats.albumCount} {stats.albumCount === 1 ? 'album' : 'albums'}
					</div>
					<div class="flex items-center gap-1.5" title="Total size">
						<svg viewBox="0 0 24 24" class="size-3.5 shrink-0 text-surface-400" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
						{formatSize(stats.mediaBytes)}
					</div>
				{:else}
					<p class="text-xs italic text-surface-400">Stats unavailable</p>
				{/if}
			</div>
		</button>

		<div class="absolute right-3 top-3 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
			<button
				type="button"
				class="grid size-8 place-items-center rounded-lg bg-surface-50 text-surface-400 shadow-sm ring-1 ring-surface-200 transition-colors hover:bg-error-50 hover:text-error-700 hover:ring-error-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-error-600"
				title="Remove Workspace"
				onclick={(e) => { e.stopPropagation(); confirming = true; superConfirming = false; }}
			>
				<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
			</button>
		</div>

		{#if confirming && !superConfirming}
			<div class="border-t border-error-200 bg-error-50 p-4" role="alertdialog">
				<p class="text-sm font-medium text-error-900">Remove workspace?</p>
				<p class="mt-1 text-xs text-error-800">
					{#if ws.managed}This will delete the unzipped export and all saved selections.{:else}This removes <span class="font-medium">{ws.display_name}</span> from the list. Its files on disk are left untouched.{/if}
				</p>
				<div class="mt-3 flex gap-2">
					<button type="button" class="rounded-lg bg-error-700 px-3 py-1.5 text-xs font-semibold text-error-50 hover:bg-error-800" onclick={() => { if (ws.managed) superConfirming = true; else { onRemove(ws.id, ws.managed); confirming = false; } }}>{ws.managed ? 'Delete permanently' : 'Remove from list'}</button>
					<button type="button" class="rounded-lg border border-surface-300 bg-surface-50 px-3 py-1.5 text-xs font-medium text-surface-700 hover:bg-surface-100" onclick={() => (confirming = false)}>Cancel</button>
				</div>
			</div>
		{/if}

		{#if superConfirming}
			<div class="border-t border-error-300 bg-error-100 p-4" role="alertdialog">
				<p class="flex items-center gap-2 text-sm font-bold text-error-900">
					<svg viewBox="0 0 24 24" class="size-4.5 shrink-0 text-error-700" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
					Are you absolutely sure?
				</p>
				<p class="mt-1 text-xs text-error-800">This will permanently destroy the exported files. This action cannot be undone.</p>
				<div class="mt-3 flex gap-2">
					<button type="button" class="rounded-lg bg-error-800 px-3 py-1.5 text-xs font-bold text-error-50 hover:bg-error-900" onclick={() => { onRemove(ws.id, ws.managed); confirming = false; superConfirming = false; }}>Yes, delete everything</button>
					<button type="button" class="rounded-lg border border-error-300 bg-error-50 px-3 py-1.5 text-xs font-medium text-error-900 hover:bg-error-200" onclick={() => { superConfirming = false; confirming = false; }}>Cancel</button>
				</div>
			</div>
		{/if}
	</li>
{:else if viewMode === 'detailed'}
	<li class="group relative block overflow-hidden transition-colors hover:bg-surface-50/70 focus-within:bg-surface-50/70">
		{#if !confirming}
			<div class="grid grid-cols-[1fr_auto_auto_auto] items-center gap-4 px-4 py-3">
				<button type="button" class="flex flex-col items-start text-left min-w-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2 rounded" onclick={() => onOpen(ws.id)}>
					<span class="truncate font-medium text-surface-900 w-full">{ws.display_name}</span>
					{#if stats?.dateStart && stats?.dateEnd}
						<span class="text-xs text-surface-500 mt-0.5 truncate w-full">{fmtDateRange(stats.dateStart, stats.dateEnd)}</span>
					{:else if loadingStats}
						<div class="h-3 w-32 animate-pulse rounded bg-surface-200 mt-1"></div>
					{/if}
				</button>
				<div class="w-16 text-right text-sm tabular-nums text-surface-600">
					{#if loadingStats}<span class="animate-pulse bg-surface-200 text-transparent rounded">000</span>{:else if stats}{stats.albumCount}{/if}
				</div>
				<div class="w-20 text-right text-sm tabular-nums text-surface-600">
					{#if loadingStats}<span class="animate-pulse bg-surface-200 text-transparent rounded">00 MB</span>{:else if stats}{formatSize(stats.mediaBytes)}{/if}
				</div>
				<div class="w-8 flex justify-end">
					<button type="button" class="opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100 rounded text-surface-400 hover:text-error-600 hover:bg-error-50 p-1.5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-error-600" title="Remove Workspace" onclick={(e) => { e.stopPropagation(); confirming = true; superConfirming = false; }}>
						<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
					</button>
				</div>
			</div>
		{:else if confirming && !superConfirming}
			<div class="flex items-center justify-between gap-4 bg-error-50 px-4 py-3" role="alertdialog">
				<div class="min-w-0 flex-1">
					<p class="text-sm font-medium text-error-900">Remove workspace?</p>
					<p class="truncate text-xs text-error-800">
						{#if ws.managed}Deletes unzipped export & selections.{:else}Removes from list, keeps files.{/if}
					</p>
				</div>
				<div class="flex shrink-0 gap-2">
					<button type="button" class="rounded-lg border border-surface-300 bg-surface-50 px-3 py-1.5 text-xs font-medium text-surface-700 hover:bg-surface-100" onclick={() => (confirming = false)}>Cancel</button>
					<button type="button" class="rounded-lg bg-error-700 px-3 py-1.5 text-xs font-semibold text-error-50 hover:bg-error-800" onclick={() => { if (ws.managed) superConfirming = true; else { onRemove(ws.id, ws.managed); confirming = false; } }}>{ws.managed ? 'Delete permanently' : 'Remove'}</button>
				</div>
			</div>
		{:else if superConfirming}
			<div class="flex items-center justify-between gap-4 bg-error-100 px-4 py-3" role="alertdialog">
				<div class="min-w-0 flex-1">
					<p class="flex items-center gap-2 text-sm font-bold text-error-900">
						<svg viewBox="0 0 24 24" class="size-4 shrink-0 text-error-700" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
						Absolutely sure?
					</p>
					<p class="truncate text-xs text-error-800">Action cannot be undone.</p>
				</div>
				<div class="flex shrink-0 gap-2">
					<button type="button" class="rounded-lg border border-error-300 bg-error-50 px-3 py-1.5 text-xs font-medium text-error-900 hover:bg-error-200" onclick={() => { superConfirming = false; confirming = false; }}>Cancel</button>
					<button type="button" class="rounded-lg bg-error-800 px-3 py-1.5 text-xs font-bold text-error-50 hover:bg-error-900" onclick={() => { onRemove(ws.id, ws.managed); confirming = false; superConfirming = false; }}>Yes, delete</button>
				</div>
			</div>
		{/if}
	</li>
{:else if viewMode === 'content'}
	<li class="group relative block overflow-hidden transition-colors hover:bg-surface-50 focus-within:bg-surface-50">
		{#if !confirming}
			<div class="flex items-center justify-between gap-4 px-4 py-2.5">
				<button type="button" class="flex items-center gap-3 text-left min-w-0 flex-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2 rounded" onclick={() => onOpen(ws.id)}>
					<span class="truncate font-medium text-surface-900">{ws.display_name}</span>
					{#if ws.last_opened_ts}
						<span class="truncate text-xs text-surface-500">Opened {fmtOpened(ws.last_opened_ts)}</span>
					{/if}
				</button>
				<div class="flex shrink-0 items-center justify-end pl-3">
					<button type="button" class="opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100 rounded text-surface-400 hover:text-error-600 hover:bg-error-50 p-1.5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-error-600" title="Remove Workspace" onclick={(e) => { e.stopPropagation(); confirming = true; superConfirming = false; }}>
						<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
					</button>
				</div>
			</div>
		{:else if confirming && !superConfirming}
			<div class="flex items-center justify-between gap-4 bg-error-50 px-4 py-2.5" role="alertdialog">
				<div class="min-w-0 flex-1 flex items-center gap-3">
					<span class="text-sm font-medium text-error-900">Remove workspace?</span>
					<span class="truncate text-xs text-error-800 hidden sm:inline">
						{#if ws.managed}Deletes unzipped export & selections.{:else}Removes from list, keeps files.{/if}
					</span>
				</div>
				<div class="flex shrink-0 gap-2">
					<button type="button" class="rounded-lg border border-surface-300 bg-surface-50 px-3 py-1.5 text-xs font-medium text-surface-700 hover:bg-surface-100" onclick={() => (confirming = false)}>Cancel</button>
					<button type="button" class="rounded-lg bg-error-700 px-3 py-1.5 text-xs font-semibold text-error-50 hover:bg-error-800" onclick={() => { if (ws.managed) superConfirming = true; else { onRemove(ws.id, ws.managed); confirming = false; } }}>{ws.managed ? 'Delete permanently' : 'Remove'}</button>
				</div>
			</div>
		{:else if superConfirming}
			<div class="flex items-center justify-between gap-4 bg-error-100 px-4 py-2.5" role="alertdialog">
				<div class="min-w-0 flex-1 flex items-center gap-3">
					<span class="flex items-center gap-2 text-sm font-bold text-error-900">
						<svg viewBox="0 0 24 24" class="size-4 shrink-0 text-error-700" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
						Absolutely sure?
					</span>
					<span class="truncate text-xs text-error-800 hidden sm:inline">Action cannot be undone.</span>
				</div>
				<div class="flex shrink-0 gap-2">
					<button type="button" class="rounded-lg border border-error-300 bg-error-50 px-3 py-1.5 text-xs font-medium text-error-900 hover:bg-error-200" onclick={() => { superConfirming = false; confirming = false; }}>Cancel</button>
					<button type="button" class="rounded-lg bg-error-800 px-3 py-1.5 text-xs font-bold text-error-50 hover:bg-error-900" onclick={() => { onRemove(ws.id, ws.managed); confirming = false; superConfirming = false; }}>Yes, delete</button>
				</div>
			</div>
		{/if}
	</li>
{/if}
