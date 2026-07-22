<script>
	import {
		autoCurate,
		devDatabase,
		devDatabaseCreate,
		devDatabaseDrop,
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
	// The *database*, as opposed to its tables. A failed connection cannot tell you which of
	// two very different things went wrong, so /api/dev/status now carries a server probe
	// (`server_up`, `database`, `database_exists`) alongside the raw error. That probe is the
	// single source of truth here — these two hold only the outcome of the last db action.
	let dbError = $state('');
	let dbNotice = $state('');
	let confirmDropDb = $state(false);
	let busy = $state(''); // '' | 'schema' | 'reset' | 'load' | 'validate' | 'curate' | 's3'
	//                     | 'db-status' | 'db-create' | 'db-drop'
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
	const LIMIT = 10;

	const connected = $derived(status?.enabled && status?.connected);
	const ready = $derived(connected && status?.tables_exist);

	async function refreshStatus() {
		status = await devStatus();
	}

	/** The explicit "is it there?" check. Re-reads the probe that /api/dev/status carries. */
	async function checkDatabase() {
		busy = 'db-status';
		dbError = '';
		dbNotice = '';
		const found = await devDatabase();
		if (!found.server_up) dbError = found.reason ?? "Can't reach the PostgreSQL server.";
		else
			dbNotice = found.database_exists
				? `Database "${found.database}" exists.`
				: `The server is up, but database "${found.database}" does not exist yet.`;
		await refreshStatus();
		busy = '';
	}

	// Create/drop, then re-read status: a freshly created database still has no tables, and a
	// dropped one takes the tables and rows with it — both change what the rest of this panel
	// may offer.
	async function runDatabase(action, key, describe) {
		busy = key;
		dbError = '';
		dbNotice = '';
		const res = await action();
		if (!res.ok) dbError = res.body?.detail ?? 'The database operation failed.';
		else dbNotice = describe(res.body);
		await refreshStatus();
		await refreshRows();
		busy = '';
	}

	const createDatabase = () =>
		runDatabase(devDatabaseCreate, 'db-create', (b) =>
			b.created
				? `Created database "${b.database}". Create the tables next.`
				: `Database "${b.database}" was already there.`
		);

	const dropDatabase = () =>
		runDatabase(devDatabaseDrop, 'db-drop', (b) =>
			b.dropped
				? `Dropped database "${b.database}".`
				: `Database "${b.database}" was already gone.`
		);

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
			: ['fb_album_id', 'title', 'hashtag', 'is_derived', 'date', 'caption']
	);

	// ── Column sizing ────────────────────────────────────────────────────────────────
	// Widths are fractions of the resizable region, kept per table so switching tabs restores
	// each layout. A handle drags the *boundary between two columns*: width moves from one to
	// its right-hand neighbour and the total is conserved. That is what removes the horizontal
	// scrollbar — the table can never grow wider than its container, so `overflow-x-auto` has
	// nothing to scroll. It also matches what the handle looks like it does.
	//
	// `min-w` on the table is the deliberate exception: below it every column is an unreadable
	// sliver, and scrolling a too-narrow viewport beats truncating all six columns to "…".
	const MIN_FRAC = 0.05;
	const PREVIEW_PX = 56; // the media thumbnail column — fixed, and has no handle

	let colWidths = $state({});
	let tableWidth = $state(0);

	const fractions = $derived(
		colWidths[table]?.length === columns.length
			? colWidths[table]
			: columns.map(() => 1 / columns.length)
	);
	const regionPx = $derived(Math.max(1, tableWidth - (table === 'media' ? PREVIEW_PX : 0)));

	// Every column is sized as a PLAIN percentage, and they sum to exactly 100 — that is what
	// guarantees the table can't overflow, so no scrollbar appears.
	//
	// It must not be `calc(<pct> - <px>)`: Chrome silently drops a mixed %/px calc() on <col>
	// and falls back to distributing the columns equally. Verified in-browser — `30%` and
	// `260px` both apply, `calc(30% - 10px)` does not. So the fixed-width preview column is
	// expressed as its own share of the measured table width instead of subtracted in CSS.
	const previewPct = $derived(
		table === 'media' && tableWidth > 0 ? (PREVIEW_PX / tableWidth) * 100 : 0
	);
	const colPcts = $derived(fractions.map((f) => f * (100 - previewPct)));

	/** Move `delta` (a fraction) across boundary `i`, clamped so neither side dips below MIN_FRAC. */
	function setBoundary(i, delta, base) {
		const lo = MIN_FRAC - base[i];
		const hi = base[i + 1] - MIN_FRAC;
		const d = Math.max(lo, Math.min(hi, delta));
		const next = [...base];
		next[i] += d;
		next[i + 1] -= d;
		colWidths[table] = next;
	}

	function startResize(e, i) {
		e.preventDefault();
		const startX = e.clientX;
		const base = [...fractions];
		let frame = 0;
		let pending = null;

		function cleanup() {
			cancelAnimationFrame(frame);
			frame = 0;
			window.removeEventListener('pointermove', onMove);
			window.removeEventListener('pointerup', onUp);
			window.removeEventListener('pointercancel', onUp);
		}

		// Coalesce moves into one layout write per frame — every change reflows the whole table.
		function apply() {
			frame = 0;
			if (pending === null) return;
			const delta = (pending - startX) / regionPx;
			pending = null;
			setBoundary(i, delta, base);
		}

		function onMove(ev) {
			pending = ev.clientX;
			if (!frame) frame = requestAnimationFrame(apply);
		}

		function onUp() {
			apply();
			cleanup();
		}

		window.addEventListener('pointermove', onMove);
		window.addEventListener('pointerup', onUp);
		window.addEventListener('pointercancel', onUp);
	}

	// The handle is the only resize affordance, so it has to work from the keyboard too —
	// same vocabulary as the gallery's dock tab: arrows step, Shift steps further, Home/End max out.
	function onHandleKey(e, i) {
		const step = e.shiftKey ? 0.06 : 0.02;
		let delta = null;
		if (e.key === 'ArrowLeft') delta = -step;
		else if (e.key === 'ArrowRight') delta = step;
		else if (e.key === 'Home') delta = -1; // clamped to MIN_FRAC by setBoundary
		else if (e.key === 'End') delta = 1;
		if (delta === null) return;
		e.preventDefault();
		setBoundary(i, delta, [...fractions]);
	}

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

