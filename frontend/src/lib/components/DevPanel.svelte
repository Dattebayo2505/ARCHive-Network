<script>
	import {
		autoCurate,
		devLoad,
		devRows,
		devStatus,
		devTable,
		devTableCreate,
		devTableDelete,
		devValidate,
		dockerFloci,
		dockerStatus,
		flociUiTarget,
		s3Status,
		storeUrl,
		uploadToS3
	} from '$lib/api.js';
	import {
		canUpload,
		flociAutoOpen,
		flociUiUrl,
		s3Target,
		shouldOpenFlociUi
	} from '$lib/s3target.svelte.js';
	import ConfirmDialog from './ConfirmDialog.svelte';

	// The dev pane runs the real downstream ETL locally: it reads the built ready/ folder,
	// copies each image into a local object store, and upserts album + media items into
	// DynamoDB. Dev-mode is a *backend* capability — every /api/dev/* route 404s unless
	// ARCHIVENETWORK_DYNAMODB_TABLE is set — so this panel must degrade honestly when it isn't.
	//
	// Auto-curate is the exception: it is a *selection* action, needs no table, and so lives
	// outside the table-gated block below.
	let { selectedPhotos = 0, selectedVideos = 0, onCurated = () => {} } = $props();

	let status = $state(null); // null while first loading
	// /api/dev/status carries the probe, keeping `endpoint_reachable` apart from `table_exists`
	// so the panel offers the right fix. These two hold only the outcome of the last table action.
	let tableError = $state('');
	let tableNotice = $state('');
	let confirmDeleteTable = $state(false);
	let busy = $state(''); // '' | 'load' | 'validate' | 'curate' | 's3'
	//                     | 'table-status' | 'table-create' | 'table-reset' | 'table-delete'
	//                     | 'docker-start' | 'docker-restart' | 'docker-stop' | 'docker-rebuild'
	let loadResult = $state(null);
	let report = $state(null);
	let error = $state(''); // an actionable failure from the last action
	let confirmReset = $state(false);
	let confirmCurate = $state(false);
	let curateResult = $state(null);
	let curateError = $state('');

	let docker = $state(null); // null while first loading
	let dockerError = $state('');
	let dockerOutput = $state(''); // the command's own tail, shown only when it failed

	let s3 = $state(null); // null while loading; { aws: {...}, floci: {...} }
	// Results and errors are kept PER TARGET, not in one slot. The switch used to clear both,
	// so flipping it to read the other bucket's name destroyed the summary you had just run —
	// and flipping back did not bring it back. A result belongs to the target it came from;
	// showing the active target's own last result is both honest and non-destructive.
	let s3Results = $state({ aws: null, floci: null });
	let s3Errors = $state({ aws: '', floci: '' });
	const s3Result = $derived(s3Results[s3Target.target]);
	const s3Error = $derived(s3Errors[s3Target.target]);
	let confirmS3 = $state(false);
	// Set only when the browser refused the post-upload tab; the fallback link is then the
	// user gesture that opens it.
	let uiBlocked = $state(false);

	// Where the Floci UI link actually points. The destination is the storage explorer on the
	// UI container's own port (:4500) — the bucket itself, not the console's landing page. But
	// that container is created *only* by the poller page, so a deep link is dead on a cold
	// machine. `uiTarget` is the backend's warmed answer; until it confirms `ready`, the link
	// falls back to the poller, which always renders. So the panel shows the deep link in every
	// normal case and can never show a refused connection.
	let uiTarget = $state(null);
	const flociUi = $derived(uiTarget?.url ?? flociUiUrl(s3?.floci?.endpoint_url));

	// Warming is idempotent and short-circuits once the container is up, so it is safe to call
	// on mount and after any lifecycle action. Called at the two moments floci can *become*
	// available rather than from an $effect on `reachable`: every probe replaces the `s3`
	// object, so an effect would re-fire on each poll and a not-ready answer would retry
	// forever at ~12s a go.
	let warming = false;
	async function warmFlociUi() {
		if (warming || s3?.floci?.reachable !== true) return;
		warming = true;
		try {
			uiTarget = await flociUiTarget();
		} finally {
			warming = false;
		}
	}
	// Docker-not-running is the common case; the endpoint line keeps the rarer causes
	// (port conflict, overridden ARCHIVENETWORK_FLOCI_ENDPOINT_URL) diagnosable. When Docker
	// *is* usable there is nothing to instruct — the Start button below does it.
	const flociEndpoint = $derived(s3?.floci?.endpoint_url ?? 'http://127.0.0.1:4566');
	// EVERY branch names Docker. The 502 this banner mirrors (`FLOCI_DOWN_DETAIL`) always
	// does, and a banner that quietly stopped saying "Docker" while the error kept saying it
	// would let the two disagree about the same failure. The branches differ only in what to
	// DO about Docker, never in whether Docker is the subject.
	const flociDownMessage = $derived(
		s3?.api_reachable === false
			? // Not a floci failure at all: the fallback reading fires when the backend itself
				// never answered, and blaming Docker for that is a misattribution.
				`The ARCHiveNetwork API isn't answering, so whether floci is up can't be checked ` +
					`from here. Start the backend, then Re-check.`
			: !docker?.available
				? `Docker isn't running. Floci needs it. Start Docker Desktop, then bring the ` +
					`container up with \`docker compose up -d\`, then Re-check. Expected at ${flociEndpoint}.`
				: docker.running
					? // Running but silent: starting it again would fix nothing, so don't suggest it.
						`Docker is running the floci container, but nothing is answering at ` +
						`${flociEndpoint}. Something else may be holding the port, or ` +
						`ARCHIVENETWORK_FLOCI_ENDPOINT_URL points elsewhere. Try Restart below, then Re-check.`
					: `Docker is running, but its floci container isn't, so there's nowhere to upload ` +
						`yet. Start it and this clears itself once the emulator answers - no terminal ` +
						`needed. Expected at ${flociEndpoint}.`
	);
	const flociDown = $derived(s3?.floci?.reachable === false);
	// Who owns the Start button. When the emulator is unreachable *and* the container is down,
	// the warning is the loud moment and the fix belongs inside it; the strip below then drops
	// its own Start so two of them aren't sitting 40px apart. A container that is running but
	// still unreachable (a port conflict, an overridden endpoint) is not a Start problem, so
	// the banner offers only Re-check and the strip keeps Restart/Stop.
	const bannerOwnsStart = $derived(flociDown && !!docker?.available && !docker.running);
	const uploadReady = $derived(canUpload(s3Target.target, s3));

	async function refreshS3() {
		s3 = await s3Status();
		return s3;
	}

	// Arming floci must evaluate against a current reading, not one from page load —
	// otherwise a container started after mount leaves a permanently disabled button.
	function switchTarget() {
		s3Target.toggle();
		uiBlocked = false;
		if (s3Target.target === 'floci') refreshS3();
	}

	// NO 'noopener' in the features string, deliberately: per spec `window.open` returns **null**
	// whenever noopener is requested, which is indistinguishable from a blocked popup — the tab
	// opened fine and the panel still claimed the browser had refused it. The null return is the
	// only signal a blocker gives, so it has to mean one thing. Dropping the flag costs nothing
	// here: the target is the user's own container on 127.0.0.1, and the visible <a> fallback
	// keeps rel="noopener noreferrer".
	function openFlociUi() {
		const win = window.open(flociUi, '_blank');
		uiBlocked = !win;
		return !!win;
	}

	async function runUpload() {
		const target = s3Target.target;
		busy = 's3';
		s3Errors = { ...s3Errors, [target]: '' };
		s3Results = { ...s3Results, [target]: null };
		uiBlocked = false;
		const res = await uploadToS3(target);
		// 409 (not built), 422 (no target) and 502 (unreachable) are expected, actionable
		// cases — not crashes.
		if (!res.ok) s3Errors = { ...s3Errors, [target]: res.body?.detail ?? 'The upload failed.' };
		else s3Results = { ...s3Results, [target]: res.body };
		busy = '';
		if (target === 'floci') {
			refreshS3();
			// Only when the bucket actually gained objects — a run that skipped everything has
			// nothing new to show, and stealing a tab for it would be noise. `window.open` after
			// an await is outside the click's task, so a strict popup blocker may refuse it;
			// `uiBlocked` turns that into a visible link rather than a silent nothing.
			if (flociAutoOpen.enabled && shouldOpenFlociUi(target, res.body)) openFlociUi();
		}
	}

	// --- The floci container's lifecycle ------------------------------------------------
	// The Docker-down message used to be the only way out of a dead emulator, and it assumed
	// the reader would open a terminal. These controls remove that assumption; they appear
	// only when the backend reports Docker is genuinely usable, so the message is still the
	// honest fallback when it isn't.
	const containerLabel = $derived(
		docker?.running
			? 'Container running'
			: docker?.exists
				? `Container ${docker.container}`
				: 'Container not created yet'
	);

	async function refreshDocker() {
		docker = await dockerStatus();
	}

	/** Poll until the S3 API answers. The container reports "running" a beat before floci has
	 *  bound :4566, so a single re-probe right after `up -d` reads as down and would re-arm
	 *  the very warning the Start button just resolved. */
	async function waitForFloci(tries = 12) {
		for (let i = 0; i < tries; i += 1) {
			const now = await refreshS3();
			if (now?.floci?.reachable) return true;
			await new Promise((resolve) => setTimeout(resolve, 1000));
		}
		return false;
	}

	async function runDocker(action) {
		busy = `docker-${action}`;
		dockerError = '';
		dockerOutput = '';
		uiBlocked = false;
		const res = await dockerFloci(action);
		if (!res.ok) {
			// 409: Docker stopped being usable between the probe and the click.
			dockerError = res.body?.detail ?? `The floci container could not be ${action}ed.`;
			await refreshDocker();
		} else {
			docker = res.body.docker;
			if (!res.body.ok) {
				dockerError = `\`docker compose ${action}\` didn't succeed.`;
				dockerOutput = res.body.output ?? '';
			}
		}
		if (action === 'stop' || dockerError) {
			await refreshS3();
			// The sibling UI container is not stopped with floci, but the deep link is only
			// trustworthy while floci can vouch for it — re-warm rather than assume.
			uiTarget = null;
		} else if (await waitForFloci()) {
			await warmFlociUi();
			// The table's reachability rides on floci, so its status is stale now too.
			await refreshStatus();
		}
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
	/** @type {{type: string, total: number, limit: number, offset: number, rows: Record<string, any>[]} | null} */
	let rows = $state(null);
	// The table shows curated columns; JSON shows each item whole (GSI keys, overrides, loaded_at).
	let view = $state('table');
	const LIMIT = 10;

	const connected = $derived(status?.enabled && status?.endpoint_reachable);
	const ready = $derived(connected && status?.table_exists);

	async function refreshStatus() {
		status = await devStatus();
	}

	/** The explicit "is it there?" check. Re-reads the probe that /api/dev/status carries. */
	async function checkTable() {
		busy = 'table-status';
		tableError = '';
		tableNotice = '';
		const found = await devTable();
		if (!found.endpoint_reachable) tableError = found.reason ?? "Can't reach DynamoDB.";
		else if (found.refused) tableError = found.reason ?? 'DynamoDB refused the request.';
		else
			tableNotice = found.table_exists
				? `Table "${found.table}" exists.`
				: `DynamoDB is up, but table "${found.table}" does not exist yet.`;
		await refreshStatus();
		busy = '';
	}

	// Create/reset/delete, then re-read status: each changes what the rest of the panel may
	// offer, and a reset or delete takes every item with it.
	async function runTable(action, key, describe) {
		busy = key;
		tableError = '';
		tableNotice = '';
		reset();
		const res = await action();
		if (!res.ok) tableError = res.body?.detail ?? 'The table operation failed.';
		else {
			tableNotice = describe(res.body);
			offset = 0;
		}
		await refreshStatus();
		await refreshRows();
		busy = '';
	}

	const createTable = () =>
		runTable(
			() => devTableCreate(false),
			'table-create',
			(b) => (b.created ? `Created table "${b.table}".` : `Table "${b.table}" was already there.`)
		);

	const resetTable = () =>
		runTable(
			() => devTableCreate(true),
			'table-reset',
			(b) => `Reset table "${b.table}"; it is empty.`
		);

	const deleteTable = () =>
		runTable(devTableDelete, 'table-delete', (b) =>
			b.deleted ? `Deleted table "${b.table}".` : `Table "${b.table}" was already gone.`
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

	// Independent of dev-mode: S3 is gated on its own setting, not the table. Warming the
	// Floci UI rides along, so the deep link is live well before anyone clicks it.
	$effect(() => {
		refreshS3().then(warmFlociUi);
	});

	// And the container is independent of both — it is a machine-level thing, so this asks
	// once on mount whether the lifecycle controls may be offered at all.
	$effect(() => {
		refreshDocker();
	});

	// Re-page / re-type whenever the browser's inputs change, and once the table appears.
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
					{
						label: 'Media',
						value: `+${loadResult.media_inserted}`,
						sub:
							`${loadResult.media_updated} updated` +
							(loadResult.skipped_deleted?.length
								? ` · ${loadResult.skipped_deleted.length} tombstoned`
								: '')
					},
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
			? ['id', 'media_type', 'album_id', 'hashtags', 'description', 'creation_at', 'storage_path']
			: ['id', 'title', 'source', 'hashtags', 'date', 'description']
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
		if (Array.isArray(value)) return value.length ? value.join(' ') : '—';
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

<!-- The one outbound link in this panel. The hover state is a SOLID green chip rather than the
     usual pale-tint-plus-dark-ink pairing: the primary ramp does not invert under `.dark`, so
     `bg-primary-100 text-primary-800` would collapse to green-on-green at night (the
     HashtagPills lesson). `bg-primary-700 text-primary-50` reads identically in both themes.
     The arrow and the sr-only note carry "new tab" without relying on the colour change. -->
{#snippet flociUiLink(label)}
	<a
		href={flociUi}
		target="_blank"
		rel="noopener noreferrer"
		onclick={() => (uiBlocked = false)}
		class="inline-flex items-center gap-1 rounded bg-surface-200 px-1.5 py-0.5 font-mono text-xs text-surface-800 underline decoration-primary-500 decoration-1 underline-offset-2 transition-colors hover:bg-primary-700 hover:text-primary-50 hover:decoration-primary-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
	>
		{label}
		<svg
			viewBox="0 0 24 24"
			class="size-3 shrink-0"
			fill="none"
			stroke="currentColor"
			stroke-width="2.5"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"><path d="M7 17 17 7M9 7h8v8" /></svg
		>
		<span class="sr-only">(opens the Floci UI in a new tab)</span>
	</a>
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
				> folder, copies each image into a local object store, and upserts it into DynamoDB. Your
				original export is never touched.
			</p>
		</header>

		<!-- ── Curation ─────────────────────────────────────────────────────────────────
		     A sibling panel, not a section of the one below: auto-curate is a *selection*
		     action and needs no table, so it must stay outside the table-gated block. -->
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

		<!-- ── Upload to S3 / floci ───────────────────────────────────────────────────
		     A sibling panel like auto-curate: an object-store push with NO database
		     involvement, so it must stay outside the DB-gated block below. The section no
		     longer hides when AWS is unconfigured — floci is always available, so the AWS
		     *position of the switch* is what gets disabled.

		     Colour carries the state: floci leaves the card neutral, AWS tints the whole card
		     with `warning` tokens, so "this writes to production" is legible from across the
		     room and not only from the button's label. The `warning` ramp does NOT invert
		     under `.dark` (only `surface` does), so this pale-tint/dark-ink pairing is stable
		     in both themes rather than the primary-100/primary-800 trap. -->
		<section
			class="mb-4 rounded-xl border p-5 transition-colors {s3Target.target === 'aws'
				? 'border-warning-400 bg-warning-50'
				: 'border-surface-300 bg-surface-50'}"
		>
			<div class="flex flex-wrap items-start justify-between gap-3">
				<div class="max-w-prose">
					<h2 class="text-sm font-semibold text-surface-900">
						Upload to {s3Target.target === 'aws' ? 'S3' : 'floci'}
					</h2>
					{#if s3Target.target === 'aws'}
						<p class="mt-1 text-xs leading-relaxed text-surface-600">
							Pushes this workspace's built <code
								class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800">ready/</code
							> media to
							<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>s3://{s3?.aws?.bucket}</code
							>
							({s3?.aws?.region}). Re-running is safe — objects already there are skipped.
						</p>
					{:else}
						<p class="mt-1 text-xs leading-relaxed text-surface-600">
							Pushes this workspace's built <code
								class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800">ready/</code
							> media to the local floci emulator at
							<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>{s3?.floci?.endpoint_url}</code
							>. Nothing leaves your machine. The bucket is created if it doesn't exist. Browse
							what's in it with
							<!-- nowrap so the full stop can't wrap onto a line of its own behind the
							     inline-flex link, which is exactly what it did at panel width. -->
							<span class="whitespace-nowrap">{@render flociUiLink('Floci UI')}.</span>
						</p>
					{/if}
				</div>

				<div class="flex flex-col items-end gap-2">
					<!-- role="switch" is honest here: "on" means the real, production target. Visible
					     labels sit on both sides so neither position reads as merely "off". -->
					<div class="flex items-center gap-2">
						<span
							class="text-xs font-medium {s3Target.target === 'floci'
								? 'text-surface-900'
								: 'text-surface-500'}">Local floci</span
						>
						<!-- Only the AWS *position* is unavailable when AWS is unconfigured. Disabling the
						     whole control would strand a profile whose stored preference is already 'aws'
						     (a bucket unset after the fact): switch dead, Upload dead, and no route back
						     to floci, the one target that is always offered. So the switch stays live
						     whenever it is pointing AT aws. -->
						<button
							type="button"
							role="switch"
							aria-checked={s3Target.target === 'aws'}
							aria-label="Upload to real AWS S3"
							disabled={(s3Target.target === 'floci' && !s3?.aws?.enabled) || busy !== ''}
							onclick={switchTarget}
							class="relative h-5 w-9 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 {s3Target.target ===
							'aws'
								? 'bg-warning-600'
								: 'bg-surface-400'}"
						>
							<span
								class="absolute top-0.5 size-4 rounded-full bg-surface-50 transition-all {s3Target.target ===
								'aws'
									? 'left-4.5'
									: 'left-0.5'}"
							></span>
						</button>
						<span
							class="text-xs font-medium {s3Target.target === 'aws'
								? 'text-warning-800'
								: 'text-surface-500'}">AWS S3</span
						>
					</div>
					{#if !s3?.aws?.enabled}
						<p class="text-right text-xs text-surface-500">
							AWS unavailable — set <code
								class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>ARCHIVENETWORK_S3_BUCKET</code
							> in <code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>.env</code
							> and restart the API.
						</p>
					{/if}
					{@render primaryBtn(
						s3Target.target === 'aws' ? 'Upload to S3' : 'Upload to floci',
						'Uploading…',
						's3',
						() => (confirmS3 = true),
						!uploadReady
					)}
				</div>
			</div>

			{#if flociDown}
				<!-- Shown on BOTH targets: someone sitting on AWS should learn the testing path is
				     down before flipping to it. Worded as information, never as an obstruction. -->
				<!-- warning-100, a step darker than the card's own warning-50 tint, so the band
				     still separates on the AWS card as well as on the neutral floci one. -->
				<div
					class="mt-4 flex flex-wrap items-start justify-between gap-3 rounded-lg border border-warning-400 bg-warning-100 px-3 py-2"
					role="status"
				>
					<p class="max-w-prose text-sm text-warning-800">{flociDownMessage}</p>
					<div class="flex shrink-0 flex-wrap items-center gap-2">
						<!-- The one place a second green button is allowed to sit near Upload: while the
						     emulator is down, Upload is disabled, so nothing is competing. This is the
						     limit moment the theme spends colour on. -->
						{#if bannerOwnsStart}
							{@render primaryBtn(
								docker.exists ? 'Start floci' : 'Create and start floci',
								'Starting…',
								'docker-start',
								() => runDocker('start')
							)}
						{/if}
						<!-- Never gated on `busy` or on the probe: this is always the way out of a
						     disabled Upload button. -->
						<button
							type="button"
							onclick={refreshS3}
							class="rounded-lg border border-warning-400 bg-surface-50 px-3 py-1.5 text-sm font-medium text-warning-800 transition-colors hover:bg-warning-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
							>Re-check</button
						>
					</div>
				</div>
			{/if}

			<!-- ── The floci container ────────────────────────────────────────────────────
			     A hairline strip, not a nested card: this section is already a card, and a box
			     inside a box is the enterprise-admin reflex the brand explicitly rejects.
			     Offered only when the backend says Docker is genuinely usable — otherwise the
			     warning above is still the honest answer, and a dead button would be a lie.
			     The verbs are rendered by state rather than disabled: Stop means nothing on a
			     container that isn't running, and a row of greyed-out buttons is not
			     self-evident, it's a puzzle. -->
			{#if docker?.available}
				<div
					class="mt-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-3 border-t border-surface-200 pt-3"
				>
					<div class="flex min-w-0 items-center gap-2.5">
						<span
							class="size-2.5 shrink-0 rounded-full {docker.running
								? 'bg-success-600'
								: 'bg-surface-400'}"
							aria-hidden="true"
						></span>
						<p class="min-w-0 text-xs text-surface-700">
							<span class="font-medium text-surface-900">{containerLabel}</span>
							<span class="text-surface-500"> · {docker.container_name}</span>
						</p>
					</div>

					<div class="flex flex-wrap items-center gap-2">
						{#if docker.running}
							{@render secondaryBtn('Restart', 'Restarting…', 'docker-restart', () =>
								runDocker('restart')
							)}
							{@render secondaryBtn('Stop', 'Stopping…', 'docker-stop', () => runDocker('stop'))}
						{:else if !bannerOwnsStart}
							{@render secondaryBtn(
								docker.exists ? 'Start' : 'Create and start',
								'Starting…',
								'docker-start',
								() => runDocker('start')
							)}
						{/if}
						<!-- Named for what it does to the image, because "Rebuild" alone would read as
						     "rebuild my ready folder" in a panel that has one of those. -->
						{@render secondaryBtn('Rebuild image', 'Rebuilding…', 'docker-rebuild', () =>
							runDocker('rebuild')
						)}
					</div>
				</div>

				<p class="mt-2 text-xs leading-relaxed text-surface-600">
					Rebuild re-pulls <code class="rounded bg-surface-200 px-1 py-0.5 font-mono">floci/floci</code
					> and re-creates the container. Uploaded objects live in
					<code class="rounded bg-surface-200 px-1 py-0.5 font-mono">workspace/floci-data/</code> and
					survive all four actions.
				</p>

				{#if dockerError}
					<div
						class="mt-3 rounded-lg border border-error-200 bg-error-50 px-3 py-2"
						role="alert"
					>
						<p class="text-sm text-error-800">{dockerError}</p>
						{#if dockerOutput}
							<pre
								class="mt-2 max-h-40 overflow-auto rounded bg-surface-100 p-2 font-mono text-xs leading-relaxed text-surface-700">{dockerOutput}</pre>
						{/if}
					</div>
				{/if}
			{/if}

			<!-- The tab is the reassurance that the upload landed somewhere real, so it is on by
			     default — but it opens a window, and anything that opens a window has to be
			     refusable. Only ever fires when the bucket actually gained objects. -->
			{#if s3Target.target === 'floci'}
				<label
					class="mt-3 flex w-fit cursor-pointer items-center gap-2 text-xs text-surface-700 select-none"
				>
					<input
						type="checkbox"
						checked={flociAutoOpen.enabled}
						onchange={(event) => flociAutoOpen.set(event.currentTarget.checked)}
						class="size-3.5 rounded border-surface-400 accent-primary-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
					/>
					Open the Floci UI after an upload that adds new objects
				</label>
			{/if}

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

				<!-- Names the target the summary came from, which is what makes keeping a result
				     per target safe: flip the switch and the numbers change, but so does this line. -->
				<p class="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-surface-600">
					<span>
						Uploaded to <span class="font-medium text-surface-800"
							>{s3Result.target === 'aws' ? `s3://${s3Result.bucket}` : s3Result.endpoint_url}</span
						>
						· bucket <code class="rounded bg-surface-200 px-1 py-0.5 font-mono">{s3Result.bucket}</code
						>
					</span>
					{#if s3Result.target === 'floci'}
						{@render flociUiLink('View in Floci UI')}
					{/if}
				</p>

				{#if uiBlocked}
					<p class="mt-1 text-xs text-surface-600" role="status">
						Your browser blocked the new tab — open the Floci UI with the link above.
					</p>
				{/if}

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
			{:else if s3Results.aws || s3Results.floci}
				<!-- The switch used to blank this whole region, and flipping back did not bring the
				     summary back. Now each target keeps its own, and the empty position says so
				     rather than looking like the panel reset itself. -->
				<p class="mt-4 text-xs text-surface-600">
					No upload to {s3Target.target === 'aws' ? 'AWS S3' : 'floci'} yet. The
					{s3Target.target === 'aws' ? 'floci' : 'AWS S3'} summary is still here — flip the switch
					back to read it.
				</p>
			{/if}
		</section>

		<!-- One panel, hairline-divided. Not four floating cards. -->
		<div class="overflow-hidden rounded-xl border border-surface-300 bg-surface-50">
			<!-- ── Status ───────────────────────────────────────────────── -->
			<section class="flex flex-wrap items-start justify-between gap-4 p-5">
				{#if status === null}
					<div class="flex items-center gap-2.5">
						<span class="size-2.5 animate-pulse rounded-full bg-surface-400" aria-hidden="true"></span>
						<p class="text-sm text-surface-600">Checking the table…</p>
					</div>
				{:else if !status.enabled}
					<div class="max-w-prose">
						<div class="flex items-center gap-2.5">
							<span class="size-2.5 rounded-full bg-surface-400" aria-hidden="true"></span>
							<p class="text-sm font-medium text-surface-900">Dev mode is not configured</p>
						</div>
						<p class="mt-2 text-sm leading-relaxed text-surface-600">
							The backend has no DynamoDB table to talk to. Set <code
								class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
								>ARCHIVENETWORK_DYNAMODB_TABLE</code
							>
							in a <code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
								>.env</code
							> file at the repo root, then restart the API.
						</p>
					</div>
				{:else if !status.endpoint_reachable || status.refused || !status.table_exists}
					<!-- An unreachable endpoint, a refusal and a missing table each need a different fix,
					     and only the last is one this panel can make — so only it earns Create table. -->
					{@const missing = status.endpoint_reachable && !status.refused}
					<div class="max-w-prose">
						<div class="flex items-center gap-2.5">
							<span
								class="size-2.5 rounded-full {missing ? 'bg-warning-500' : 'bg-error-500'}"
								aria-hidden="true"
							></span>
							<p class="text-sm font-medium text-surface-900">
								{#if missing}
									The table doesn't exist yet
								{:else if status.refused}
									DynamoDB refused the request
								{:else}
									Can't reach DynamoDB
								{/if}
							</p>
						</div>

						<p class="mt-2 text-sm leading-relaxed text-surface-600">
							{#if missing}
								DynamoDB at <code
									class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>{status.endpoint}</code
								>
								is up, but has no table named
								<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>{status.table}</code
								>. Create it here.
							{:else if status.refused}
								<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>{status.endpoint}</code
								>
								answered but refused to describe
								<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>{status.table}</code
								>. Check the credentials and permissions.
							{:else if status.on_emulator}
								Nothing answered at <code
									class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>{status.endpoint}</code
								>. Start floci with <code
									class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>docker compose up -d</code
								> (or the Docker controls above), then check again.
							{:else}
								<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>{status.endpoint}</code
								> did not answer with this machine's AWS credentials.
							{/if}
						</p>
						{#if !missing && status.reason}
							<p class="mt-2 font-mono text-xs leading-relaxed break-words text-error-700">
								{status.reason}
							</p>
						{/if}
					</div>

					<div class="flex gap-2">
						{@render secondaryBtn('Check status', 'Checking…', 'table-status', checkTable)}
						{#if missing && status.on_emulator}
							{@render primaryBtn('Create table', 'Creating…', 'table-create', createTable)}
						{/if}
					</div>
				{:else}
					<div>
						<div class="flex items-center gap-2.5">
							<span class="size-2.5 rounded-full bg-success-500" aria-hidden="true"></span>
							<p class="text-sm font-medium text-surface-900">Connected</p>
						</div>
						<p class="mt-2 text-xs text-surface-600">
							Table <code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>{status.table}</code
							>
							· endpoint
							<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>{status.endpoint}</code
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
						{@render secondaryBtn('Check status', 'Checking…', 'table-status', checkTable)}
						<!-- Table admin is emulator-only (the backend 409s on AWS; Terraform owns those
						     tables). Delete sits last behind a named confirm: the widest blast radius here. -->
						{#if status.on_emulator}
							{@render secondaryBtn('Reset table', 'Resetting…', 'table-reset', () => (confirmReset = true))}
							{@render secondaryBtn(
								'Delete table',
								'Deleting…',
								'table-delete',
								() => (confirmDeleteTable = true)
							)}
						{/if}
					</div>
				{/if}

				{#if tableError}
					<p
						class="w-full rounded-lg border border-error-200 bg-error-50 px-3 py-2 font-mono text-xs break-words text-error-800"
						role="alert"
					>
						{tableError}
					</p>
				{:else if tableNotice}
					<p
						class="w-full rounded-lg border border-surface-200 bg-surface-100 px-3 py-2 text-sm text-surface-800"
						aria-live="polite"
					>
						{tableNotice}
					</p>
				{/if}
			</section>

			{#if ready}
				<!-- Item counts. Hairline grid, same idiom as the build summary. -->
				<div class="grid grid-cols-2 gap-px border-y border-surface-200 bg-surface-200">
					{#each [{ label: 'album items', value: status.counts.album }, { label: 'media items', value: status.counts.media }] as stat (stat.label)}
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
							<h2 class="text-sm font-semibold text-surface-900">Load into DynamoDB</h2>
							<p class="mt-0.5 text-xs text-surface-600">
								Storage first, then the items. Re-running is safe — nothing is uploaded twice, and
								CMS edits and deletions are never overwritten.
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

						{#if loadResult.orphans.length || loadResult.errors.length || loadResult.skipped_deleted?.length}
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
										...loadResult.errors,
										...(loadResult.skipped_deleted ?? []).map((k) => `tombstoned: ${k}`)
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
								Checks the loaded items against the ready folder and the object store.
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

				<!-- ── Item browser ──────────────────────────────────────── -->
				<section class="p-5">
					<div class="flex flex-wrap items-center justify-between gap-3">
						<h2 class="text-sm font-semibold text-surface-900">Items</h2>
						<div class="flex flex-wrap items-center gap-2">
							<div class="flex rounded-lg border border-surface-300 p-0.5" role="group" aria-label="View as">
								{#each [['table', 'Table'], ['json', 'JSON']] as [v, label] (v)}
									<button
										type="button"
										aria-pressed={view === v}
										onclick={() => (view = v)}
										class="rounded-md px-3 py-1 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 {view ===
										v
											? 'bg-primary-100 font-semibold text-primary-900'
											: 'text-surface-600 hover:bg-surface-200'}"
									>
										{label}
									</button>
								{/each}
							</div>
							<div
								class="flex rounded-lg border border-surface-300 p-0.5"
								role="tablist"
								aria-label="Item type"
							>
								{#each ['media', 'album'] as t (t)}
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
							<p class="text-sm font-medium text-surface-800">No items yet</p>
							<p class="mt-1 text-sm text-surface-600">
								Run the load above to populate <code class="font-mono text-xs">{table}</code> items.
							</p>
						</div>
					{:else}
						{#if view === 'json'}
							<pre
								data-testid="rows-json"
								class="mt-4 max-h-[32rem] overflow-auto rounded-lg border border-surface-200 bg-surface-100 p-3 font-mono text-xs leading-relaxed text-surface-800">{JSON.stringify(
									rows.rows,
									null,
									2
								)}</pre>
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
										{#each rows.rows as row (row.id)}
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
						{/if}

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
			{:else if connected && !status.table_exists && !status.refused}
				<div class="border-t border-surface-200 px-5 py-8 text-center">
					<p class="text-sm font-medium text-surface-800">The table isn't there yet</p>
					<p class="mx-auto mt-1 max-w-prose text-sm text-surface-600">
						Create <code class="font-mono text-xs">{status.table}</code> to start loading this workspace.
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
	title="Reset the table?"
	message="This deletes the {status?.table} table and recreates it empty. Items are lost, including any simulated CMS edits; the files already in the object store are left alone. Your export and ready folder are untouched."
	confirmLabel="Delete and recreate"
	cancelLabel="Cancel"
	destructive
	onConfirm={() => {
		confirmReset = false;
		resetTable();
	}}
	onCancel={() => (confirmReset = false)}
/>

<ConfirmDialog
	open={confirmDeleteTable}
	title="Delete the {status?.table} table?"
	message="This deletes the whole table and every item in it. The files already in the object store, your export, and your ready folder are all left alone. You can create it again from this panel."
	confirmLabel="Delete table"
	cancelLabel="Cancel"
	destructive
	onConfirm={() => {
		confirmDeleteTable = false;
		deleteTable();
	}}
	onCancel={() => (confirmDeleteTable = false)}
/>

<ConfirmDialog
	open={confirmS3}
	title={s3Target.target === 'aws'
		? 'Upload this build to AWS S3?'
		: 'Upload this build to floci?'}
	message={s3Target.target === 'aws'
		? `Copies this workspace's built ready/ media to s3://${s3?.aws?.bucket} (${s3?.aws?.region}). This is the REAL bucket. Objects already present are skipped; nothing is deleted. Your export, ready folder, and local store are untouched.`
		: `Copies this workspace's built ready/ media to the local floci emulator at ${s3?.floci?.endpoint_url} (bucket ${s3?.floci?.bucket}). Nothing leaves your machine. Objects already present are skipped; nothing is deleted.`}
	confirmLabel={s3Target.target === 'aws' ? 'Upload to S3' : 'Upload to floci'}
	cancelLabel="Cancel"
	onConfirm={() => {
		confirmS3 = false;
		runUpload();
	}}
	onCancel={() => (confirmS3 = false)}
/>
