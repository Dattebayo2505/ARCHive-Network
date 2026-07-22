<script>
	import { slide } from 'svelte/transition';
	import { prefersReducedMotion } from 'svelte/motion';
	import { formatSize } from '$lib/stats.js';

	let { builds = [], onReveal, onDelete } = $props();

	// Which row is showing its confirm band. Only ever one — opening a second closes
	// the first, so two rows can never both be armed to delete.
	let confirmingId = $state(null);

	function fmtDate(ts) {
		return new Date(ts * 1000).toLocaleDateString(undefined, {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	}

	// "8 photos · 2 videos · 3 albums" — videos omitted when zero. null counts (a build
	// that failed to parse) collapse the whole segment.
	function counts(b) {
		if (b.photos == null) return null;
		const parts = [`${b.photos} photo${b.photos === 1 ? '' : 's'}`];
		if (b.videos) parts.push(`${b.videos} video${b.videos === 1 ? '' : 's'}`);
		parts.push(`${b.albums} album${b.albums === 1 ? '' : 's'}`);
		return parts.join(' · ');
	}

	// Arming the row unmounts the trash button that had focus, so hand focus to Cancel:
	// the safe choice, and it keeps Escape reachable without a keyboard trap.
	function takeFocus(node) {
		node.focus();
	}
</script>

<ul class="divide-y divide-surface-200 overflow-hidden rounded-xl border border-surface-300 bg-surface-50 shadow-sm">
	{#each builds as b (b.id)}
		<li
			class="group relative block overflow-hidden transition-colors hover:bg-surface-100 focus-within:bg-surface-100"
			out:slide={{ duration: prefersReducedMotion.current ? 0 : 180 }}
		>
			{#if confirmingId !== b.id}
				<div class="flex items-center justify-between gap-4 px-4 py-3">
					<button
						type="button"
						class="flex min-w-0 flex-1 flex-col items-start rounded text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2"
						title="Open in Explorer"
						onclick={() => onReveal?.(b.id)}
					>
						<!-- The row *is* the open action, so its accessible name has to start with a
						     verb; the visible content alone would announce as a bare folder name. -->
						<span class="sr-only">Open in Explorer:</span>
						<span class="w-full truncate font-medium text-surface-900">{b.display_name}</span>
						<span class="mt-0.5 w-full truncate text-xs tabular-nums text-surface-600">
							{fmtDate(b.built_ts)} · {formatSize(b.size_bytes)}{#if counts(b)} · {counts(b)}{/if}
						</span>
					</button>
					<div class="flex shrink-0 items-center justify-end pl-3">
						<button
							type="button"
							class="rounded p-1.5 text-surface-500 opacity-0 transition-opacity hover:bg-error-50 hover:text-error-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-error-600 focus-within:opacity-100 group-hover:opacity-100"
							title="Delete ready folder"
							aria-label="Delete the ready folder {b.display_name}"
							onclick={(e) => {
								e.stopPropagation();
								confirmingId = b.id;
							}}
						>
							<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
						</button>
					</div>
				</div>
			{:else}
				<!-- One step, not the workspace's two: deleting a build costs only the copy on
				     disk. The export and this workspace's picks survive, so it rebuilds. -->
				<div
					class="flex items-center justify-between gap-4 bg-error-50 px-4 py-3"
					role="alertdialog"
					aria-label="Delete {b.display_name}?"
					tabindex="-1"
					onkeydown={(e) => {
						if (e.key === 'Escape') confirmingId = null;
					}}
				>
					<div class="min-w-0 flex-1">
						<p class="text-sm font-medium text-error-900">Delete ready folder?</p>
						<p class="truncate text-xs text-error-800">
							Deletes the built copy on disk. Your picks are kept.
						</p>
					</div>
					<div class="flex shrink-0 gap-2">
						<button
							type="button"
							class="rounded-lg border border-surface-300 bg-surface-50 px-3 py-1.5 text-xs font-medium text-surface-700 hover:bg-surface-100"
							use:takeFocus
							onclick={() => (confirmingId = null)}
						>
							Cancel
						</button>
						<button
							type="button"
							class="rounded-lg bg-error-700 px-3 py-1.5 text-xs font-semibold text-error-50 hover:bg-error-800"
							onclick={() => {
								confirmingId = null;
								onDelete?.(b.id);
							}}
						>
							Delete folder
						</button>
					</div>
				</div>
			{/if}
		</li>
	{/each}
</ul>
