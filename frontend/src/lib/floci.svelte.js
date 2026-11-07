// --- The Floci UI -----------------------------------------------------------------------
// floci does not serve its UI in-process: `/_floci/ui` is a poller that waits on
// `/_floci/ui/status`, which floci answers by starting the `floci/floci-ui` container on
// port 4500 through the host container runtime. So the UI lives under the SAME endpoint as
// the S3 API, and needs the docker.sock bind-mount `docker-compose.yml` carries.

/** The poller page. Not the destination — the *cold-start* path: it is the only thing that
 *  creates the sibling container, and it always renders something, so it is what the panel
 *  links to until the UI is confirmed up. Falls back to the documented default so the link is
 *  never `undefined/_floci/ui` during the first paint, before /api/envs has answered. */
export function flociUiUrl(endpointUrl) {
	const base = String(endpointUrl || 'http://127.0.0.1:4566').replace(/\/+$/, '');
	return `${base}/_floci/ui`;
}

/** Whether a Publish result is worth opening the Floci UI for.
 *
 *  "Already published" is exactly `files_stored === 0`: every object was skipped because it was
 *  already in the bucket, so a new tab would show the volunteer nothing they did not already
 *  have. A first publish stores new keys, and so does the first one after a re-autocurate — a
 *  different selection builds a different ready folder, whose photos are keys the bucket has
 *  never seen. AWS envs never auto-open: they have no local UI. */
export function shouldOpenFlociUi(env, result) {
	return env?.kind === 'floci' && (result?.steps?.publish?.files_stored ?? 0) > 0;
}

const AUTO_KEY = 'archive-floci-autoopen';

function readAuto() {
	// Default ON: the tab is the confirmation that the publish landed somewhere real, which is
	// exactly the reassurance this tool trades on. Opt out, never opt in.
	try {
		return localStorage.getItem(AUTO_KEY) !== 'off';
	} catch {
		return true; // blocked storage throws on access; it runs at import, so it must not escape
	}
}

let auto = $state(readAuto());

export const flociAutoOpen = {
	get enabled() {
		return auto;
	},
	set(value) {
		auto = !!value;
		try {
			localStorage.setItem(AUTO_KEY, auto ? 'on' : 'off');
		} catch {
			// The preference just doesn't survive a reload.
		}
	}
};
