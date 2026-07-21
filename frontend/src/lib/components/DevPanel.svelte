<script>
	import {
		autoCurate,
		devLoad,
		devRows,
		devSchema,
		devStatus,
		devValidate,
		s3Status,
		storeUrl,
		uploadToS3
	} from '$lib/api.js';
	import ConfirmDialog from './ConfirmDialog.svelte';

	// The dev pane runs the real downstream ETL locally: it reads the built ready/ folder,
	// copies each image into a local object store, and upserts photo_album + media into
	// PostgreSQL. Dev-mode is a *backend* capability — every /api/dev/* route 404s unless
	// ARCHIVENETWORK_DATABASE_URL is set — so this panel must degrade honestly when it isn't.
	//
	// Auto-curate is the exception: it is a *selection* action, needs no database, and so lives
	// outside the DB-gated block below.
	let { selectedPhotos = 0, selectedVideos = 0, onCurated = () => {} } = $props();

	let status = $state(null); // null while first loading
	let busy = $state(''); // '' | 'schema' | 'reset' | 'load' | 'validate' | 'curate' | 's3'
	let loadResult = $state(null);
	let report = $state(null);
	let error = $state(''); // an actionable failure from the last action
	let confirmReset = $state(false);
	let confirmCurate = $state(false);
	let curateResult = $state(null);
	let curateError = $state('');

	let s3 = $state(null); // null while loading; { enabled, bucket?, region? }
	let s3Result = $state(null);
	let s3Error = $state('');
	let confirmS3 = $state(false);

	async function refreshS3() {
		s3 = await s3Status();
	}

	async function runUpload() {
		busy = 's3';
		s3Error = '';
		s3Result = null;
		const res = await uploadToS3();
		// 409 (not built) and 502 (S3 unreachable) are expected, actionable cases — not crashes.
		if (!res.ok) s3Error = res.body?.detail ?? 'The S3 upload failed.';
		else s3Result = res.body;
		busy = '';
	}

	const hasSelection = $derived(selectedPhotos + selectedVideos > 0);

	async function runCurate() {
		busy = 'curate';
		curateError = '';
		curateResult = null;
		const res = await autoCurate();
		if (!res.ok) curateError = res.body?.detail ?? 'Auto-curate failed.';
		else {
			curateResult = res.body;
			await onCurated(); // the gallery owns the inventory; let it refresh its counts
		}
		busy = '';
	}

	let table = $state('media');
	let offset = $state(0);
	let rows = $state(null);
	const LIMIT = 25;

	const connected = $derived(status?.enabled && status?.connected);
	const ready = $derived(connected && status?.tables_exist);

	async function refreshStatus() {
		status = await devStatus();
	}

	async function refreshRows() {
		if (!ready) {
			rows = null;
			return;
		}
		const res = await devRows(table, LIMIT, offset);
		rows = res.ok ? res.body : null;
	}

	// First paint: ask the backend what it can actually do.
	$effect(() => {
		refreshStatus();
	});

	// Independent of dev-mode: S3 is gated on its own setting, not the database.
	$effect(() => {
		refreshS3();
	});

	// Re-page / re-table whenever the browser's inputs change, and once the schema appears.
	$effect(() => {
		void table;
		void offset;
		void ready;
		refreshRows();
	});

	function reset() {
		loadResult = null;
		report = null;
		error = '';
	}

	async function createSchema(destructive) {
		busy = destructive ? 'reset' : 'schema';
		reset();
		const res = await devSchema(destructive);
		if (!res.ok) error = res.body?.detail ?? 'Could not create the tables.';
		else if (destructive) offset = 0;
		await refreshStatus();
		await refreshRows();
		busy = '';
	}

	async function runLoad() {
		busy = 'load';
		reset();
		const res = await devLoad();
		// 409 is the expected "you have not built this workspace yet" case, not a crash.
		if (!res.ok) error = res.body?.detail ?? 'The load failed.';
		else loadResult = res.body;
		await refreshStatus();
		await refreshRows();
		busy = '';
	}

	async function runValidate() {
		busy = 'validate';
		reset();
		const res = await devValidate();
		if (!res.ok) error = res.body?.detail ?? 'Validation could not run.';
		else report = res.body;
		busy = '';
	}

	const loadStats = $derived(
		loadResult
			? [
					{ label: 'Albums', value: `+${loadResult.albums_inserted}`, sub: `${loadResult.albums_updated} updated` },
					{ label: 'Media', value: `+${loadResult.media_inserted}`, sub: `${loadResult.media_updated} updated` },
					{ label: 'Files stored', value: loadResult.files_stored, sub: `${loadResult.files_skipped} already there` },
					{
						label: 'Orphans',
						value: loadResult.orphans.length,
						sub: loadResult.orphans.length ? 'uri with no file' : 'none',
						warn: loadResult.orphans.length > 0
					}
				]
			: []
	);

	const page = $derived(rows ? Math.floor(rows.offset / rows.limit) + 1 : 1);
	const pages = $derived(rows ? Math.max(1, Math.ceil(rows.total / rows.limit)) : 1);
	const columns = $derived(
		table === 'media'
			? ['fbid', 'media_type', 'fb_album_id', 'hashtag', 'caption', 'creation_at', 'storage_path']
			: ['fb_album_id', 'title', 'hashtag', 'is_derived', 'date', 'description']
	);

	function cell(value) {
		if (value === null || value === undefined || value === '') return '—';
		if (typeof value === 'boolean') return value ? 'yes' : 'no';
		return String(value);
	}
