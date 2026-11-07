<script>
	import { onMount } from 'svelte';
	import {
		autoCurate,
		devRows,
		devStatus,
		devTables,
		devTablesCreate,
		devTablesDelete,
		devValidate,
		dockerFloci,
		dockerStatus,
		flociUiTarget,
		getCurrentReadyBuild,
		listEnvs,
		publish
	} from '$lib/api.js';
	import { canPublish, envChoice } from '$lib/env.svelte.js';
	import { flociAutoOpen, flociUiUrl, shouldOpenFlociUi } from '$lib/floci.svelte.js';
	import ConfirmDialog from './ConfirmDialog.svelte';
	import EnvBanner from './EnvBanner.svelte';
	import EnvPicker from './EnvPicker.svelte';
	import EnvSignIn from './EnvSignIn.svelte';
	import PublishResult from './PublishResult.svelte';
	import TypeToConfirmDialog from './TypeToConfirmDialog.svelte';

	// The dev pane runs the real downstream ETL against one named environment: Publish uploads
	// this workspace's built ready/ folder to the env's bucket, upserts album + media items into
	// its DynamoDB tables, and verifies both landed. Everything below the environment bar is
	// scoped to the picked env; auto-curate is a *selection* action and is not.
	// `readyBuild` is the gallery's own build summary (it re-fetches after every build and delete),
	// so Publish enables the moment the rail's Build finishes. Left undefined, the panel fetches its own.
	let {
		selectedPhotos = 0,
		selectedVideos = 0,
		onCurated = () => {},
		readyBuild = undefined
	} = $props();

	// ── Environments ──────────────────────────────────────────────────────────────────
	let envList = $state(null); // null while the first /api/envs is in flight
	const env = $derived(envList?.envs?.find((e) => e.name === envChoice.name) ?? null);
	const isFloci = $derived(env?.kind === 'floci');
	// A 401 from any call marks that env's login as gone until it signs in again, whatever the
	// last /api/envs said. Keyed by env so dev's expiry never repaints prod's row.
	let expired = $state({});
	const EXPIRED = 'Your AWS login expired — sign in again.';
	const signedIn = $derived(isFloci || (!!env?.signed_in && !expired[env?.name]));

	function markExpired(name) {
		expired = { ...expired, [name]: true };
		// Drop the old env's "Connected" card now: refreshStatus short-circuits to signed out.
		if (name === env?.name) refreshStatus();
	}

	/** True when a response is the structured "signed out" refusal; flips the sign-in row. */
	function checkSignedOut(name, res) {
		const body = res?.body ?? res;
		if (res?.status === 401 || body?.error === 'signed_out') {
			markExpired(name);
			return true;
		}
		return false;
	}

	let status = $state(null); // null while loading
	// /api/dev/status carries the probe, keeping `endpoint_reachable` apart from `table_exists`
	// so the panel offers the right fix. These two hold only the outcome of the last table action.
	let tableError = $state('');
	let tableNotice = $state('');
	let confirmDeleteTable = $state(false);
	let busy = $state(''); // '' | 'publish' | 'validate' | 'curate'
	//                     | 'table-status' | 'table-create' | 'table-reset' | 'table-delete'
	//                     | 'docker-start' | 'docker-restart' | 'docker-stop' | 'docker-rebuild'
	let report = $state(null);
	let error = $state(''); // an actionable failure from the last validation
	let confirmReset = $state(false);
	let confirmCurate = $state(false);
	let curateResult = $state(null);
	let curateError = $state('');

	// The build summary for this workspace: Publish needs one, and the prod dialog states its counts.
	// The backend's 409 stays the backstop for a summary that has gone stale.
	let build = $state(null);
	$effect(() => {
		if (readyBuild !== undefined) build = readyBuild;
	});
	async function refreshBuild() {
		build = await getCurrentReadyBuild();
		return build;
	}

	// ── Publish ───────────────────────────────────────────────────────────────────────
	let publishResult = $state(null);
	let publishError = $state('');
	let confirmPublish = $state(false);

	const connected = $derived(!!status?.enabled && !!status?.endpoint_reachable);
	const ready = $derived(connected && !!status?.table_exists);
	const publishable = $derived(
		canPublish(env, { built: !!build, signedIn, tablesReady: ready, busy: busy !== '' })
	);
	// Say why Publish is off, so a disabled button is never a puzzle.
	const publishBlocker = $derived(
		!env
			? ''
			: !signedIn
				? `Sign in to ${env.label} first.`
				: !build
					? 'Build the ready folder from the gallery first.'
					: status && !ready
						? 'The tables below need attention first.'
						: ''
	);

	const mediaCount = $derived((build?.photos ?? 0) + (build?.videos ?? 0));
	const confirmDetails = $derived(
		env
			? [
					{ label: 'Environment', value: env.label },
					{ label: 'Bucket', value: `s3://${env.s3_bucket}` },
					{ label: 'Tables', value: `${env.table_prefix}-*` },
					{ label: 'Signed in as', value: env.identity ?? 'unknown' },
					{ label: 'Albums', value: String(build?.albums ?? 0) },
					{ label: 'Media', value: String(mediaCount) }
				]
			: []
	);

	const PUBLISH_ERRORS = {
		access_denied: (b) => `AWS refused the request: ${b.detail ?? 'access denied'}.`,
		confirm_required: (b) =>
			`The server needs the environment name typed exactly ("${b.env}"). Nothing was written.`,
		publish_running: (b) =>
			`A Publish to ${b.env} is already running (another tab?). Wait for it to finish.`,
		not_configured: (b) =>
			`${b.env} isn't set up yet: add its sign-in values to environments.local.toml, or, for a profile env, check that its AWS profile exists in your AWS config.`
	};

	async function startPublish() {
		if (!env) return;
		if (env.confirm) {
			const name = env.name;
			publishError = '';
			// Fresh counts: the dialog states what this Publish will write, not what it was at mount.
			// Fetched into a local: the call answers null on any error, so a blip must not erase the
			// build the gallery reported and leave Publish stuck off.
			const fresh = await getCurrentReadyBuild();
			// The picker stays live during the refetch; never open a dialog for an env not clicked.
			if (envChoice.name !== name) return;
			if (!fresh) {
				publishError =
					"Couldn't confirm the ready folder is still built. Nothing was published; try again, " +
					'or rebuild it from the gallery.';
				return;
			}
			build = fresh;
			confirmPublish = true;
		} else runPublish(null);
	}

	async function runPublish(typed) {
		const target = env;
		busy = 'publish';
		publishError = '';
		publishResult = null;
		uiBlocked = false;
		let res;
		try {
			res = await publish(target.name, typed);
		} catch {
			res = { ok: false, status: 0, body: { detail: "Couldn't reach the API." } };
		}
		busy = '';
		if (envChoice.name !== target.name) return; // switched away mid-run; its result is stale
		if (checkSignedOut(target.name, res)) {
			// The sign-in row already says the login expired; only the server's own detail adds to it.
			publishError = res.body?.detail ?? '';
			return;
		}
		if (!res.ok) {
			const code = res.body?.error;
			publishError = PUBLISH_ERRORS[code]?.(res.body) ?? res.body?.detail ?? 'Publish failed.';
		} else {
			publishResult = res.body;
			// Only when the bucket actually gained objects. `window.open` after an await is outside
			// the click's task, so a strict blocker may refuse it; `uiBlocked` then shows a link.
			if (flociAutoOpen.enabled && shouldOpenFlociUi(target, res.body)) openFlociUi();
		}
		await refreshStatus();
		await refreshRows();
	}

	// ── The Floci UI ──────────────────────────────────────────────────────────────────
	// The destination is the storage explorer on the UI container's own port (:4500), but that
	// container is created only by the poller page, so until the backend confirms `ready` the
	// link falls back to the poller, which always renders.
	let uiTarget = $state(null);
	let uiBlocked = $state(false);
	const flociEndpoint = $derived(env?.endpoint_url ?? 'http://127.0.0.1:4566');
	const flociUi = $derived(uiTarget?.url ?? flociUiUrl(env?.endpoint_url));
	const apiDown = $derived(envList?.api_reachable === false || status?.api_reachable === false);
	// floci's S3 and DynamoDB share one endpoint, so the table probe doubles as the liveness check.
	const flociDown = $derived(isFloci && !!status && status.endpoint_reachable === false);

	let warming = false;
	async function warmFlociUi() {
		if (warming || !isFloci || status?.endpoint_reachable !== true) return;
		warming = true;
		try {
			uiTarget = await flociUiTarget();
		} finally {
			warming = false;
		}
	}

	// NO 'noopener' in the features string: per spec `window.open` then returns null on success,
	// which is the only signal a popup blocker gives. The visible <a> keeps rel="noopener".
	function openFlociUi() {
		const win = window.open(flociUi, '_blank');
		uiBlocked = !win;
		return !!win;
	}

	// EVERY branch names Docker, matching the backend's 502; they differ only in what to DO.
	const flociDownMessage = $derived(
		apiDown
			? `The ARCHiveNetwork API isn't answering, so whether floci is up can't be checked ` +
					`from here. Start the backend, then Re-check.`
			: !docker?.available
				? `Docker isn't running. Floci needs it. Start Docker Desktop, then bring the ` +
					`container up with \`docker compose up -d\`, then Re-check. Expected at ${flociEndpoint}.`
				: docker.running
					? `Docker is running the floci container, but nothing is answering at ` +
						`${flociEndpoint}. Something else may be holding the port, or the endpoint in ` +
						`environments.local.toml points elsewhere. Try Restart below, then Re-check.`
					: `Docker is running, but its floci container isn't, so there's nowhere to publish ` +
						`yet. Start it and this clears itself once the emulator answers - no terminal ` +
						`needed. Expected at ${flociEndpoint}.`
	);

	// ── The floci container's lifecycle ───────────────────────────────────────────────
	// Offered only when the backend reports Docker is genuinely usable, so the message above is
	// still the honest fallback when it isn't.
	let docker = $state(null); // null while first loading
	let dockerError = $state('');
	let dockerOutput = $state(''); // the command's own tail, shown only when it failed
	// When the emulator is down *and* the container is stopped, the warning owns Start.
	const bannerOwnsStart = $derived(flociDown && !!docker?.available && !docker.running);
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

	/** Poll until floci answers. The container reports "running" a beat before floci binds
	 *  :4566, so a single re-probe right after `up -d` would re-arm the warning. */
	async function waitForFloci(tries = 12) {
		for (let i = 0; i < tries; i += 1) {
			await refreshStatus();
			if (status?.endpoint_reachable) return true;
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
			await refreshStatus();
			// The deep link is only trustworthy while floci can vouch for it — re-warm, don't assume.
			uiTarget = null;
		} else if (await waitForFloci()) {
			await warmFlociUi();
		}
		busy = '';
	}

	// ── Curation ──────────────────────────────────────────────────────────────────────
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

	// ── Tables ────────────────────────────────────────────────────────────────────────
	let table = $state('media');
	let offset = $state(0);
	/** @type {{type: string, total: number, limit: number, offset: number, rows: Record<string, any>[]} | null} */
	let rows = $state(null);
	let rowsError = $state(''); // why the last rows request failed, shown in place of the skeleton
	// A device flow started in this mount locks the env picker, so its approval is never orphaned.
	let signInPending = $state(false);
	// The table shows curated columns; JSON shows each item whole (index keys, overrides, loaded_at).
	let view = $state('table');
	const LIMIT = 10;

	async function refreshStatus() {
		const target = env;
		if (!target) return;
		// Never signed in: asking would only earn a 401 and a misleading "expired" message.
		if (!signedIn) {
			status = { error: 'signed_out' };
			return;
		}
		let next;
		try {
			next = await devStatus(target.name);
		} catch {
			next = { api_reachable: false, enabled: true, endpoint_reachable: false };
		}
		if (envChoice.name !== target.name) return;
		// markExpired has already re-run this and set the signed-out status.
		if (checkSignedOut(target.name, next)) return;
		status = next;
	}

	// A probe's `tables` holds only the probed kinds: all 11 on floci, the 5 loader tables on AWS.
	const tableTotal = (p) => Object.keys(p?.tables ?? {}).length;
	const missingNames = (p) => (p?.missing ?? []).map((k) => p.tables?.[k] ?? k).join(', ');

	/** The explicit "is it there?" check. Re-reads the probe that /api/dev/status carries. */
	async function checkTable() {
		busy = 'table-status';
		tableError = '';
		tableNotice = '';
		const found = await devTables(env.name);
		if (checkSignedOut(env.name, found)) tableError = EXPIRED;
		else if (!found.endpoint_reachable) tableError = found.reason ?? "Can't reach DynamoDB.";
		else if (found.refused) tableError = found.reason ?? 'DynamoDB refused the request.';
		else
			tableNotice = found.table_exists
				? `All ${tableTotal(found)} tables exist under "${found.prefix}".`
				: `DynamoDB is up, but ${found.missing.length} of ${tableTotal(found)} tables are missing: ${missingNames(found)}.`;
		await refreshStatus();
		busy = '';
	}

	// Create/reset/delete, then re-read status: each changes what the rest of the panel may
	// offer, and a reset or delete takes every item with it.
	async function runTable(action, key, describe) {
		busy = key;
		tableError = '';
		tableNotice = '';
		report = null;
		error = '';
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
			() => devTablesCreate(env.name, false),
			'table-create',
			(b) =>
				b.created?.length
					? `Created ${b.created.length} tables.`
					: `All ${tableTotal(b)} tables were already there.`
		);

	const resetTable = () =>
		runTable(
			() => devTablesCreate(env.name, true),
			'table-reset',
			() => 'Reset all 11 tables; they are empty.'
		);

	const deleteTable = () =>
		runTable(
			() => devTablesDelete(env.name),
			'table-delete',
			(b) => (b.deleted?.length ? `Deleted ${b.deleted.length} tables.` : 'The tables were already gone.')
		);

	async function refreshRows() {
		const target = env;
		if (!ready || !target) {
			rows = null;
			rowsError = '';
			return;
		}
		let res;
		try {
			res = await devRows(target.name, table, LIMIT, offset);
		} catch {
			res = { ok: false, status: 0, body: { detail: "Couldn't reach the API." } };
		}
		if (envChoice.name !== target.name) return;
		// A failure is a message, never the loading skeleton: that would pulse forever.
		rowsError = res.ok
			? ''
			: checkSignedOut(target.name, res)
				? EXPIRED
				: (res.body?.detail ?? `HTTP ${res.status}`);
		rows = res.ok ? res.body : null;
	}

	async function runValidate() {
		busy = 'validate';
		report = null;
		error = '';
		const res = await devValidate(env.name);
		if (checkSignedOut(env.name, res)) error = EXPIRED;
		else if (!res.ok) error = res.body?.detail ?? 'Validation could not run.';
		else report = res.body;
		busy = '';
	}

	// ── Switching env ─────────────────────────────────────────────────────────────────
	/** Results belong to the env they came from, so a switch clears them and re-probes. */
	async function selectEnv(name) {
		envChoice.set(name);
		publishResult = null;
		publishError = '';
		report = null;
		error = '';
		tableError = '';
		tableNotice = '';
		rows = null;
		rowsError = '';
		offset = 0;
		status = null;
		uiTarget = null;
		uiBlocked = false;
		signInPending = false; // the old env's sign-in row unmounts with its poll
		await refreshStatus();
		await warmFlociUi();
	}

	/** Re-list the envs. Only the mount's first call reads the stored choice; later ones keep this
	 *  tab's own pick, and a pick the list no longer allows goes through a full switch. */
	async function refreshEnvs({ initial = false } = {}) {
		const before = envChoice.name;
		envList = await listEnvs();
		// A fresh list is the authoritative login answer, and dev and prod can share one login,
		// so the 401 overrides (which only patch a stale list) all go.
		expired = {};
		const next = envChoice.reconcile(envList, { fromStorage: initial });
		if (!initial && next !== before) await selectEnv(next);
	}

	async function onSignedIn() {
		await refreshEnvs();
		await refreshStatus();
	}

	async function onSignedOut() {
		await refreshEnvs();
		await refreshStatus();
	}

	onMount(async () => {
		refreshDocker();
		if (readyBuild === undefined) refreshBuild(); // the gallery's prop already carries it
		await refreshEnvs({ initial: true });
		await refreshStatus();
		await warmFlociUi();
	});

	// Re-page / re-type whenever the browser's inputs change, and once the tables appear.
	$effect(() => {
		void table;
		void offset;
		void ready;
		refreshRows();
	});

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

