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
