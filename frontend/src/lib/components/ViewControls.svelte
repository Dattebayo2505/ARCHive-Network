<script>
	import { VIEW_SIZES } from '$lib/viewSizes.js';

	let { size, onSize, onOpenPreview, previewDisabled = false } = $props();

	let btns = $state([]);

	// Arrow-key roving within the segmented control (WAI-ARIA radiogroup pattern):
	// Left/Up = previous, Right/Down = next, Home/End = ends. Selection follows focus.
	function onKey(e, i) {
		const last = VIEW_SIZES.length - 1;
		let next = null;
		if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = i < last ? i + 1 : 0;
		else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = i > 0 ? i - 1 : last;
		else if (e.key === 'Home') next = 0;
		else if (e.key === 'End') next = last;
		if (next === null) return;
		e.preventDefault();
		onSize(VIEW_SIZES[next].id);
		btns[next]?.focus();
	}
</script>

<div class="flex flex-wrap items-center justify-end gap-2">
	<div
		class="flex items-center gap-2 rounded-lg border border-surface-300 bg-surface-50 py-1 pr-1 pl-2.5"
	>
		<span class="text-xs font-medium text-surface-500 select-none" id="size-label">Size</span>
		<div
			class="flex items-center gap-0.5"
			role="radiogroup"
			aria-labelledby="size-label"
		>
			{#each VIEW_SIZES as s, i (s.id)}
				{@const active = s.id === size}
				<button
					bind:this={btns[i]}
					type="button"
					role="radio"
					aria-checked={active}
					aria-label={`${s.name} thumbnails`}
					title={`${s.name} thumbnails`}
					tabindex={active ? 0 : -1}
					class="grid h-7 min-w-[1.85rem] place-items-center rounded-md px-1.5 text-xs font-semibold tabular-nums transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
					class:bg-primary-700={active}
					class:text-primary-50={active}
					class:shadow-sm={active}
					class:text-surface-600={!active}
					class:hover:bg-surface-200={!active}
					onclick={() => onSize(s.id)}
					onkeydown={(e) => onKey(e, i)}
				>
					{s.label}
				</button>
			{/each}
		</div>
	</div>

	<button
		type="button"
		class="flex h-9 items-center gap-1.5 rounded-lg border border-surface-300 bg-surface-50 px-3 text-sm font-medium text-surface-700 transition-colors hover:bg-surface-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
		onclick={onOpenPreview}
		disabled={previewDisabled}
	>
		<svg
			viewBox="0 0 24 24"
			class="size-4 text-primary-600"
			fill="none"
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"
		>
			<path d="M15 3h6v6" />
			<path d="M9 21H3v-6" />
			<path d="M21 3l-7 7" />
			<path d="M3 21l7-7" />
		</svg>
		Preview
	</button>
</div>