<!-- Scrollbar hidden to match every other inner scroll pane in the app (the photo grid, the
     album rail, the selection dock, the preview filmstrips all do the same). The pane still
     scrolls by wheel, trackpad and keyboard; this panel was simply the one that missed the
     convention, and its 15px Windows bar sat right against the row table's edge. -->
<div class="flex h-full flex-col overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
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
					<!-- Two very different failures arrive as the same libpq error, so the probe in
					     /api/dev/status splits them. A missing database is one button away from
					     fixed; a dead server is not something this panel can repair. -->
					{@const missing = status.server_up && !status.database_exists}
					<div class="max-w-prose">
						<div class="flex items-center gap-2.5">
							<span
								class="size-2.5 rounded-full {missing ? 'bg-warning-500' : 'bg-error-500'}"
								aria-hidden="true"
							></span>
							<p class="text-sm font-medium text-surface-900">
								{#if missing}
									The database doesn't exist yet
								{:else if status.server_up}
									Can't open the database
								{:else}
									Can't reach the PostgreSQL server
								{/if}
							</p>
						</div>

						{#if missing}
							<p class="mt-2 text-sm leading-relaxed text-surface-600">
								The server at <code
									class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>127.0.0.1:5432</code
								>
								is running and accepted your credentials, but it has no database named
								<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>{status.database}</code
								>. Create it here, then create the tables.
							</p>
						{:else}
							<p class="mt-2 text-sm leading-relaxed text-surface-600">
								{status.server_up
									? 'The server is up but refused this database.'
									: 'Nothing answered on that host and port. Start PostgreSQL, then check again.'}
							</p>
							<p class="mt-2 font-mono text-xs leading-relaxed break-words text-error-700">
								{status.reason}
							</p>
						{/if}
					</div>

					<div class="flex gap-2">
						{@render secondaryBtn('Check status', 'Checking…', 'db-status', checkDatabase)}
						{#if missing}
							{@render primaryBtn('Create database', 'Creating…', 'db-create', createDatabase)}
						{/if}
					</div>
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
							Database <code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>{status.database}</code
							>
							· object store
							<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>{status.media_root}</code
							>
							· served at
							<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>{status.media_base_url}</code
							>
						</p>
					</div>
					<div class="flex flex-wrap justify-end gap-2">
						{@render secondaryBtn('Check status', 'Checking…', 'db-status', checkDatabase)}
						{#if !status.tables_exist}
							{@render primaryBtn('Create tables', 'Creating…', 'schema', () => createSchema(false))}
						{:else}
							{@render secondaryBtn('Reset tables', 'Resetting…', 'reset', () => (confirmReset = true))}
						{/if}
						<!-- Drop the whole database, not just its tables. Sits last and behind a named
						     confirm: it is the widest-blast-radius control on this panel. -->
						{@render secondaryBtn(
							'Drop database',
							'Dropping…',
							'db-drop',
							() => (confirmDropDb = true)
						)}
					</div>
				{/if}

				{#if dbError}
					<p
						class="w-full rounded-lg border border-error-200 bg-error-50 px-3 py-2 font-mono text-xs break-words text-error-800"
						role="alert"
					>
						{dbError}
					</p>
				{:else if dbNotice}
					<p
						class="w-full rounded-lg border border-surface-200 bg-surface-100 px-3 py-2 text-sm text-surface-800"
						aria-live="polite"
					>
						{dbNotice}
					</p>
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
							<table
								class="w-full min-w-[46rem] table-fixed border-collapse text-left"
								bind:clientWidth={tableWidth}
							>
								<!-- Declared once here rather than per-<th>: with `table-fixed` the colgroup
								     is what actually sizes the columns. See `colPcts` for why these are
								     plain percentages and never a mixed %/px calc(). -->
								<colgroup>
									{#if table === 'media'}
										<col style="width: {previewPct}%" />
									{/if}
									{#each columns as col, i (col)}
										<col style="width: {colPcts[i]}%" />
									{/each}
								</colgroup>
								<thead>
									<tr class="border-b border-surface-200 bg-surface-100">
										{#if table === 'media'}
											<th class="px-3 py-2"><span class="sr-only">Preview</span></th>
										{/if}
										{#each columns as col, i (col)}
											<th
												class="relative px-3 py-2 font-mono text-xs font-semibold text-surface-700 select-none"
											>
												<span class="block truncate" title={col}>{col}</span>
												{#if i < columns.length - 1}
													<button
														type="button"
														onpointerdown={(e) => startResize(e, i)}
														onkeydown={(e) => onHandleKey(e, i)}
														aria-label="Resize the {col} column"
														title="Drag to resize · arrow keys also work"
														class="absolute top-1/2 right-0 z-10 h-6 w-3 -translate-y-1/2 translate-x-1/2 cursor-col-resize rounded-xs before:absolute before:inset-y-0 before:left-1/2 before:w-px before:-translate-x-1/2 before:bg-surface-300 before:transition-colors hover:before:bg-primary-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 focus-visible:before:bg-primary-600"
													></button>
												{/if}
											</th>
										{/each}
									</tr>
								</thead>
								<tbody>
									{#each rows.rows as row (row.media_id ?? row.fb_album_id)}
										<tr class="border-b border-surface-200 last:border-0 hover:bg-surface-100">
											{#if table === 'media'}
												<td class="px-3 py-1.5">
													<!-- `min-w-9` is still load-bearing under `table-fixed`: Tailwind's preflight
													     `img { max-width: 100% }` resolves against the column box, so a squeezed
													     column would collapse the preview to nothing. The colgroup pins this
													     column at PREVIEW_PX; the min-width is the floor if that ever gives. -->
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
												<!-- `table-fixed` + the colgroup own the width now, so the cell only has
												     to truncate what it's given. The title keeps the full value reachable. -->
												<td
													class="truncate px-3 py-1.5 font-mono text-xs text-surface-700"
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
	open={confirmDropDb}
	title="Drop the {status?.database} database?"
	message="This deletes the entire database — the photo_album and media tables and every row in them — not just their contents. Any open connections to it are closed first. The files already in the object store, your export, and your ready folder are all left alone. You can create it again from this panel."
	confirmLabel="Drop database"
	cancelLabel="Cancel"
	destructive
	onConfirm={() => {
		confirmDropDb = false;
		dropDatabase();
	}}
	onCancel={() => (confirmDropDb = false)}
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
