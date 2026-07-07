import { browser } from '$app/environment';

// Persisted light/dark preference for the ARCHive Network shell. The UI shipped
// light-only for a long time; dark mode is opt-in per-viewer and remembered.
// An explicit choice always wins; with no saved choice we follow the OS so the
// toggle feels native. The pre-paint init lives in `app.html` (no theme flash);
// this module keeps the class + `color-scheme` in sync after hydration and
// exposes a reactive `theme.mode` for the header toggle.
const KEY = 'archive-theme';

function systemPrefersDark() {
	return browser && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function readStored() {
	if (!browser) return null;
	try {
		const v = localStorage.getItem(KEY);
		return v === 'dark' || v === 'light' ? v : null;
	} catch {
		return null;
	}
}

function initialMode() {
	return readStored() ?? (systemPrefersDark() ? 'dark' : 'light');
}

function apply(mode) {
	if (!browser) return;
	const root = document.documentElement;
	root.classList.toggle('dark', mode === 'dark');
	// Flip native form controls, scrollbars, and the caret to match.
	root.style.colorScheme = mode;
}

export const theme = $state({ mode: initialMode() });

export function setTheme(mode) {
	if (mode !== 'dark' && mode !== 'light') return;
	theme.mode = mode;
	apply(mode);
	if (browser) {
		try {
			localStorage.setItem(KEY, mode);
		} catch {
			/* private mode / storage disabled — session-only is fine */
		}
	}
}

export function toggleTheme() {
	setTheme(theme.mode === 'dark' ? 'light' : 'dark');
}
