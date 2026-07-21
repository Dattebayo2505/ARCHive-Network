<script>
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { ingestFolder, ingestUpload, ingestZip, listReadyBuilds, listWorkspaces, openWorkspace, removeWorkspace, revealReadyBuild } from '$lib/api.js';
	import { formatSize } from '$lib/stats.js';
	import FolderPicker from '$lib/components/FolderPicker.svelte';
	import ReadyBuildList from '$lib/components/ReadyBuildList.svelte';
	import WorkspaceList from '$lib/components/WorkspaceList.svelte';

	let busy = $state(false);
	let busyLabel = $state('');
	let progress = $state(0); // 0..1 while an HTTP upload is in flight; 0 otherwise
	let errors = $state([]);
	let dragging = $state(false);
	let pickerOpen = $state(false);
	let typedPath = $state('');
	let fileInput = $state();
	let workspaces = $state([]);
	let resolving = $state(true); // true while deciding auto-resume vs. show list
	let viewMode = $state('list'); // 'list' | 'detailed' | 'content'
	let workspaceStatsMap = $state({});
	let readyBuilds = $state([]);
	let totalMediaBytes = $derived(workspaces.reduce((sum, ws) => sum + (workspaceStatsMap[ws.id]?.mediaBytes || 0), 0));

	function handleStatLoad(wsId, stats) {
		workspaceStatsMap[wsId] = stats;
	}

	async function revealBuild(id) {
		const result = await revealReadyBuild(id);
		if (!result.ok) errors = [result.error ?? 'Could not open the file manager.'];
	}

	async function handle(promise, label) {
		busy = true;
		busyLabel = label;
		errors = [];
		const result = await promise;
		busy = false;
		progress = 0;
		if (result.ok) await goto('/gallery');
		else errors = result.errors ?? ['Something went wrong loading that export.'];
	}

	function onFiles(fileList) {
		const file = fileList?.[0];
		if (!file) return;
		if (!file.name.toLowerCase().endsWith('.zip')) {
			errors = [`"${file.name}" isn’t a .zip — drop the export archive you downloaded from Facebook.`];
			return;
		}
		progress = 0;
		handle(
			ingestUpload(file, { onProgress: (p) => (progress = p) }),
			`Uploading ${file.name}…`
		);
	}

	function onDrop(e) {
		e.preventDefault();
		dragging = false;
		if (!busy) onFiles(e.dataTransfer?.files);
	}

	function chooseFolder(path) {
		pickerOpen = false;
		typedPath = path;
		handle(ingestFolder(path), 'Reading folder…');
	}

	// A .zip picked from this computer: the server unzips it in place — no upload.
	function chooseZip(path) {
		pickerOpen = false;
		handle(ingestZip(path), 'Unzipping the archive…');
	}

	function submitTyped(e) {
		e.preventDefault();
		const p = typedPath.trim();
		if (!p || busy) return;
		handle(ingestFolder(p), 'Reading folder…');
	}

	onMount(async () => {
		const switching = new URLSearchParams(window.location.search).get('switch') === '1';
		const data = await listWorkspaces();
		workspaces = data.workspaces ?? [];
		if (!switching && data.last_active) {
			const result = await openWorkspace(data.last_active);
			if (result.ok) {
				await goto('/gallery');
				return;
			}
		}
		const ready = await listReadyBuilds();
		readyBuilds = ready.builds ?? [];
		resolving = false;
	});

	async function openWs(id) {
		busy = true;
		busyLabel = 'Opening workspace…';
		const result = await openWorkspace(id);
		busy = false;
		if (result.ok) await goto('/gallery');
		else errors = [result.error ?? 'Could not open that workspace.'];
	}

	async function removeWs(id, deleteFiles) {
		const result = await removeWorkspace(id, deleteFiles);
		if (result.ok) {
			workspaces = workspaces.filter((w) => w.id !== id);
		} else {
			errors = [result.error ?? 'Could not remove that workspace.'];
		}
	}
</script>

