// Dev-mode is a *UI preference* — it only reveals the Dev panel. The backend independently
// decides whether dev-mode is usable: every /api/dev/* route 404s unless ARCHIVENETWORK_DATABASE_URL
// is set. So flipping this on without a database is harmless; the panel just says "not configured".
const KEY = 'archive-dev-mode';

function read() {
	if (typeof localStorage === 'undefined') return false;
	return localStorage.getItem(KEY) === 'true';
}

let enabled = $state(read());

export const devMode = {
	get enabled() {
		return enabled;
	},
	set(value) {
		enabled = !!value;
		if (typeof localStorage !== 'undefined') localStorage.setItem(KEY, String(enabled));
	},
	toggle() {
		this.set(!enabled);
	}
};
