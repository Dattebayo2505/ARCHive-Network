<script>
	import { formatSize } from '$lib/stats.js';

	let { builds = [], onReveal } = $props();

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
</script>

<ul class="divide-y divide-surface-200 overflow-hidden rounded-xl border border-surface-300 bg-surface-50 shadow-sm">
	{#each builds as b (b.id)}
		<li class="flex items-center gap-3 px-4 py-3">
			<span
				class="grid size-9 shrink-0 place-items-center rounded-lg bg-primary-100 text-primary-700"
				aria-hidden="true"
			>
				<svg
					viewBox="0 0 24 24"
					class="size-5"
					fill="none"
					stroke="currentColor"
					stroke-width="1.75"
					stroke-linecap="round"
					stroke-linejoin="round"
				>
					<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
				</svg>
			</span>
			<div class="min-w-0 flex-1">
				<p class="truncate font-medium text-surface-800">{b.display_name}</p>
				<p class="mt-0.5 text-sm tabular-nums text-surface-600">
					{fmtDate(b.built_ts)} · {formatSize(b.size_bytes)}{#if counts(b)} · {counts(b)}{/if}
				</p>
			</div>
			<button
				type="button"
				class="shrink-0 rounded-lg border border-surface-300 bg-surface-50 px-3 py-1.5 text-sm font-medium text-surface-800 shadow-sm transition-colors hover:bg-surface-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
				onclick={() => onReveal?.(b.id)}
			>
				Open in Explorer
			</button>
		</li>
	{/each}
</ul>