<!-- Every probed table with its item count; a missing one says so in words, not only colour.
     Counts arrive only once every table exists, so a partial set shows "—" beside the present ones. -->
{#snippet tableList()}
	<ul
		class="grid grid-cols-1 gap-px border-b border-surface-200 bg-surface-200 sm:grid-cols-2 lg:grid-cols-3"
		data-testid="table-list"
		aria-label="DynamoDB tables"
	>
		{#each Object.entries(status.tables ?? {}) as [kind, name] (kind)}
			{@const gone = status.missing?.includes(kind)}
			<li class="flex items-baseline justify-between gap-3 bg-surface-50 px-5 py-2">
				<code class="min-w-0 truncate font-mono text-xs text-surface-800" title={name}>{name}</code>
				{#if gone}
					<span class="shrink-0 text-xs font-semibold text-warning-700">missing</span>
				{:else}
					<span class="shrink-0 font-mono text-xs tabular-nums text-surface-600"
						>{status.counts?.[kind] ?? '—'}</span
					>
				{/if}
			</li>
		{/each}
	</ul>
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

<!-- Scrollbar hidden to match every other inner scroll pane in the app. The pane still scrolls
     by wheel, trackpad and keyboard. -->
<div class="flex h-full flex-col overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
	<div class="mx-auto w-full max-w-5xl px-6 pb-6">
		<header class="pt-6 pb-4">
			<h1 class="text-lg font-semibold text-surface-900">Dev Mode</h1>
			<p class="mt-1 max-w-prose text-sm leading-relaxed text-surface-600">
				Publishes this workspace's built <code
					class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800">ready/</code
				> folder to one environment: the images go to its bucket, the items to its DynamoDB tables,
				and both are checked afterwards. Your original export is never touched.
			</p>
		</header>

		<!-- ── Environment ──────────────────────────────────────────────────────────────
		     Sticky, so the banner stays in view while scrolling the tables: it is the
		     always-visible "you are not on floci". Same canvas colour as the body, so it reads
		     as part of the page rather than a floating glass bar. -->
		<div class="sticky top-0 z-10 -mx-6 mb-4 bg-surface-100 px-6 pt-1 pb-3" data-testid="env-bar">
			{#if envList === null}
				<div class="flex items-center gap-2.5 py-2">
					<span class="size-2.5 animate-pulse rounded-full bg-surface-400" aria-hidden="true"></span>
					<p class="text-sm text-surface-600">Loading environments…</p>
				</div>
			{:else if envList.api_reachable === false}
				<p
					class="rounded-lg border border-error-200 bg-error-50 px-3 py-2 text-sm text-error-800"
					role="alert"
				>
					The ARCHiveNetwork API isn't answering, so the environments can't be listed. Start the
					backend, then reload this page.
				</p>
			{:else}
				<EnvPicker
					envs={envList.envs}
					selected={envChoice.name}
					disabled={busy !== '' || signInPending}
					onSelect={selectEnv}
				/>
				{#if env && env.kind !== 'floci'}
					<div class="mt-3"><EnvBanner {env} identity={signedIn ? env.identity : null} /></div>
				{/if}
			{/if}

			{#if envList?.stale_settings?.length || envList?.errors?.length}
				<div
					class="mt-3 rounded-lg border border-warning-300 bg-warning-50 px-3 py-2 text-xs leading-relaxed text-warning-900"
					data-testid="env-notices"
				>
					{#if envList.stale_settings?.length}
						<p>
							These <code class="font-mono">.env</code> lines are no longer read — move them to
							<code class="font-mono">environments.local.toml</code> and delete them:
							{#each envList.stale_settings as name, i (name)}<code class="font-mono font-semibold"
									>{name}</code
								>{i < envList.stale_settings.length - 1 ? ', ' : '.'}{/each}
						</p>
					{/if}
					{#if envList.errors?.length}
						<p class={envList.stale_settings?.length ? 'mt-1.5' : ''}>
							<span class="font-semibold">environments.local.toml has problems</span>, so its envs are
							skipped and the committed ones still work:
						</p>
						<ul class="mt-1 list-disc pl-5 font-mono">
							{#each envList.errors as problem (problem)}<li class="break-words">{problem}</li>{/each}
						</ul>
					{/if}
				</div>
			{/if}
		</div>

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
						Next: build the ready folder from the gallery, then publish it below.
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

		{#if env}
			<!-- ── Publish ───────────────────────────────────────────────────────────────
			     One button replaces the old Upload and Load: the same run stores the bytes first,
			     then the items, then checks both. The card stays neutral; the banner above
			     carries the AWS / prod tone so it is never out of sight. -->
			<section class="mb-4 rounded-xl border border-surface-300 bg-surface-50" aria-label="Publish">
				{#if !isFloci}
					<div class="border-b border-surface-200 p-5">
						{#key env.name}
							<EnvSignIn
								{env}
								login={expired[env.name] ? 'signed_out' : (env.login ?? (signedIn ? 'signed_in' : 'signed_out'))}
								onPendingChange={(p) => (signInPending = p)}
								identity={env.identity}
								notice={expired[env.name] ? EXPIRED : ''}
								onSignIn={onSignedIn}
								onSignOut={onSignedOut}
							/>
						{/key}
					</div>
				{/if}

				<div class="p-5">
					<div class="flex flex-wrap items-start justify-between gap-3">
						<div class="max-w-prose">
							<h2 class="text-sm font-semibold text-surface-900">Publish to {env.label}</h2>
							<p class="mt-1 text-xs leading-relaxed text-surface-600">
								Uploads the built media to
								<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
									>s3://{env.s3_bucket}</code
								>, upserts the items into
								<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
									>{env.table_prefix}-*</code
								>, then verifies both landed. Re-running is safe: objects already there are skipped,
								and CMS edits and deletions are never overwritten.
								{#if isFloci}
									Nothing leaves your machine. Browse the bucket with
									<span class="whitespace-nowrap">{@render flociUiLink('Floci UI')}.</span>
								{/if}
							</p>
						</div>
						<div class="flex flex-col items-end gap-1.5">
							{@render primaryBtn(
								`Publish to ${env.label}`,
								'Publishing…',
								'publish',
								startPublish,
								!publishable
							)}
							{#if publishBlocker && busy === ''}
								<p class="max-w-56 text-right text-xs text-surface-600">{publishBlocker}</p>
							{/if}
						</div>
					</div>

					{#if flociDown}
						<!-- warning-100 so the band still separates from the card. Worded as information. -->
						<div
							class="mt-4 flex flex-wrap items-start justify-between gap-3 rounded-lg border border-warning-400 bg-warning-100 px-3 py-2"
							role="status"
						>
							<p class="max-w-prose text-sm text-warning-800">{flociDownMessage}</p>
							<div class="flex shrink-0 flex-wrap items-center gap-2">
								<!-- The one place a second green button may sit near Publish: while the emulator
								     is down, Publish is disabled, so nothing is competing. -->
								{#if bannerOwnsStart}
									{@render primaryBtn(
										docker.exists ? 'Start floci' : 'Create and start floci',
										'Starting…',
										'docker-start',
										() => runDocker('start')
									)}
								{/if}
								<!-- Never gated on `busy`: this is always the way out of a disabled Publish. -->
								<button
									type="button"
									onclick={refreshStatus}
									class="rounded-lg border border-warning-400 bg-surface-50 px-3 py-1.5 text-sm font-medium text-warning-800 transition-colors hover:bg-warning-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
									>Re-check</button
								>
							</div>
						</div>
					{/if}

					<!-- The floci container: a hairline strip, not a nested card. Verbs are rendered by
					     state rather than disabled, and only when Docker is genuinely usable. -->
					{#if isFloci && docker?.available}
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
								<!-- Named for the image, because "Rebuild" alone would read as "rebuild my ready folder". -->
								{@render secondaryBtn('Rebuild image', 'Rebuilding…', 'docker-rebuild', () =>
									runDocker('rebuild')
								)}
							</div>
						</div>

						<p class="mt-2 text-xs leading-relaxed text-surface-600">
							Rebuild re-pulls <code class="rounded bg-surface-200 px-1 py-0.5 font-mono"
								>floci/floci</code
							> and re-creates the container. Published objects live in
							<code class="rounded bg-surface-200 px-1 py-0.5 font-mono">workspace/floci-data/</code> and
							survive all four actions.
						</p>

						{#if dockerError}
							<div class="mt-3 rounded-lg border border-error-200 bg-error-50 px-3 py-2" role="alert">
								<p class="text-sm text-error-800">{dockerError}</p>
								{#if dockerOutput}
									<pre
										class="mt-2 max-h-40 overflow-auto rounded bg-surface-100 p-2 font-mono text-xs leading-relaxed text-surface-700">{dockerOutput}</pre>
								{/if}
							</div>
						{/if}
					{/if}

					<!-- The tab is the reassurance that the publish landed somewhere real, so it is on by
					     default, but anything that opens a window has to be refusable. -->
					{#if isFloci}
						<label
							class="mt-3 flex w-fit cursor-pointer items-center gap-2 text-xs text-surface-700 select-none"
						>
							<input
								type="checkbox"
								checked={flociAutoOpen.enabled}
								onchange={(event) => flociAutoOpen.set(event.currentTarget.checked)}
								class="size-3.5 rounded border-surface-400 accent-primary-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
							/>
							Open the Floci UI after a Publish that adds new objects
						</label>
					{/if}

					{#if publishError}
						<p
							class="mt-4 rounded-lg border border-error-200 bg-error-50 px-3 py-2 text-sm text-error-800"
							role="alert"
						>
							{publishError}
						</p>
					{/if}

					{#if publishResult}
						<div class="mt-4"><PublishResult result={publishResult} /></div>
						{#if isFloci}
							<p class="mt-2 text-xs text-surface-600">{@render flociUiLink('View in Floci UI')}</p>
						{/if}
						{#if uiBlocked}
							<p class="mt-1 text-xs text-surface-600" role="status">
								Your browser blocked the new tab — open the Floci UI with the link above.
							</p>
						{/if}
					{/if}
				</div>
			</section>

		{/if}

		{#if env}
		<!-- One panel, hairline-divided. Not four floating cards. -->
		<div class="overflow-hidden rounded-xl border border-surface-300 bg-surface-50">
			<!-- ── Status ───────────────────────────────────────────────── -->
			<section class="flex flex-wrap items-start justify-between gap-4 p-5">
				{#if status === null}
					<div class="flex items-center gap-2.5">
						<span class="size-2.5 animate-pulse rounded-full bg-surface-400" aria-hidden="true"></span>
						<p class="text-sm text-surface-600">Checking the tables…</p>
					</div>
				{:else if status.error === 'signed_out'}
					<div class="flex items-center gap-2.5">
						<span class="size-2.5 rounded-full bg-surface-400" aria-hidden="true"></span>
						<p class="text-sm text-surface-700">Sign in to {env.label} to see its tables.</p>
					</div>
				{:else if status.error || !status.enabled}
					<!-- A structured refusal (access denied, not configured) or an unexpected body. -->
					<div class="max-w-prose">
						<div class="flex items-center gap-2.5">
							<span class="size-2.5 rounded-full bg-error-500" aria-hidden="true"></span>
							<p class="text-sm font-medium text-surface-900">Can't read this environment's tables</p>
						</div>
						<p class="mt-2 font-mono text-xs leading-relaxed break-words text-error-700">
							{status.detail ?? status.reason ?? status.error ?? 'The status check failed.'}
						</p>
					</div>
					{@render secondaryBtn('Check status', 'Checking…', 'table-status', checkTable)}
				{:else if !status.endpoint_reachable || status.refused || !status.table_exists}
					<!-- An unreachable endpoint, a refusal and missing tables each need a different fix,
					     and only the last is one this panel can make (on floci) — so only it earns Create. -->
					{@const missing = status.endpoint_reachable && !status.refused}
					{@const total = tableTotal(status)}
					{@const gone = status.missing?.length ?? 0}
					<div class="max-w-prose">
						<div class="flex items-center gap-2.5">
							<span
								class="size-2.5 rounded-full {missing ? 'bg-warning-500' : 'bg-error-500'}"
								aria-hidden="true"
							></span>
							<p class="text-sm font-medium text-surface-900">
								{#if missing && gone < total}
									{gone} of {total} tables {gone === 1 ? 'is' : 'are'} missing
								{:else if missing}
									The tables don't exist yet
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
								is up, but {gone === 1 ? 'this table is' : 'these tables are'} missing:
								<code
									class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs break-words text-surface-800"
									>{missingNames(status)}</code
								>.
								{isFloci
									? 'Create them here.'
									: "On AWS they're created by hand, per the AWS guide, not from this panel."}
							{:else if status.refused}
								<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>{status.endpoint}</code
								>
								answered but refused to describe the
								<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>{status.prefix}-*</code
								> tables. Check that your sign-in's role has the permissions in the AWS guide.
							{:else if isFloci && docker?.available}
								<!-- Docker can be driven from the panel, so the controls above are the fix, not a terminal. -->
								Nothing answered at <code
									class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>{status.endpoint}</code
								>. Start floci with the Docker controls above, then check again.
							{:else if isFloci}
								Nothing answered at <code
									class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>{status.endpoint}</code
								>. Start floci with <code
									class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>docker compose up -d</code
								>, then check again.
							{:else}
								<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-xs text-surface-800"
									>{status.endpoint}</code
								> did not answer with this sign-in.
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
						{#if missing && isFloci}
							{@render primaryBtn('Create tables', 'Creating…', 'table-create', createTable)}
						{/if}
					</div>
				{:else}
					<div>
						<div class="flex items-center gap-2.5">
							<span class="size-2.5 rounded-full bg-success-500" aria-hidden="true"></span>
							<p class="text-sm font-medium text-surface-900">Connected</p>
						</div>
						<p class="mt-2 text-xs text-surface-600">
							{tableTotal(status)} tables <code
								class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>{status.prefix}-*</code
							>
							· endpoint
							<code class="rounded bg-surface-200 px-1 py-0.5 font-mono text-surface-800"
								>{status.endpoint}</code
							>
						</p>
					</div>
					<div class="flex flex-wrap justify-end gap-2">
						{@render secondaryBtn('Check status', 'Checking…', 'table-status', checkTable)}
						<!-- Table admin is emulator-only (the backend 409s on AWS, where tables are made by
						     hand). Delete sits last behind a named confirm: the widest blast radius here. -->
						{#if isFloci}
							{@render secondaryBtn('Reset tables', 'Resetting…', 'table-reset', () => (confirmReset = true))}
							{@render secondaryBtn(
								'Delete tables',
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
				{@render tableList()}


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

					{#if rowsError}
						<div
							class="mt-4 rounded-lg border border-error-200 bg-error-50 px-4 py-3"
							role="alert"
							data-testid="rows-error"
						>
							<p class="text-sm font-medium text-error-800">
								The <code class="font-mono text-xs">{table}</code> items couldn't be read.
							</p>
							<p class="mt-1 font-mono text-xs break-words text-error-800">{rowsError}</p>
						</div>
					{:else if rows === null}
						<!-- Skeleton, not a spinner: the shape of what's coming. -->
						<div
							class="mt-4 space-y-px overflow-hidden rounded-lg bg-surface-200"
							data-testid="rows-skeleton"
						>
							{#each Array(5) as _, i (i)}
								<div class="h-11 animate-pulse bg-surface-100"></div>
							{/each}
						</div>
					{:else if rows.total === 0}
						<div class="mt-4 rounded-lg border border-dashed border-surface-300 px-4 py-8 text-center">
							<p class="text-sm font-medium text-surface-800">No items yet</p>
							<p class="mt-1 text-sm text-surface-600">
								Publish above to populate <code class="font-mono text-xs">{table}</code> items.
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
														{#if row.preview_url}
															<img
																src={row.preview_url}
																alt=""
																loading="lazy"
																width="36"
																height="36"
																class="size-9 min-w-9 rounded object-cover ring-1 ring-surface-300"
															/>
														{:else}
															<!-- No storage_path, so no presigned link: an empty frame, not a broken image. -->
															<span
																class="block size-9 min-w-9 rounded bg-surface-200 ring-1 ring-surface-300"
																title="No stored file"
															></span>
														{/if}
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
				<div class="border-t border-surface-200">{@render tableList()}</div>
				<div class="px-5 py-8 text-center">
					<p class="text-sm font-medium text-surface-800">Some tables aren't there yet</p>
					<p class="mx-auto mt-1 max-w-prose text-sm text-surface-600">
						{isFloci ? 'Create' : 'Make'} <code class="font-mono text-xs">{missingNames(status)}</code> to
						start publishing this workspace.
					</p>
				</div>
			{/if}
		</div>
		{/if}
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
	title="Reset the tables?"
	message="This deletes all 11 {status?.prefix}-* tables and recreates them empty. Items are lost, including any simulated CMS edits; the files already in the object store are left alone. Your export and ready folder are untouched."
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
	title="Delete the {status?.prefix}-* tables?"
	message="This deletes all 11 tables and every item in them. The files already in the object store, your export, and your ready folder are all left alone. You can create them again from this panel."
	confirmLabel="Delete tables"
	cancelLabel="Cancel"
	destructive
	onConfirm={() => {
		confirmDeleteTable = false;
		deleteTable();
	}}
	onCancel={() => (confirmDeleteTable = false)}
/>

<!-- Every confirm env, on every Publish: the typed word is sent as `confirm`, so the server's
     backstop checks the very value the volunteer typed. -->
<TypeToConfirmDialog
	open={confirmPublish}
	word={env?.name ?? ''}
	title="Publish to {env?.name}?"
	details={confirmDetails}
	confirmLabel="Publish to {env?.name}"
	onConfirm={(typed) => {
		confirmPublish = false;
		runPublish(typed);
	}}
	onCancel={() => (confirmPublish = false)}
/>