</script>

{#snippet primaryBtn(label, busyLabel, key, onclick, disabled = false)}
	<button
		type="button"
		{onclick}
		disabled={disabled || busy !== ''}
		class="rounded-lg bg-primary-700 px-4 py-2 text-sm font-semibold text-primary-50 shadow-sm transition-colors hover:bg-primary-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
	>
		{busy === key ? busyLabel : label}
	</button>
{/snippet}

{#snippet secondaryBtn(label, busyLabel, key, onclick, disabled = false)}
	<button
		type="button"
		{onclick}
		disabled={disabled || busy !== ''}
		class="rounded-lg border border-surface-300 bg-surface-50 px-3.5 py-2 text-sm font-medium text-surface-800 transition-colors hover:bg-surface-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
	>
		{busy === key ? busyLabel : label}
	</button>
{/snippet}

<div class="flex h-full flex-col overflow-y-auto">
	<div class="mx-auto w-full max-w-5xl px-6 py-6">
		<header class="mb-5">
			<h1 class="text-lg font-semibold text-surface-900">Dev Mode</h1>
			<p class="mt-1 max-w-prose text-sm leading-relaxed text-surface-600">
				Runs the downstream ETL locally: reads this workspace's built <code
					class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800">ready/</code
				> folder, copies each image into a local object store, and upserts it into PostgreSQL. Your
				original export is never touched.
			</p>
		</header>

		<!-- ── Curation ─────────────────────────────────────────────────────────────────
		     A sibling panel, not a section of the one below: auto-curate is a *selection*
		     action and needs no database, so it must stay outside the DB-gated block. -->
		<section class="mb-4 rounded-xl border border-surface-300 bg-surface-50 p-5">
			<div class="flex flex-wrap items-start justify-between gap-3">
				<div class="max-w-prose">
					<h2 class="text-sm font-semibold text-surface-900">Auto-curate a selection</h2>
					<p class="mt-1 text-xs leading-relaxed text-surface-600">
						Picks up to 10 photos at random from every album — all of them where an album has
						fewer — and selects every video. Videos already carry an auto-captured first-frame
						still, so they build as-is.
					</p>
					<p class="mt-1.5 text-xs leading-relaxed text-surface-600">
						These are real picks, not auto-kept photos: they appear selected in the gallery and
						you can change any of them. Build still ships only what is selected.
					</p>
				</div>
				<div class="flex flex-col items-end gap-1.5">
					{@render primaryBtn('Auto-curate', 'Picking…', 'curate', () =>
						hasSelection ? (confirmCurate = true) : runCurate()
					)}
					<p class="text-xs tabular-nums text-surface-600">
						{selectedPhotos} photos · {selectedVideos} videos selected
					</p>
				</div>
			</div>

			{#if curateError}
				<p
					class="mt-4 rounded-lg border border-error-200 bg-error-50 px-3 py-2 text-sm text-error-800"
					role="alert"
				>
					{curateError}
				</p>
			{/if}

			{#if curateResult}
				{@const albums = curateResult.albums.filter((a) => a.picked > 0)}
				<div class="mt-4" aria-live="polite">
					<p class="text-sm text-surface-800">
						Picked <span class="font-semibold tabular-nums">{curateResult.photos_selected}</span>
						photos across
						<span class="font-semibold tabular-nums">{albums.length}</span>
						albums, and selected
						<span class="font-semibold tabular-nums">{curateResult.videos_selected}</span> videos.
					</p>
					<p class="mt-1 text-xs text-surface-600">
						Next: build the ready folder from the gallery, then load it below.
					</p>

					<details class="group mt-3">
						<summary
							class="flex cursor-pointer list-none items-center gap-1.5 text-sm font-medium text-surface-700 select-none"
						>
							<svg
								viewBox="0 0 24 24"
								class="size-4 transition-transform group-open:rotate-90"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
								stroke-linecap="round"
								stroke-linejoin="round"
								aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg
							>
							Per-album picks
						</summary>
						<ul
							class="mt-2 max-h-56 divide-y divide-surface-200 overflow-y-auto rounded-lg border border-surface-200"
						>
							{#each albums as a (a.fb_album_id)}
								<li class="flex items-center justify-between gap-3 px-3 py-1.5">
									<span class="min-w-0 flex-1 truncate text-xs text-surface-700">{a.name}</span>
									<span class="shrink-0 font-mono text-xs tabular-nums text-surface-600"
										>{a.picked} / {a.available}</span
									>
								</li>
							{/each}
						</ul>
					</details>
				</div>
			{/if}
		</section>

		<!-- ── Upload to S3 ───────────────────────────────────────────────────────────
		     A sibling panel like auto-curate: an object-store push with NO database
		     involvement, so it must stay outside the DB-gated block below. Gated on the
		     backend having a bucket configured. -->
		<section class="mb-4 rounded-xl border border-surface-300 bg-surface-50 p-5">
			<div class="flex flex-wrap items-start justify-between gap-3">
				<div class="max-w-prose">
					<h2 class="text-sm font-semibold text-surface-900">Upload to S3</h2>
					{#if s3?.enabled}
						<p class="mt-1 text-xs leading-relaxed text-surface-600">
							Pushes this workspace's built <code
								class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800">ready/</code
							> media to
							<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>s3://{s3.bucket}</code
							>
							({s3.region}). Re-running is safe — objects already there are skipped.
						</p>
					{:else}
						<p class="mt-1 text-xs leading-relaxed text-surface-600">
							Not configured. Set <code
								class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
								>ARCHIVENETWORK_S3_BUCKET</code
							> in <code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
								>.env</code
							> and restart the API.
						</p>
					{/if}
				</div>
				{#if s3?.enabled}
					<div class="flex flex-col items-end gap-1.5">
						{@render primaryBtn('Upload to S3', 'Uploading…', 's3', () => (confirmS3 = true))}
					</div>
				{/if}
			</div>

			{#if s3Error}
				<p
					class="mt-4 rounded-lg border border-error-200 bg-error-50 px-3 py-2 text-sm text-error-800"
					role="alert"
				>
					{s3Error}
				</p>
			{/if}

			{#if s3Result}
				<div
					class="mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-surface-200 bg-surface-200"
					aria-live="polite"
				>
					{#each [{ label: 'Uploaded', value: s3Result.uploaded }, { label: 'Skipped', value: s3Result.skipped, sub: 'already there' }, { label: 'Orphans', value: s3Result.orphans.length, sub: s3Result.orphans.length ? 'uri with no file' : 'none', warn: s3Result.orphans.length > 0 }] as stat (stat.label)}
						<div class="bg-surface-50 px-4 py-3">
							<p
								class="text-lg font-semibold tabular-nums {stat.warn
									? 'text-warning-700'
									: 'text-surface-900'}"
							>
								{stat.value}
							</p>
							<p class="mt-0.5 text-xs font-medium text-surface-800">{stat.label}</p>
							{#if stat.sub}<p class="text-xs text-surface-600">{stat.sub}</p>{/if}
						</div>
					{/each}
				</div>

				{#if s3Result.orphans.length || s3Result.errors.length}
					<details class="group mt-3">
						<summary
							class="flex cursor-pointer list-none items-center gap-1.5 text-sm font-medium text-surface-700 select-none"
						>
							<svg
								viewBox="0 0 24 24"
								class="size-4 transition-transform group-open:rotate-90"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
								stroke-linecap="round"
								stroke-linejoin="round"
								aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg
							>
							What was skipped
						</summary>
						<pre
							class="mt-2 max-h-44 overflow-auto rounded-lg bg-surface-100 p-3 font-mono text-xs leading-relaxed text-surface-700">{[
								...s3Result.orphans,
								...s3Result.errors
							].join('\n')}</pre>
					</details>
				{/if}
			{/if}
		</section>

		<!-- One panel, hairline-divided. Not four floating cards. -->
		<div class="overflow-hidden rounded-xl border border-surface-300 bg-surface-50">
			<!-- ── Status ───────────────────────────────────────────────── -->
			<section class="flex flex-wrap items-start justify-between gap-4 p-5">
				{#if status === null}
					<div class="flex items-center gap-2.5">
						<span class="size-2.5 animate-pulse rounded-full bg-surface-400" aria-hidden="true"></span>
						<p class="text-sm text-surface-600">Checking the database…</p>
					</div>
				{:else if !status.enabled}
					<div class="max-w-prose">
						<div class="flex items-center gap-2.5">
							<span class="size-2.5 rounded-full bg-surface-400" aria-hidden="true"></span>
							<p class="text-sm font-medium text-surface-900">Dev mode is not configured</p>
						</div>
						<p class="mt-2 text-sm leading-relaxed text-surface-600">
							The backend has no database to talk to. Set <code
								class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
								>ARCHIVENETWORK_DATABASE_URL</code
							>
							in a <code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
								>.env</code
							> file at the repo root, then restart the API.
						</p>
					</div>
				{:else if !status.connected}
					<div class="max-w-prose">
						<div class="flex items-center gap-2.5">
							<span class="size-2.5 rounded-full bg-error-500" aria-hidden="true"></span>
							<p class="text-sm font-medium text-surface-900">Can't reach PostgreSQL</p>
						</div>
						<p class="mt-2 font-mono text-xs leading-relaxed break-words text-error-700">
							{status.reason}
						</p>
					</div>
					{@render secondaryBtn('Retry', 'Retrying…', 'schema', refreshStatus)}
				{:else}
					<div>
						<div class="flex items-center gap-2.5">
							<span
								class="size-2.5 rounded-full {status.tables_exist
									? 'bg-success-500'
									: 'bg-warning-500'}"
								aria-hidden="true"
							></span>
							<p class="text-sm font-medium text-surface-900">
								{status.tables_exist ? 'Connected' : 'Connected — tables not created yet'}
							</p>
						</div>
						<p class="mt-2 text-xs text-surface-600">
							Object store <code
								class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>{status.media_root}</code
							>
							· served at
							<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>{status.media_base_url}</code
							>
						</p>
					</div>
					<div class="flex gap-2">
						{#if !status.tables_exist}
							{@render primaryBtn('Create tables', 'Creating…', 'schema', () => createSchema(false))}
						{:else}
							{@render secondaryBtn('Reset tables', 'Resetting…', 'reset', () => (confirmReset = true))}
						{/if}
					</div>
				{/if}
			</section>

			{#if ready}
				<!-- Row counts. Hairline grid, same idiom as the build summary. -->
				<div class="grid grid-cols-2 gap-px border-y border-surface-200 bg-surface-200">
					{#each [{ label: 'photo_album rows', value: status.counts.photo_album }, { label: 'media rows', value: status.counts.media }] as stat (stat.label)}
						<div class="bg-surface-50 px-5 py-3">
							<p class="text-xl font-semibold tabular-nums text-surface-900">{stat.value}</p>
							<p class="mt-0.5 font-mono text-xs text-surface-600">{stat.label}</p>
						</div>
					{/each}
				</div>

				<!-- ── Load ─────────────────────────────────────────────── -->
				<section class="border-b border-surface-200 p-5">
					<div class="flex flex-wrap items-center justify-between gap-3">
						<div>
							<h2 class="text-sm font-semibold text-surface-900">Load into PostgreSQL</h2>
							<p class="mt-0.5 text-xs text-surface-600">
								Storage first, then the rows. Re-running is safe — nothing is uploaded or inserted
								twice.
							</p>
						</div>
						{@render primaryBtn('Run load', 'Loading…', 'load', runLoad)}
					</div>

					{#if error}
						<p
							class="mt-4 rounded-lg border border-error-200 bg-error-50 px-3 py-2 text-sm text-error-800"
							role="alert"
						>
							{error}
						</p>
					{/if}

					{#if loadResult}
						<div
							class="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-surface-200 bg-surface-200 sm:grid-cols-4"
							aria-live="polite"
						>
							{#each loadStats as stat (stat.label)}
								<div class="bg-surface-50 px-4 py-3">
									<p
										class="text-lg font-semibold tabular-nums {stat.warn
											? 'text-warning-700'
											: 'text-surface-900'}"
									>
										{stat.value}
									</p>
									<p class="mt-0.5 text-xs font-medium text-surface-800">{stat.label}</p>
									<p class="text-xs text-surface-600">{stat.sub}</p>
								</div>
							{/each}
						</div>

						{#if loadResult.orphans.length || loadResult.errors.length}
							<details class="group mt-3">
								<summary
									class="flex cursor-pointer list-none items-center gap-1.5 text-sm font-medium text-surface-700 select-none"
								>
									<svg
										viewBox="0 0 24 24"
										class="size-4 transition-transform group-open:rotate-90"
										fill="none"
										stroke="currentColor"
										stroke-width="2"
										stroke-linecap="round"
										stroke-linejoin="round"
										aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg
									>
									What was skipped
								</summary>
								<pre
									class="mt-2 max-h-44 overflow-auto rounded-lg bg-surface-100 p-3 font-mono text-xs leading-relaxed text-surface-700">{[
										...loadResult.orphans,
										...loadResult.errors
									].join('\n')}</pre>
							</details>
						{/if}
					{/if}
				</section>

				<!-- ── Validation ───────────────────────────────────────── -->
				<section class="border-b border-surface-200 p-5">
					<div class="flex flex-wrap items-center justify-between gap-3">
						<div>
							<h2 class="text-sm font-semibold text-surface-900">Validation</h2>
							<p class="mt-0.5 text-xs text-surface-600">
								Checks the loaded rows against the ready folder and the object store.
							</p>
						</div>
						{@render secondaryBtn('Run checks', 'Checking…', 'validate', runValidate)}
					</div>

					{#if report}
						{@const failed = report.checks.filter((c) => !c.ok).length}
						<p
							class="mt-4 text-sm font-medium {report.ok ? 'text-success-800' : 'text-error-800'}"
							aria-live="polite"
						>
							{report.ok
								? `All ${report.checks.length} checks passed.`
								: `${failed} of ${report.checks.length} checks failed.`}
						</p>
						<ul class="mt-2 divide-y divide-surface-200 rounded-lg border border-surface-200">
							{#each report.checks as check (check.name)}
								<li class="flex items-start gap-3 px-3 py-2.5">
									<!-- Icon + word: the verdict must never be carried by colour alone. -->
									<span
										class="mt-px grid size-4 shrink-0 place-items-center rounded-full {check.ok
											? 'bg-success-100 text-success-700'
											: 'bg-error-100 text-error-700'}"
										aria-hidden="true"
									>
										<svg
											viewBox="0 0 24 24"
											class="size-3"
											fill="none"
											stroke="currentColor"
											stroke-width="3.5"
											stroke-linecap="round"
											stroke-linejoin="round"
										>
											{#if check.ok}<path d="M20 6 9 17l-5-5" />{:else}<path
													d="M18 6 6 18M6 6l12 12"
												/>{/if}
										</svg>
									</span>
									<span class="min-w-0 flex-1">
										<span class="block text-sm text-surface-800">{check.name}</span>
										{#if !check.ok && check.detail}
											<span class="mt-0.5 block font-mono text-xs break-words text-error-700"
												>{check.detail}</span
											>
										{/if}
									</span>
									<span
										class="shrink-0 text-xs font-semibold {check.ok
											? 'text-success-700'
											: 'text-error-700'}">{check.ok ? 'Pass' : 'Fail'}</span
									>
								</li>
							{/each}
						</ul>
					{/if}
				</section>

				<!-- ── Row browser ──────────────────────────────────────── -->
				<section class="p-5">
					<div class="flex flex-wrap items-center justify-between gap-3">
						<h2 class="text-sm font-semibold text-surface-900">Rows</h2>
						<div
							class="flex rounded-lg border border-surface-300 p-0.5"
							role="tablist"
							aria-label="Table"
						>
							{#each ['media', 'photo_album'] as t (t)}
								<button
									type="button"
									role="tab"
									aria-selected={table === t}
									onclick={() => {
										table = t;
										offset = 0;
									}}
									class="rounded-md px-3 py-1 font-mono text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 {table ===
									t
										? 'bg-primary-100 font-semibold text-primary-900'
										: 'text-surface-600 hover:bg-surface-200'}"
								>
									{t}
								</button>
							{/each}
						</div>
					</div>

					{#if rows === null}
						<!-- Skeleton, not a spinner: the shape of what's coming. -->
						<div class="mt-4 space-y-px overflow-hidden rounded-lg bg-surface-200">
							{#each Array(5) as _, i (i)}
								<div class="h-11 animate-pulse bg-surface-100"></div>
							{/each}
						</div>
					{:else if rows.total === 0}
						<div class="mt-4 rounded-lg border border-dashed border-surface-300 px-4 py-8 text-center">
							<p class="text-sm font-medium text-surface-800">No rows yet</p>
							<p class="mt-1 text-sm text-surface-600">
								Run the load above to populate <code class="font-mono text-xs">{table}</code>.
							</p>
						</div>
					{:else}
						<div class="mt-4 overflow-x-auto rounded-lg border border-surface-200">
							<table class="w-full border-collapse text-left">
								<thead>
									<tr class="border-b border-surface-200 bg-surface-100">
										{#if table === 'media'}
											<th class="w-14 px-3 py-2"><span class="sr-only">Preview</span></th>
										{/if}
										{#each columns as col (col)}
											<th
												class="px-3 py-2 font-mono text-xs font-semibold whitespace-nowrap text-surface-700"
												>{col}</th
											>
										{/each}
									</tr>
								</thead>
								<tbody>
									{#each rows.rows as row (row.media_id ?? row.fb_album_id)}
										<tr class="border-b border-surface-200 last:border-0 hover:bg-surface-100">
											{#if table === 'media'}
												<td class="px-3 py-1.5">
													<!-- `min-w-9` is load-bearing. The table is table-layout:auto and already
													     overflows its wrapper, so the header's `w-14` is only a hint; and
													     Tailwind's preflight `img { max-width: 100% }` resolves to 100% of a
													     zero-width column, letting the browser collapse this cell to nothing.
													     An explicit min-width is the floor that keeps the preview visible. -->
													<img
														src={storeUrl(row.storage_path, status.media_base_url)}
														alt=""
														loading="lazy"
														width="36"
														height="36"
														class="size-9 min-w-9 rounded object-cover ring-1 ring-surface-300"
													/>
												</td>
											{/if}
											{#each columns as col (col)}
												<td
													class="max-w-[16rem] truncate px-3 py-1.5 font-mono text-xs text-surface-700"
													title={cell(row[col])}>{cell(row[col])}</td
												>
											{/each}
										</tr>
									{/each}
								</tbody>
							</table>
						</div>

						<div class="mt-3 flex items-center justify-between gap-3">
							<p class="font-mono text-xs text-surface-600">
								{rows.offset + 1}–{Math.min(rows.offset + rows.limit, rows.total)} of {rows.total}
							</p>
							<div class="flex items-center gap-2">
								{@render secondaryBtn(
									'Previous',
									'…',
									'page',
									() => (offset = Math.max(0, offset - LIMIT)),
									offset === 0
								)}
								<span class="font-mono text-xs text-surface-600">{page} / {pages}</span>
								{@render secondaryBtn(
									'Next',
									'…',
									'page',
									() => (offset = offset + LIMIT),
									rows.offset + rows.limit >= rows.total
								)}
							</div>
						</div>
					{/if}
				</section>
			{:else if status?.enabled && status?.connected && !status?.tables_exist}
				<div class="border-t border-surface-200 px-5 py-8 text-center">
					<p class="text-sm font-medium text-surface-800">The schema isn't there yet</p>
					<p class="mx-auto mt-1 max-w-prose text-sm text-surface-600">
						Create <code class="font-mono text-xs">photo_album</code> and
						<code class="font-mono text-xs">media</code> to start loading this workspace.
					</p>
				</div>
			{/if}
		</div>
	</div>
</div>

<ConfirmDialog
	open={confirmCurate}
	title="Replace the current selection?"
	message="Auto-curate overwrites every pick you have made — {selectedPhotos} photos and {selectedVideos} videos — with a fresh random selection of up to 10 photos per album plus all videos. Your export and any ready folder you have already built are untouched."
	confirmLabel="Replace selection"
	cancelLabel="Cancel"
	destructive
	onConfirm={() => {
		confirmCurate = false;
		runCurate();
	}}
	onCancel={() => (confirmCurate = false)}
/>

<ConfirmDialog
	open={confirmReset}
	title="Reset the database?"
	message="This drops the photo_album and media tables and recreates them empty. Rows are lost; the files already in the object store are left alone. Your export and ready folder are untouched."
	confirmLabel="Drop and recreate"
	cancelLabel="Cancel"
	destructive
	onConfirm={() => {
		confirmReset = false;
		createSchema(true);
	}}
	onCancel={() => (confirmReset = false)}
/>

<ConfirmDialog
	open={confirmS3}
	title="Upload this build to S3?"
	message="Copies this workspace's built ready/ media to s3://{s3?.bucket} ({s3?.region}). Objects already present are skipped; nothing is deleted. Your export, ready folder, and local store are untouched."
	confirmLabel="Upload to S3"
	cancelLabel="Cancel"
	onConfirm={() => {
		confirmS3 = false;
		runUpload();
	}}
	onCancel={() => (confirmS3 = false)}
/>
