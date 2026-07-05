<script>
	import '../app.css';
	import { page } from '$app/state';

	let { children } = $props();

	const steps = [
		{ label: 'Load export', match: (p) => p === '/' },
		{ label: 'Curate photos', match: (p) => p.startsWith('/gallery') }
	];
	let activeStep = $derived(steps.findIndex((s) => s.match(page.url.pathname)));
</script>

<div class="flex h-dvh flex-col bg-surface-100">
	<header
		class="sticky top-0 z-30 border-b border-primary-800/40 bg-primary-700 text-primary-50 shadow-sm"
	>
		<div class="mx-auto flex max-w-7xl items-center gap-3 px-3 py-2 sm:px-4">
			<!-- Archers mark: a stylised bow + arrow -->
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
				<p class="truncate text-base font-semibold tracking-tight sm:text-lg">Streamlinify</p>
				<p class="truncate text-xs text-primary-100/80">Archers Network · weekly export curation</p>
			</div>

			<!-- Step indicator -->
			<nav class="ml-auto hidden items-center gap-1.5 md:flex" aria-label="Progress">
				{#each steps as step, i}
					{#if i > 0}
						<span class="h-px w-5 bg-primary-50/30" aria-hidden="true"></span>
					{/if}
					<span
						class="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors"
						class:bg-primary-50={i === activeStep}
						class:text-primary-800={i === activeStep}
						class:text-primary-100={i !== activeStep}
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
		</div>
	</header>

	<main class="mx-auto w-full min-h-0 max-w-7xl flex-1 overflow-y-auto px-3 py-2 sm:px-0 sm:py-5">
		{@render children()}
	</main>

	<footer class="border-t border-surface-300 bg-surface-50">
		<div
			class="mx-auto flex max-w-7xl flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2 text-xs text-surface-600 sm:px-4"
		>
			<svg viewBox="0 0 24 24" class="size-3.5 shrink-0 text-primary-600" fill="none"
				stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
				aria-hidden="true">
				<rect x="3" y="11" width="18" height="11" rx="2" />
				<path d="M7 11V7a5 5 0 0 1 10 0v4" />
			</svg>
			<span>Your export is <strong class="font-semibold text-surface-700">read-only</strong> —
				Streamlinify only writes a filtered copy to <code
					class="rounded bg-surface-200 px-1 py-0.5 font-mono text-[0.7rem] text-surface-800"
					>workspace/ready/</code
				>.</span>
		</div>
	</footer>
</div>
