<script>
	import '../app.css';
	import { page } from '$app/state';
	import { getSession, markStatsSeen } from '$lib/api.js';
	import { theme, toggleTheme } from '$lib/theme.svelte.js';
	import SettingsMenu from '$lib/components/SettingsMenu.svelte';
	import WorkspaceStats from '$lib/components/WorkspaceStats.svelte';

	let isDark = $derived(theme.mode === 'dark');

	let { children } = $props();

	const steps = [
		{ label: 'Load export', match: (p) => p === '/' },
		{ label: 'Curate photos', match: (p) => p.startsWith('/gallery') }
	];
	let activeStep = $derived(steps.findIndex((s) => s.match(page.url.pathname)));
	// Show the back arrow only once inside a workspace (the gallery); the landing
	// page IS the workspace picker, so there's nothing to go back to there.
	let onGallery = $derived(page.url.pathname.startsWith('/gallery'));

	// The header subtitle shows the active workspace's name. Re-fetch the session
	// whenever the route changes so it stays in sync after opening/switching.
	let displayName = $state('');
	let statsOpen = $state(false);
	$effect(() => {
		const inGallery = page.url.pathname.startsWith('/gallery'); // reactive dep: re-run on navigation
		getSession().then((s) => {
			displayName = s?.loaded ? (s.display_name ?? '') : '';
			// First gallery visit for this workspace: show the stats popup once,
			// and persist the seen-flag so a reopened (or handed-off) week stays quiet.
			if (inGallery && s?.loaded && s.stats_seen === false) {
				statsOpen = true;
				markStatsSeen();
			}
		});
	});
</script>

<div class="flex h-dvh flex-col bg-surface-100">
	<header
		class="sticky top-0 z-30 border-b border-primary-800/40 bg-primary-700 text-primary-50 shadow-sm"
	>
		<div class="flex w-full items-center gap-3 px-3 py-2 sm:px-4">
			{#if onGallery}
				<a
					href="/?switch=1"
					class="grid size-9 shrink-0 place-items-center rounded-lg text-primary-50 transition-colors hover:bg-primary-50/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-50"
					aria-label="Back to workspaces"
					title="Back to workspaces"
				>
					<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2"
						stroke-linecap="round" stroke-linejoin="round">
						<path d="M19 12H5" />
						<path d="m12 19-7-7 7-7" />
					</svg>
				</a>
			{/if}

			<!-- Brand logo -->
			<span
				class="grid size-9 shrink-0 place-items-center rounded-lg bg-primary-50/15"
				aria-hidden="true"
			>
				<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2"
					stroke-linecap="round" stroke-linejoin="round">
					<path d="M4 20 A16 16 0 0 1 20 4" />
					<path d="M4 20 L20 4" />
					<path d="M14 4 H20 V10" />
				</svg>
			</span>

			<div class="min-w-0 leading-tight">
				<p class="font-display truncate text-base font-semibold tracking-tight sm:text-lg">ARCHive Network</p>
				<p class="truncate text-xs text-primary-50/90">
					{displayName || 'From profile archives to production-ready assets'}
				</p>
			</div>

			{#if onGallery && displayName}
				<!-- Workspace stats: scoped to the whole export, so it lives with the
				     workspace name rather than in the per-album gallery toolbar. -->
				<button
					type="button"
					class="grid size-9 shrink-0 place-items-center rounded-lg text-primary-50 transition-colors hover:bg-primary-50/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-50"
					aria-label="Workspace stats"
					title="Workspace stats"
					onclick={() => (statsOpen = true)}
				>
					<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2"
						stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<circle cx="12" cy="12" r="10" />
						<path d="M12 16v-4" />
						<path d="M12 8h.01" />
					</svg>
				</button>
			{/if}

			<div class="ml-auto flex items-center gap-2 sm:gap-3">
				<!-- Step indicator -->
				<nav class="hidden items-center gap-1.5 md:flex" aria-label="Progress">
					{#each steps as step, i}
						{#if i > 0}
							<span class="h-px w-5 bg-primary-50/30" aria-hidden="true"></span>
						{/if}
						<span
							class="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors"
							class:bg-primary-50={i === activeStep}
							class:text-primary-800={i === activeStep}
							class:text-primary-50={i !== activeStep}
							class:opacity-70={i !== activeStep}
							aria-current={i === activeStep ? 'step' : undefined}
						>
							<span
								class="grid size-4 place-items-center rounded-full text-[0.65rem] font-semibold"
								class:bg-primary-700={i === activeStep}
								class:text-primary-50={i === activeStep}
								class:bg-primary-50={i !== activeStep}
								class:text-primary-700={i !== activeStep}
							>{i + 1}</span>
							{step.label}
						</span>
					{/each}
				</nav>

				<!-- Settings (hosts the Dev Mode toggle) -->
				<SettingsMenu />

				<!-- Light / dark toggle -->
				<button
					type="button"
					onclick={toggleTheme}
					class="relative grid size-9 shrink-0 place-items-center rounded-lg text-primary-50 transition-colors hover:bg-primary-50/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-50"
					aria-pressed={isDark}
					aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
					title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
				>
					<!-- Sun (shown in dark mode → click for light) -->
					<svg
						viewBox="0 0 24 24"
						class="theme-icon absolute size-5"
						class:theme-icon-hidden={!isDark}
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<circle cx="12" cy="12" r="4" />
						<path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
					</svg>
					<!-- Moon (shown in light mode → click for dark) -->
					<svg
						viewBox="0 0 24 24"
						class="theme-icon absolute size-5"
						class:theme-icon-hidden={isDark}
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" />
					</svg>
				</button>
			</div>
		</div>
	</header>

	<main class="mx-auto w-full min-h-0 flex-1 overflow-y-auto px-3 py-2 sm:px-1 sm:py-5">
		{@render children()}
	</main>

	{#if statsOpen}
		<WorkspaceStats {displayName} onClose={() => (statsOpen = false)} />
	{/if}

	<!-- theme-toggle icon crossfade lives here (scoped); reduced-motion is
	     honoured by the global rule in app.css that collapses transitions. -->
	<footer class="border-t border-surface-300 bg-surface-50">
		<div
			class="flex w-full flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2 text-xs text-surface-600 sm:px-4"
		>
			<svg viewBox="0 0 24 24" class="size-3.5 shrink-0 text-primary-600 dark:text-primary-400" fill="none"
				stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
				aria-hidden="true">
				<rect x="3" y="11" width="18" height="11" rx="2" />
				<path d="M7 11V7a5 5 0 0 1 10 0v4" />
			</svg>
			<span>Your export is <strong class="font-semibold text-surface-700">read-only</strong> —
				ARCHive Network only writes a filtered copy to <code
					class="rounded bg-surface-200 px-1 py-0.5 font-mono text-[0.7rem] text-surface-800"
					>workspace/ready/</code
				>.</span>
		</div>
	</footer>
</div>

<style>
	/* Crossfade + quarter-turn between the sun and moon glyphs. The two SVGs are
	   stacked (absolute); the inactive one fades and rotates out. Motion is
	   transform/opacity only, and the global prefers-reduced-motion rule collapses
	   it to an instant swap. */
	.theme-icon {
		opacity: 1;
		transform: rotate(0deg) scale(1);
		transition:
			opacity 200ms cubic-bezier(0.22, 1, 0.36, 1),
			transform 200ms cubic-bezier(0.22, 1, 0.36, 1);
	}

	.theme-icon-hidden {
		opacity: 0;
		transform: rotate(-90deg) scale(0.5);
	}
</style>