<script>
	import { trapFocus } from '$lib/focusTrap.js';

	let { result, onClose } = $props();

	const stats = $derived([
		{ label: 'Media files copied', value: result.copied },
		{ label: 'Albums written', value: result.albums_written },
		{ label: 'Orphans skipped', value: result.orphans.length, warn: result.orphans.length > 0 }
	]);
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div
	class="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 backdrop-blur-[1px]"
	onclick={(e) => e.target === e.currentTarget && onClose()}
	onkeydown={(e) => e.key === 'Escape' && onClose()}
	role="dialog"
	aria-modal="true"
	aria-labelledby="build-title"
	tabindex="-1"
	use:trapFocus
>
	<div
		class="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-surface-300 bg-surface-50 shadow-xl"
	>
		<div class="flex items-start gap-3.5 p-6 pb-4">
			<span
				class="grid size-11 shrink-0 place-items-center rounded-full bg-success-100 text-success-700"
				aria-hidden="true"
			>
				<svg viewBox="0 0 24 24" class="size-6" fill="none" stroke="currentColor" stroke-width="2.5"
					stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
			</span>
			<div class="mt-0.5">
				<h2 id="build-title" class="text-lg font-semibold text-surface-900">Ready folder built</h2>
				<p class="mt-0.5 text-sm text-surface-600">
					Saved to <code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
						>workspace/ready/</code
					>. Your original export was not touched.
				</p>
			</div>
		</div>

		<div class="grid grid-cols-3 gap-px border-y border-surface-200 bg-surface-200">
			{#each stats as s}
				<div class="bg-surface-50 px-4 py-3 text-center">
					<p
						class="text-2xl font-semibold tabular-nums"
						class:text-warning-700={s.warn}
						class:text-surface-900={!s.warn}
					>
						{s.value}
					</p>
					<p class="mt-0.5 text-xs text-surface-600">{s.label}</p>
				</div>
			{/each}
		</div>

		<div class="flex-1 overflow-y-auto px-6 py-4">
			<details class="group">
				<summary
					class="flex cursor-pointer list-none items-center gap-1.5 text-sm font-medium text-surface-700 select-none"
				>
					<svg viewBox="0 0 24 24" class="size-4 transition-transform group-open:rotate-90" fill="none"
						stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
						aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>
					Build report
				</summary>
				<pre
					class="mt-2 max-h-56 overflow-auto rounded-lg bg-surface-100 p-3 font-mono text-xs leading-relaxed text-surface-700">{result.summary}</pre>
			</details>
		</div>

		<div class="flex justify-end border-t border-surface-200 px-6 py-4">
			<button
				type="button"
				class="rounded-lg bg-primary-700 px-4 py-2 text-sm font-semibold text-primary-50 shadow-sm transition-colors hover:bg-primary-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
				onclick={onClose}
			>
				Back to gallery
			</button>
		</div>
	</div>
</div>