<section class="mx-auto max-w-2xl">
	{#if resolving}
		<div class="flex items-center justify-center py-16" aria-live="polite">
			<span class="size-8 animate-spin rounded-full border-[3px] border-primary-200 border-t-primary-600" aria-hidden="true"></span>
		</div>
	{:else}
		{#if workspaces.length}
			<div class="mb-8">
				<div class="mb-3 flex items-center justify-between">
					<h2 class="flex items-center gap-2 text-lg font-semibold tracking-tight text-surface-900">
						Your workspaces
						{#if totalMediaBytes > 0}
							<span class="text-surface-300 font-normal">|</span>
							<span class="text-base font-medium text-surface-500 tracking-normal tabular-nums">
								{formatSize(totalMediaBytes)}
							</span>
						{/if}
					</h2>
					<div class="flex items-center gap-1 rounded-lg border border-surface-200 bg-surface-50 p-0.5 shadow-sm">
						<button class="rounded-md p-1.5 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 {viewMode === 'detailed' ? 'bg-surface-200 text-surface-900 shadow-sm' : 'text-surface-500 hover:text-surface-700 hover:bg-surface-100'}" title="Detailed list" onclick={() => viewMode = 'detailed'}>
							<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h16M4 18h16"/><path d="M8 6v12M16 6v12" stroke-opacity="0.3" stroke-dasharray="2 2"/></svg>
						</button>
						<button class="rounded-md p-1.5 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 {viewMode === 'list' ? 'bg-surface-200 text-surface-900 shadow-sm' : 'text-surface-500 hover:text-surface-700 hover:bg-surface-100'}" title="Cards view" onclick={() => viewMode = 'list'}>
							<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>
						</button>
						<button class="rounded-md p-1.5 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 {viewMode === 'content' ? 'bg-surface-200 text-surface-900 shadow-sm' : 'text-surface-500 hover:text-surface-700 hover:bg-surface-100'}" title="Compact list" onclick={() => viewMode = 'content'}>
							<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>
						</button>
					</div>
				</div>
				<WorkspaceList {workspaces} onOpen={openWs} onRemove={removeWs} onStatLoad={handleStatLoad} {viewMode} />
			</div>
		{/if}

		{#if readyBuilds.length}
			<div class="mb-8">
				<h2 class="mb-3 text-lg font-semibold tracking-tight text-surface-900">Ready builds</h2>
				<ReadyBuildList builds={readyBuilds} onReveal={revealBuild} />
			</div>
		{/if}

		{#if workspaces.length || readyBuilds.length}
			<div class="my-6 flex items-center gap-3 text-xs font-medium tracking-wide text-surface-600">
				<span class="h-px flex-1 bg-surface-300"></span>
				OR ADD A NEW EXPORT
				<span class="h-px flex-1 bg-surface-300"></span>
			</div>
		{/if}
	<div class="mb-6">
		<h1 class="text-2xl font-semibold tracking-tight text-surface-900 text-balance">
			Load this week’s export
		</h1>
		<p class="mt-1.5 text-surface-600">
			Drop the Facebook <em class="not-italic font-medium text-surface-700">Download Your
				Information</em> archive, or point ARCHive Network at the unzipped folder. Nothing is changed
			until you build.
		</p>
	</div>

	{#if errors.length}
		<div
			class="mb-5 rounded-xl border border-error-200 bg-error-50 p-4"
			role="alert"
			aria-live="polite"
		>
			<p class="flex items-center gap-2 font-medium text-error-800">
				<svg viewBox="0 0 24 24" class="size-4.5 shrink-0" fill="none" stroke="currentColor"
					stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" /></svg>
				That export isn’t complete
			</p>
			<ul class="mt-2 space-y-1 pl-6.5 text-sm text-error-700">
				{#each errors as e}
					<li class="list-disc">
						Missing <code class="font-mono text-error-800">{e}</code>
					</li>
				{/each}
			</ul>
		</div>
	{/if}

	<!-- Primary: drag-and-drop .zip -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="group relative rounded-2xl border-2 border-dashed bg-surface-50 px-6 py-10 text-center transition-all duration-300 {dragging
			? 'border-primary-500 bg-primary-50 dark:bg-primary-100 shadow-inner'
			: 'border-surface-300 hover:border-primary-400 hover:bg-surface-100'}"
		ondragover={(e) => {
			e.preventDefault();
			dragging = true;
		}}
		ondragleave={() => (dragging = false)}
		ondrop={onDrop}
	>
		<input
			bind:this={fileInput}
			class="sr-only"
			type="file"
			accept=".zip"
			onchange={(e) => onFiles(e.currentTarget.files)}
		/>

		{#if busy}
			<div class="flex flex-col items-center gap-3 py-2" aria-live="polite">
				<span
					class="size-8 animate-spin rounded-full border-[3px] border-primary-200 border-t-primary-600"
					aria-hidden="true"
				></span>
				<p class="font-medium text-surface-700">{busyLabel}</p>
				{#if progress > 0 && progress < 1}
					<div class="w-full max-w-xs">
						<div
							class="h-2 overflow-hidden rounded-full bg-surface-200"
							role="progressbar"
							aria-valuenow={Math.round(progress * 100)}
							aria-valuemin="0"
							aria-valuemax="100"
						>
							<div
								class="h-full rounded-full bg-primary-600 transition-[width] duration-150"
								style="width: {progress * 100}%"
							></div>
						</div>
						<p class="mt-1.5 text-sm tabular-nums text-surface-600">
							{Math.round(progress * 100)}% uploaded
						</p>
					</div>
				{:else}
					<p class="text-sm text-surface-600">Large exports can take a moment.</p>
				{/if}
			</div>
		{:else}
			<span
				class="mx-auto mb-4 grid size-14 place-items-center rounded-full bg-primary-100 text-primary-700 transition-all duration-300 {dragging ? 'scale-110 shadow-lg ring-4 ring-primary-500/20' : 'group-hover:-translate-y-1 group-hover:bg-primary-200 group-hover:shadow-md'}"
				aria-hidden="true"
			>
				<svg viewBox="0 0 24 24" class="size-7 transition-transform duration-300 {dragging ? 'animate-bounce' : 'group-hover:scale-105'}" fill="none" stroke="currentColor" stroke-width="1.75"
					stroke-linecap="round" stroke-linejoin="round">
					<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
					<path d="M12 3v13M7 8l5-5 5 5" />
				</svg>
			</span>
			<p class="font-medium text-surface-800">
				Drop your <span class="font-mono text-sm text-surface-700">export.zip</span> here
			</p>
			<p class="mt-1 text-sm text-surface-600">or</p>
			<button
				type="button"
				class="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-primary-700 px-4 py-2 text-sm font-semibold text-primary-50 shadow-sm transition-colors hover:bg-primary-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
				onclick={() => fileInput?.click()}
			>
				Browse files
			</button>
		{/if}
	</div>

	<!-- Divider -->
	<div class="my-5 flex items-center gap-3 text-xs font-medium tracking-wide text-surface-600">
		<span class="h-px flex-1 bg-surface-300"></span>
		ALREADY UNZIPPED?
		<span class="h-px flex-1 bg-surface-300"></span>
	</div>

	<!-- Secondary: folder on this machine -->
	<div class="rounded-2xl border border-surface-300 bg-surface-50 p-5">
		<div class="flex items-start gap-3">
			<span
				class="grid size-10 shrink-0 place-items-center rounded-lg bg-surface-200 text-surface-600"
				aria-hidden="true"
			>
				<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="1.75"
					stroke-linecap="round" stroke-linejoin="round">
					<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
				</svg>
			</span>
			<div class="min-w-0 flex-1">
				<p class="font-medium text-surface-800">Load from this computer</p>
				<p class="mt-0.5 text-sm text-surface-600">
					Browse to the unzipped export <em class="not-italic font-medium text-surface-700">or a
						.zip</em>, or paste a path. The .zip is unzipped locally — no upload.
				</p>
			</div>
			<button
				type="button"
				class="shrink-0 rounded-lg border border-surface-300 bg-surface-50 px-3.5 py-2 text-sm font-medium text-surface-800 shadow-sm transition-colors hover:bg-surface-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:opacity-50"
				onclick={() => (pickerOpen = true)}
				disabled={busy}
			>
				Browse…
			</button>
		</div>

		<form class="mt-3 flex items-center gap-2" onsubmit={submitTyped}>
			<div
				class="flex flex-1 items-center gap-2 rounded-lg border border-surface-300 bg-surface-50 px-3 focus-within:border-primary-500 focus-within:ring-2 focus-within:ring-primary-500/30"
			>
				<svg viewBox="0 0 24 24" class="size-4 shrink-0 text-surface-400" fill="none"
					stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
					<path d="m9 18 6-6-6-6" /><path d="M4 12h11" opacity="0.4" />
				</svg>
				<input
					class="min-w-0 flex-1 bg-transparent py-2 font-mono text-sm text-surface-800 placeholder:font-sans placeholder:text-surface-600 focus:outline-none"
					type="text"
					bind:value={typedPath}
					placeholder="e.g. D:\exports\facebook-export"
					spellcheck="false"
					autocomplete="off"
					aria-label="Folder path"
					disabled={busy}
				/>
			</div>
			<button
				type="submit"
				class="shrink-0 rounded-lg bg-primary-700 px-4 py-2 text-sm font-semibold text-primary-50 shadow-sm transition-colors hover:bg-primary-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:opacity-50"
				disabled={busy || !typedPath.trim()}
			>
				Load
			</button>
		</form>
	</div>
	{/if}
</section>

<FolderPicker
	open={pickerOpen}
	onClose={() => (pickerOpen = false)}
	onChoose={chooseFolder}
	onChooseZip={chooseZip}
/>
