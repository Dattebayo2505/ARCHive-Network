<script>
	import { trapFocus } from '$lib/focusTrap.js';
	import { getInventory } from '$lib/api.js';
	import { computeStats, formatDateRange, formatSize } from '$lib/stats.js';

	let { displayName = '', onClose } = $props();

	// The dialog owns its data: fetch the inventory when it opens so the header
	// button works from any gallery surface without threading page state up.
	let inventory = $state(null);
	let failed = $state(false);
	$effect(() => {
		getInventory()
			.then((inv) => {
				if (inv === null) failed = true;
				else inventory = inv;
			})
			.catch(() => (failed = true));
	});

	let stats = $derived(inventory ? computeStats(inventory) : null);

	function albumsValue(s) {
		let v = `${s.mainAlbums}`;
		if (s.derivedAlbums) v += ` (+${s.derivedAlbums} derived)`;
		return v;
	}

	let rows = $derived(
		stats
			? [
					{ label: 'Date range', value: formatDateRange(stats.dateRange) ?? '—' },
					{
						label: 'Albums',
						value: albumsValue(stats),
						note: stats.archivedAlbums
							? `${stats.archivedAlbums} more ${stats.archivedAlbums === 1 ? 'album is' : 'albums are'} archived and excluded from the build`
							: null
					},
					{ label: 'Photos', value: stats.totalPhotos.toLocaleString() },
					{ label: 'Videos', value: stats.totalVideos.toLocaleString() },
					{
						label: 'Exported media size',
						value: formatSize(stats.mediaBytes),
						note: 'photos on disk — videos and .json metadata not counted'
					}
				]
			: []
	);
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div
	class="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 backdrop-blur-[1px]"
	onclick={(e) => e.target === e.currentTarget && onClose()}
	onkeydown={(e) => e.key === 'Escape' && onClose()}
	role="dialog"
	aria-modal="true"
	aria-labelledby="workspace-stats-title"
	tabindex="-1"
	use:trapFocus
>
	<div
		class="flex max-h-[85vh] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-surface-300 bg-surface-50 shadow-xl"
	>
		<div class="flex items-start gap-3.5 p-6 pb-4">
			<span
				class="grid size-11 shrink-0 place-items-center rounded-full bg-primary-100 text-primary-700"
				aria-hidden="true"
			>
				<svg viewBox="0 0 24 24" class="size-6" fill="none" stroke="currentColor" stroke-width="2"
					stroke-linecap="round" stroke-linejoin="round">
					<circle cx="12" cy="12" r="10" />
					<path d="M12 16v-4" />
					<path d="M12 8h.01" />
				</svg>
			</span>
			<div class="mt-0.5 min-w-0 flex-1">
				<h2 id="workspace-stats-title" class="text-lg font-semibold text-surface-900">
					Workspace stats
				</h2>
				<p class="mt-0.5 truncate text-sm text-surface-600">
					{displayName || 'This export at a glance'}
				</p>
			</div>
			<button
				type="button"
				class="grid size-9 shrink-0 place-items-center rounded-lg text-surface-500 transition-colors hover:bg-surface-200 hover:text-surface-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
				aria-label="Close"
				title="Close"
				onclick={onClose}
			>
				<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2"
					stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
					<path d="M18 6 6 18M6 6l12 12" />
				</svg>
			</button>
		</div>

		<div class="border-t border-surface-200 px-6 py-2">
			{#if failed}
				<p class="py-4 text-sm text-surface-600">
					Couldn't load the workspace's details. Close this and try again from the ⓘ button in the
					header.
				</p>
			{:else if !stats}
				<!-- Skeleton rows while the inventory loads. -->
				{#each Array(6) as _, i (i)}
					<div
						class="flex items-center justify-between gap-4 py-3"
						class:border-t={i > 0}
						class:border-surface-200={i > 0}
					>
						<div class="h-3.5 w-24 animate-pulse rounded bg-surface-200"></div>
						<div class="h-3.5 w-32 animate-pulse rounded bg-surface-200"></div>
					</div>
				{/each}
			{:else}
				{#each rows as row, i (row.label)}
					<div class="py-3" class:border-t={i > 0} class:border-surface-200={i > 0}>
						<div class="flex items-baseline justify-between gap-4">
							<p class="text-sm text-surface-600">{row.label}</p>
							<p class="text-right text-sm font-medium tabular-nums text-surface-900">
								{row.value}
							</p>
						</div>
						{#if row.note}
							<p class="mt-0.5 text-right text-xs text-surface-600">{row.note}</p>
						{/if}
					</div>
				{/each}
			{/if}
		</div>
	</div>
</div>
