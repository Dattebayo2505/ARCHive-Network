<script>
	import { devMode } from '$lib/devmode.svelte.js';

	let open = $state(false);
	let root;

	// Close on outside click / Escape — a popover that traps you is worse than no popover.
	function onWindowPointerDown(event) {
		if (open && root && !root.contains(event.target)) open = false;
	}

	function onWindowKeydown(event) {
		if (open && event.key === 'Escape') open = false;
	}
</script>

<svelte:window onpointerdown={onWindowPointerDown} onkeydown={onWindowKeydown} />

<div class="relative" bind:this={root}>
	<!-- The header is brand-green in both themes, so this matches the theme toggle exactly. -->
	<button
		type="button"
		onclick={() => (open = !open)}
		class="relative grid size-9 shrink-0 place-items-center rounded-lg text-primary-50 transition-colors hover:bg-primary-50/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-50 {open
			? 'bg-primary-50/15'
			: ''}"
		aria-expanded={open}
		aria-haspopup="true"
		aria-label="Settings"
		title="Settings"
	>
		<svg
			viewBox="0 0 24 24"
			class="size-5"
			fill="none"
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"
		>
			<circle cx="12" cy="12" r="3" />
			<path
				d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.14.63.63 1.12 1.26 1.26H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"
			/>
		</svg>
	</button>

	{#if open}
		<!-- Surface tokens only: dark mode inverts the ramp for free. Never a `dark:` override. -->
		<div
			class="absolute right-0 z-50 mt-2 w-72 rounded-xl border border-surface-300 bg-surface-50 p-4 shadow-xl"
			role="dialog"
			aria-label="Settings"
		>
			<p class="mb-3 text-xs font-semibold tracking-wide text-surface-500 uppercase">Settings</p>

			<label class="flex cursor-pointer items-start justify-between gap-3">
				<span class="min-w-0">
					<span class="block text-sm font-medium text-surface-900">Dev Mode</span>
					<span class="mt-0.5 block text-xs leading-snug text-surface-500">
						Load the build into PostgreSQL and inspect the rows. Adds a Dev Mode entry to the
						album rail.
					</span>
				</span>
				<input
					type="checkbox"
					class="mt-0.5 size-4 shrink-0 accent-primary-600"
					checked={devMode.enabled}
					onchange={() => devMode.toggle()}
				/>
			</label>
		</div>
	{/if}
</div>
