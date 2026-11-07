// Which named environment the Dev panel writes to. A *UI preference*, like devMode: the backend
// never remembers it, and every env-scoped request names it, so two tabs can never disagree.
//
// The value is only trusted after `reconcile` checks it against the server's list. Until then it
// is 'local', and a stale or unusable stored name falls back to the server's default (always a
// floci env), so a fresh or out-of-date browser is never armed at AWS.
const KEY = 'archive-env';
const INITIAL = 'local';

function readStored() {
	try {
		return localStorage.getItem(KEY);
	} catch {
		return null;
	}
}

function writeStored(value) {
	try {
		localStorage.setItem(KEY, value);
	} catch {
		// Private windows and blocked storage: the choice just doesn't survive a reload.
	}
}

/** `stored` if it names a listed, configured env; otherwise the server's default. */
export function pickEnv(stored, list) {
	const fallback = list?.default ?? INITIAL;
	const hit = (list?.envs ?? []).find((e) => e.name === stored);
	return hit && hit.configured ? stored : fallback;
}

let name = $state(INITIAL);

export const envChoice = {
	get name() {
		return name;
	},
	set(value) {
		name = value;
		writeStored(value);
	},
	/** Settle the choice against a `/api/envs` body and return it. */
	reconcile(list) {
		const stored = readStored();
		name = pickEnv(stored, list);
		// The offline fallback lists no envs; overwriting the stored choice then would forget a
		// perfectly good preference just because the API was briefly down.
		if (list?.api_reachable !== false && stored !== name) writeStored(name);
		return name;
	}
};

/** How loudly the panel should say "you are not on floci". */
export function bannerTone(env) {
	if (!env || env.kind === 'floci') return 'none';
	return env.confirm ? 'prod' : 'aws';
}

/** Whether Publish may be offered. Sign-in gates only AWS envs; floci uses dummy keys. */
export function canPublish(env, { built, signedIn, tablesReady, busy } = {}) {
	if (!env || env.configured === false) return false;
	if (env.kind !== 'floci' && !signedIn) return false;
	return !!built && !!tablesReady && !busy;
}
