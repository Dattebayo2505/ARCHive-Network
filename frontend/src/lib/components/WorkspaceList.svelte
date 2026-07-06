<script>
	let { workspaces = [], onOpen, onRemove } = $props();
	// id of the card currently showing its delete-confirm row, or null.
	let confirmingId = $state(null);

	function fmt(ts) {
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

<ul class="space-y-2">
	{#each workspaces as ws (ws.id)}
		<li class="rounded-xl border border-surface-300 bg-surface-50 shadow-sm">
			<div class="flex items-center gap-3 p-3">
				<button
					type="button"
					class="min-w-0 flex-1 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
					onclick={() => onOpen(ws.id)}
				>
					<p class="truncate font-medium text-surface-900">{ws.display_name}</p>
					<p class="truncate text-xs text-surface-500" title={ws.raw_name}>
						{ws.raw_name}{#if ws.last_opened_ts} · opened {fmt(ws.last_opened_ts)}{/if}
					</p>
				</button>
				{#if confirmingId !== ws.id}
					<button
						type="button"
						class="shrink-0 rounded-lg px-2.5 py-1.5 text-sm font-medium text-surface-500 transition-colors hover:bg-error-50 hover:text-error-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-error-600"
						onclick={() => (confirmingId = ws.id)}
					>
						Remove
					</button>
				{/if}
			</div>

			{#if confirmingId === ws.id}
				<div class="border-t border-error-200 bg-error-50 p-3" role="alertdialog" aria-live="polite">
					<p class="text-sm text-error-800">
						{#if ws.managed}
							This permanently deletes the unzipped export and all saved selections for
							<span class="font-medium">{ws.display_name}</span>. This cannot be undone.
						{:else}
							This removes <span class="font-medium">{ws.display_name}</span> from the list.
							Its files on disk are left untouched.
						{/if}
					</p>
					<div class="mt-2 flex gap-2">
						<button
							type="button"
							class="rounded-lg bg-error-700 px-3 py-1.5 text-sm font-semibold text-error-50 transition-colors hover:bg-error-800"
							onclick={() => { onRemove(ws.id, ws.managed); confirmingId = null; }}
						>
							{ws.managed ? 'Delete permanently' : 'Remove from list'}
						</button>
						<button
							type="button"
							class="rounded-lg border border-surface-300 bg-surface-50 px-3 py-1.5 text-sm font-medium text-surface-700 transition-colors hover:bg-surface-100"
							onclick={() => (confirmingId = null)}
						>
							Cancel
						</button>
					</div>
				</div>
			{/if}
		</li>
	{/each}
</ul>
