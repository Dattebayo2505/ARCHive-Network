<script>
	import { trapFocus } from '$lib/focusTrap.js';
	import ConfirmDialog from './ConfirmDialog.svelte';
	
	let {
		open = false,
		albumsToBuild = [],
		totalImages = 0,
		totalVideos = 0,
		totalMB = "0.00",
		onConfirm,
		onCancel
	} = $props();

	function handleKey(e) {
		if (e.key === 'Escape') onCancel?.();
	}
	
	function handleBackdrop(e) {
		if (e.target === e.currentTarget) onCancel?.();
	}

	let albumsExpanded = $state(false);
	let finalConfirmOpen = $state(false);

	function formatFBDate(isoString) {
		if (!isoString) return '-';
		const date = new Date(isoString);
		return new Intl.DateTimeFormat('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		}).format(date);
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-[80] grid place-items-center bg-surface-950/50 p-4 backdrop-blur-[1px]"
		onclick={handleBackdrop}
		onkeydown={handleKey}
		role="dialog"
		aria-modal="true"
		aria-labelledby="confirm-title"
		tabindex="-1"
		use:trapFocus
	>
		<div class="w-full max-w-2xl overflow-hidden rounded-2xl border border-surface-300 bg-surface-50 shadow-xl animate-in flex flex-col max-h-[90vh]">
			<!-- Header -->
			<div class="flex items-start gap-3.5 p-6 pb-4 shrink-0">
				<span
					class="grid size-11 shrink-0 place-items-center rounded-full bg-primary-100 text-primary-700"
					aria-hidden="true"
				>
					<svg viewBox="0 0 24 24" class="size-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4" />
					</svg>
				</span>
				<div class="mt-0.5 w-full">
					<h2 id="confirm-title" class="text-lg font-semibold text-surface-900">Build ready folder</h2>
					<p class="mt-1 text-sm leading-relaxed text-surface-600">Review your selection before building the ready directory.</p>
				</div>
			</div>

			<!-- Body summary -->
			<div class="px-6 pb-4 shrink-0">
				<div class="grid grid-cols-4 gap-2 rounded-xl bg-surface-100 p-4 border border-surface-200 shadow-sm">
					<div class="flex flex-col items-center text-center">
						<span class="text-xl font-bold text-surface-900">{albumsToBuild.length}</span>
						<span class="text-[0.65rem] font-bold uppercase tracking-wider text-surface-500 mt-0.5">Albums</span>
					</div>
					<div class="flex flex-col items-center text-center border-l border-surface-200">
						<span class="text-xl font-bold text-surface-900">{totalImages}</span>
						<span class="text-[0.65rem] font-bold uppercase tracking-wider text-surface-500 mt-0.5">Images</span>
					</div>
					<div class="flex flex-col items-center text-center border-l border-surface-200">
						<span class="text-xl font-bold text-surface-900">{totalVideos}</span>
						<span class="text-[0.65rem] font-bold uppercase tracking-wider text-surface-500 mt-0.5">Videos</span>
					</div>
					<div class="flex flex-col items-center text-center border-l border-surface-200">
						<span class="text-xl font-bold text-surface-900">{totalMB}</span>
						<span class="text-[0.65rem] font-bold uppercase tracking-wider text-surface-500 mt-0.5">Est. MB</span>
					</div>
				</div>
			</div>

			<!-- Albums Dropdown -->
			{#if albumsToBuild.length > 0}
				<div class="px-6 pb-6 flex-1 min-h-0 flex flex-col">
					<button 
						type="button" 
						class="flex w-full items-center justify-between rounded-lg border border-surface-200 bg-surface-50 px-4 py-2.5 text-sm font-medium text-surface-700 shadow-sm hover:bg-surface-100 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
						onclick={() => (albumsExpanded = !albumsExpanded)}
					>
						<span class="flex items-center gap-2">
							<svg viewBox="0 0 24 24" class="size-4 text-surface-500" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<rect width="18" height="18" x="3" y="3" rx="2" />
								<path d="M3 9h18" />
							</svg>
							Selected Albums to Build
						</span>
						<svg viewBox="0 0 24 24" class="size-4 text-surface-500 transition-transform {albumsExpanded ? 'rotate-180' : ''}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<path d="m6 9 6 6 6-6"/>
						</svg>
					</button>

					{#if albumsExpanded}
						<div class="mt-2 flex-1 min-h-0 overflow-hidden rounded-lg border border-surface-200 bg-white flex flex-col shadow-inner animate-in-slide">
							<!-- Fixed Header (outside scroll) -->
							<div class="border-b border-surface-200 bg-surface-100 overflow-y-hidden" style="scrollbar-gutter: stable;">
								<div class="grid grid-cols-[1fr_6rem_6rem_6rem] px-3 py-2 text-[0.65rem] font-bold uppercase tracking-wider text-surface-500">
									<div class="pr-4">Album Name</div>
									<div class="text-center border-l border-surface-200">Image Count</div>
									<div class="text-center border-l border-surface-200">Date</div>
									<div class="text-center border-l border-surface-200">Size</div>
								</div>
							</div>
							<!-- Scrollable Container -->
							<div class="max-h-64 overflow-y-auto overscroll-contain pb-1" style="scrollbar-gutter: stable;">
								{#each albumsToBuild as album, i}
									<div class="grid grid-cols-[1fr_6rem_6rem_6rem] items-center px-3 py-2 text-sm text-surface-700 {i !== albumsToBuild.length - 1 ? 'border-b border-surface-100' : ''} hover:bg-surface-50 transition-colors">
										<div class="truncate pr-4 font-medium" title={album.name}>{album.name}</div>
										<div class="text-center border-l border-surface-100 flex items-center justify-center">
											{#if album.max_per_album != null && album.count_selected >= album.max_per_album}
												<span class="inline-block rounded bg-warning-900/75 px-1.5 py-0.5 text-[0.6rem] font-semibold text-warning-50">MAX</span>
											{:else}
												<span class="text-surface-500 text-xs tabular-nums">{album.count_selected}</span>
											{/if}
										</div>
										<div class="text-center border-l border-surface-100 text-surface-500 text-xs">
											{formatFBDate(album.post_timestamp)}
										</div>
										<div class="text-center border-l border-surface-100 text-surface-500 tabular-nums text-xs">
											{((album.photos.filter(p => p.selected).reduce((sum, p) => sum + (p.file_size_bytes || 0), 0)) / (1024*1024)).toFixed(1)} MB
										</div>
									</div>
								{/each}
							</div>
						</div>
					{/if}
				</div>
			{/if}

			<!-- Action buttons -->
			<div class="flex justify-end gap-3 border-t border-surface-200 px-6 py-4 bg-surface-50 shrink-0">
				<button
					type="button"
					class="rounded-lg px-4 py-2 text-sm font-medium text-surface-700 transition-colors hover:bg-surface-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
					onclick={() => onCancel?.()}
				>
					Cancel
				</button>
				<button
					type="button"
					class="rounded-lg px-4 py-2 text-sm font-semibold text-primary-50 bg-primary-700 hover:bg-primary-800 shadow-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
					onclick={() => (finalConfirmOpen = true)}
				>
					Yes, build it
				</button>
			</div>
		</div>
	</div>
{/if}

<ConfirmDialog
	open={finalConfirmOpen}
	title="Confirm Build"
	message="Are you sure you want to proceed with building the ready folder? This process will organize all selected media."
	confirmLabel="Confirm"
	cancelLabel="Cancel"
	destructive={true}
	onCancel={() => (finalConfirmOpen = false)}
	onConfirm={() => {
		finalConfirmOpen = false;
		onConfirm?.();
	}}
/>

<style>
	.animate-in {
		animation: dialog-enter 0.15s ease-out;
	}
	
	.animate-in-slide {
		animation: slide-down 0.2s ease-out;
		transform-origin: top;
	}

	@keyframes dialog-enter {
		from {
			opacity: 0;
			transform: scale(0.95) translateY(4px);
		}
		to {
			opacity: 1;
			transform: scale(1) translateY(0);
		}
	}
	
	@keyframes slide-down {
		from {
			opacity: 0;
			transform: scaleY(0.95);
		}
		to {
			opacity: 1;
			transform: scaleY(1);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.animate-in, .animate-in-slide {
			animation: none;
		}
	}
</style>
