<script>
	import WorkspaceCard from './WorkspaceCard.svelte';

	let { workspaces = [], onOpen, onRemove, onStatLoad, viewMode = 'list' } = $props();
</script>

{#if viewMode === 'list'}
	<ul class="grid grid-cols-1 sm:grid-cols-2 gap-4">
		{#each workspaces as ws (ws.id)}
			<WorkspaceCard {ws} {onOpen} {onRemove} {onStatLoad} {viewMode} />
		{/each}
	</ul>
{:else if viewMode === 'detailed'}
	<div class="rounded-xl border border-surface-300 bg-surface-50 shadow-sm overflow-hidden">
		<!-- Header row -->
		<div class="grid grid-cols-[1fr_auto_auto_auto] gap-4 border-b border-surface-200 bg-surface-100 px-4 py-2 text-xs font-semibold tracking-wider text-surface-500 uppercase">
			<div class="w-full">Workspace</div>
			<div class="w-16 text-right">Albums</div>
			<div class="w-20 text-right">Size</div>
			<div class="w-8"></div>
		</div>
		<ul class="divide-y divide-surface-200">
			{#each workspaces as ws (ws.id)}
				<WorkspaceCard {ws} {onOpen} {onRemove} {onStatLoad} {viewMode} />
			{/each}
		</ul>
	</div>
{:else if viewMode === 'content'}
	<ul class="divide-y divide-surface-200 border-y border-surface-200">
		{#each workspaces as ws (ws.id)}
			<WorkspaceCard {ws} {onOpen} {onRemove} {onStatLoad} {viewMode} />
		{/each}
	</ul>
{/if}
