// Which object store the Dev panel's Upload writes to. A *UI preference* like devMode —
// the backend never remembers it. The target is named on every request instead, so it is
// unambiguous at the moment Upload is clicked and two tabs can never disagree.
//
// The default is 'floci' on purpose: a fresh browser, a cleared profile, or a machine that
// has never run this app is armed at the emulator, never at production.
const KEY = 'archive-s3-target';
const TARGETS = ['floci', 'aws'];

function read() {
	if (typeof localStorage === 'undefined') return 'floci';
	const stored = localStorage.getItem(KEY);
	return TARGETS.includes(stored) ? stored : 'floci';
}

let target = $state(read());

export const s3Target = {
	get target() {
		return target;
	},
	set(value) {
		target = TARGETS.includes(value) ? value : 'floci';
		if (typeof localStorage !== 'undefined') localStorage.setItem(KEY, target);
	},
	toggle() {
		this.set(target === 'floci' ? 'aws' : 'floci');
	}
};

/** Whether Upload should be offered for `target`, given a /api/s3/status body.
 *  Floci is gated on liveness; AWS is gated only on configuration — the floci probe must
 *  never be able to block an AWS upload. */
export function canUpload(target, s3) {
	if (!s3) return false;
	if (target === 'aws') return s3.aws?.enabled === true;
	return s3.floci?.enabled === true && s3.floci?.reachable === true;
}

// --- The Floci UI -----------------------------------------------------------------------
// floci does not serve its UI in-process: `/_floci/ui` is a poller that waits on
// `/_floci/ui/status`, which floci answers by starting the `floci/floci-ui` container on
// port 4500 through the host container runtime. So the UI lives under the SAME endpoint as
// the S3 API, and needs the docker.sock bind-mount `docker-compose.yml` carries.

/** The poller page. Not the destination — the *cold-start* path: it is the only thing that
 *  creates the sibling container, and it always renders something, so it is what the panel
 *  links to until the UI is confirmed up. Falls back to the documented default so the link is
 *  never `undefined/_floci/ui` during the first paint, before /api/s3/status has answered. */
export function flociUiUrl(endpointUrl) {
	const base = String(endpointUrl || 'http://127.0.0.1:4566').replace(/\/+$/, '');
	return `${base}/_floci/ui`;
}

/** The destination proper: the storage explorer on the UI container's OWN port, which is
 *  where the uploaded objects are — not the console's generic landing page.
 *
 *  The port is hard-coded rather than derived because the UI is a *separate container*; only
 *  the host is shared with the S3 endpoint. A deep link is dead until that container exists,
 *  so nothing should use this without first confirming readiness (`/api/docker/floci-ui`). */
export function flociExplorerUrl(endpointUrl) {
	const { protocol, hostname } = parseEndpoint(endpointUrl);
	return `${protocol}//${hostname}:4500/cloud-explorer/aws/storage`;
}

function parseEndpoint(endpointUrl) {
	try {
		const url = new URL(String(endpointUrl || 'http://127.0.0.1:4566'));
		return { protocol: url.protocol, hostname: url.hostname };
	} catch {
		return { protocol: 'http:', hostname: '127.0.0.1' };
	}
}

/** Whether an upload is worth opening the Floci UI for.
 *
 *  "There is already a build uploaded" is exactly `uploaded === 0`: every object was skipped
 *  because it was already in the bucket, so a new tab would show the volunteer nothing they
 *  did not already have. A first upload writes new keys, and so does the first upload after a
 *  re-autocurate — a different selection builds a different ready folder, whose photos are
 *  keys the bucket has never seen. AWS never auto-opens: it has no local UI to open. */
export function shouldOpenFlociUi(target, result) {
	return target === 'floci' && (result?.uploaded ?? 0) > 0;
}

const AUTO_KEY = 'archive-floci-autoopen';

function readAuto() {
	if (typeof localStorage === 'undefined') return true;
	// Default ON: the tab is the confirmation that the upload landed somewhere real, which is
	// exactly the reassurance this tool trades on. Opt out, never opt in.
	return localStorage.getItem(AUTO_KEY) !== 'off';
}

let auto = $state(readAuto());

export const flociAutoOpen = {
	get enabled() {
		return auto;
	},
	set(value) {
		auto = !!value;
		if (typeof localStorage !== 'undefined') localStorage.setItem(AUTO_KEY, auto ? 'on' : 'off');
	}
};
