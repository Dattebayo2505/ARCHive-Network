<script>
	import { browse } from '$lib/api.js';
	import { trapFocus } from '$lib/focusTrap.js';

	let { open = false, onClose, onChoose, onChooseZip } = $props();

	let path = $state(null);
	let parent = $state(null);
	let dirs = $state([]);
	let files = $state([]);
	let drives = $state([]);
	let isExport = $state(false);
	let loading = $state(false);
	let error = $state('');
	let pathInput = $state('');

	async function load(target) {
		loading = true;
		error = '';
		const res = await browse(target);
		loading = false;
		if (!res.ok) {
			error = res.error;
			return;
		}
		path = res.path;
		parent = res.parent;
		dirs = res.dirs;
		files = res.files ?? [];
		isExport = res.is_export;
		drives = res.drives ?? [];
		pathInput = res.path;
	}

	function go() {
		const t = pathInput.trim();
		if (t) load(t);
	}

	function driveActive(d) {
		return path && path.slice(0, 2).toUpperCase() === d.slice(0, 2).toUpperCase();
	}

	// Load home directory the first time the dialog opens.
	let started = $state(false);
	$effect(() => {
		if (open && !started) {
			started = true;
			load(null);
		}
		if (!open) started = false;
	});

	function onKey(e) {
		if (e.key === 'Escape') onClose?.();
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 backdrop-blur-[1px]"
		onclick={(e) => e.target === e.currentTarget && onClose?.()}
		onkeydown={onKey}
		role="dialog"
		aria-modal="true"
		aria-label="Choose export folder"
		tabindex="-1"
		use:trapFocus
	>
		<div
			class="flex max-h-[82vh] w-full max-w-lg flex-col overflow-hidden rounded-xl border border-surface-300 bg-surface-50 shadow-xl"
		>
			<header class="flex items-center gap-3 border-b border-surface-200 px-5 py-3.5">
				<h2 class="text-base font-semibold text-surface-900">Choose export folder</h2>
				<button
					type="button"
					class="ml-auto grid size-7 place-items-center rounded-md text-surface-500 transition-colors hover:bg-surface-200 hover:text-surface-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
					onclick={() => onClose?.()}
					aria-label="Close"
				>
					<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2"
						stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
				</button>
			</header>

			<!-- Drives + editable address bar -->
			<div class="space-y-2 border-b border-surface-200 bg-surface-100 px-4 py-3">
				{#if drives.length > 1}
					<div class="flex flex-wrap items-center gap-1.5">
						<span class="text-xs font-medium text-surface-600">Drives</span>
						{#each drives as d (d)}
							<button
								type="button"
								class="rounded-md px-2 py-1 font-mono text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
								class:bg-primary-200={driveActive(d)}
								class:text-primary-900={driveActive(d)}
								class:bg-surface-200={!driveActive(d)}
								class:text-surface-700={!driveActive(d)}
								class:hover:bg-surface-300={!driveActive(d)}
								onclick={() => load(d)}
							>
								{d.replace(/\\$/, '')}
							</button>
						{/each}
					</div>
				{/if}

				<div class="flex items-center gap-2">
					<div
						class="flex flex-1 items-center gap-2 rounded-lg border border-surface-300 bg-surface-50 px-2.5 focus-within:border-primary-500 focus-within:ring-2 focus-within:ring-primary-500/30"
					>
						<svg viewBox="0 0 24 24" class="size-4 shrink-0 text-surface-500" fill="none"
							stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
						</svg>
						<input
							class="min-w-0 flex-1 bg-transparent py-2 font-mono text-xs text-surface-800 placeholder:text-surface-600 focus:outline-none"
							bind:value={pathInput}
							onkeydown={(e) => e.key === 'Enter' && (e.preventDefault(), go())}
							placeholder="Type or paste a folder path…"
							spellcheck="false"
							autocomplete="off"
							aria-label="Folder path"
						/>
					</div>
					<button
						type="button"
						class="shrink-0 rounded-lg border border-surface-300 bg-surface-50 px-3 py-2 text-sm font-medium text-surface-800 transition-colors hover:bg-surface-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
						onclick={go}>Go</button
					>
				</div>
			</div>

			<!-- Directory list -->
			<div class="min-h-[11rem] flex-1 overflow-y-auto p-2">
				{#if error}
					<p
						class="mx-1 mb-1 flex items-start gap-1.5 rounded-md bg-error-50 px-3 py-2 text-sm text-error-700"
						role="alert"
					>
						<svg viewBox="0 0 24 24" class="mt-px size-4 shrink-0" fill="none" stroke="currentColor"
							stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" /></svg>
						{error}
					</p>
				{/if}
				{#if loading}
					<ul class="space-y-1.5 p-1" aria-hidden="true">
						{#each Array(6) as _}
							<li class="h-9 animate-pulse rounded-md bg-surface-200"></li>
						{/each}
					</ul>
				{:else}
					<ul class="space-y-0.5">
						{#if parent}
							<li>
								<button
									type="button"
									class="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-surface-600 transition-colors hover:bg-surface-200 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary-600"
									onclick={() => load(parent)}
								>
									<svg viewBox="0 0 24 24" class="size-4 shrink-0" fill="none" stroke="currentColor"
										stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m18 15-6-6-6 6" /></svg>
									<span class="font-medium">Up one level</span>
								</button>
							</li>
						{/if}
						{#each dirs as dir (dir.path)}
							<li>
								<button
									type="button"
									class="group flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-surface-800 transition-colors hover:bg-primary-50 dark:hover:bg-primary-100 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary-600"
									onclick={() => load(dir.path)}
								>
									<svg viewBox="0 0 24 24" class="size-4 shrink-0 text-primary-600 dark:text-primary-400" fill="none"
										stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
										<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
									</svg>
									<span class="truncate">{dir.name}</span>
									{#if dir.is_export}
										<span
											class="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full bg-primary-100 px-2 py-0.5 text-[0.7rem] font-medium text-primary-800"
										>
											<svg viewBox="0 0 24 24" class="size-3" fill="none" stroke="currentColor"
												stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
											Export
										</span>
									{/if}
									<svg viewBox="0 0 24 24"
										class="size-4 shrink-0 text-surface-400 opacity-0 transition-opacity group-hover:opacity-100"
										class:ml-auto={!dir.is_export} fill="none" stroke="currentColor" stroke-width="2"
										stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6" /></svg>
								</button>
							</li>
						{/each}
						{#each files as file (file.path)}
							<li>
								<button
									type="button"
									class="group flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-surface-800 transition-colors hover:bg-primary-50 dark:hover:bg-primary-100 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary-600"
									onclick={() => onChooseZip?.(file.path)}
								>
									<svg viewBox="0 0 24 24" class="size-4 shrink-0 text-surface-500" fill="none"
										stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
										<path d="M4 4a2 2 0 0 1 2-2h8l6 6v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" /><path d="M14 2v6h6" /><path d="M10 7h1M10 10h1M10 13h1" />
									</svg>
									<span class="truncate">{file.name}</span>
									<span
										class="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full bg-surface-200 px-2 py-0.5 text-[0.7rem] font-medium text-surface-600 transition-colors group-hover:bg-primary-100 group-hover:text-primary-800"
									>
										Unzip &amp; load
									</span>
								</button>
							</li>
						{/each}
						{#if !dirs.length && !files.length && !error}
							<li class="px-3 py-8 text-center text-sm text-surface-600">
								No sub-folders or .zip files here.
							</li>
						{/if}
					</ul>
				{/if}
			</div>

			<!-- Footer: use current folder -->
			<footer class="border-t border-surface-200 px-5 py-3.5">
				{#if !loading && !error}
					{#if isExport}
						<p class="mb-2.5 flex items-center gap-1.5 text-xs text-primary-700">
							<svg viewBox="0 0 24 24" class="size-3.5" fill="none" stroke="currentColor"
								stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
							This folder is a valid Facebook export.
						</p>
					{:else}
						<p class="mb-2.5 flex items-start gap-1.5 text-xs text-surface-600">
							<svg viewBox="0 0 24 24" class="mt-px size-3.5 shrink-0" fill="none" stroke="currentColor"
								stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" /></svg>
							No export detected here yet — open the folder with <code class="font-mono">posts/</code>, or
							pick a <code class="font-mono">.zip</code> to unzip it here (no upload).
						</p>
					{/if}
				{/if}
				<div class="flex justify-end gap-2">
					<button
						type="button"
						class="rounded-lg px-3.5 py-2 text-sm font-medium text-surface-700 transition-colors hover:bg-surface-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
						onclick={() => onClose?.()}>Cancel</button
					>
					<button
						type="button"
						class="inline-flex items-center gap-1.5 rounded-lg bg-primary-700 px-4 py-2 text-sm font-semibold text-primary-50 shadow-sm transition-colors hover:bg-primary-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
						disabled={loading || !!error || !path}
						onclick={() => onChoose?.(path)}
					>
						Use this folder
					</button>
				</div>
			</footer>
		</div>
	</div>
{/if}
