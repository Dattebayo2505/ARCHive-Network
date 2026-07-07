// A Svelte action that makes an overlay behave like a real modal for keyboard
// and screen-reader users: on mount it moves focus into the dialog, keeps Tab /
// Shift+Tab cycling within it, and on unmount restores focus to whatever was
// focused before it opened. Apply with `use:trapFocus` on the dialog container
// (the element rendered inside `{#if open}` so mount/destroy track open/close).
//
// Escape-to-close stays the caller's job — with focus trapped inside, the
// backdrop's keydown handler now reliably receives the event.

const FOCUSABLE =
	'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]),' +
	' textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function trapFocus(node) {
	const previouslyFocused =
		typeof document !== 'undefined' ? document.activeElement : null;

	function focusable() {
		return Array.from(node.querySelectorAll(FOCUSABLE)).filter(
			(el) => el.offsetWidth > 0 || el.offsetHeight > 0 || el === document.activeElement
		);
	}

	function onKeydown(e) {
		if (e.key !== 'Tab') return;
		const items = focusable();
		if (items.length === 0) {
			e.preventDefault();
			node.focus();
			return;
		}
		const first = items[0];
		const last = items[items.length - 1];
		const active = document.activeElement;
		if (e.shiftKey && (active === first || !node.contains(active))) {
			e.preventDefault();
			last.focus();
		} else if (!e.shiftKey && (active === last || !node.contains(active))) {
			e.preventDefault();
			first.focus();
		}
	}

	// Move focus into the dialog. Fall back to the container itself (it carries
	// tabindex="-1") when nothing focusable has rendered yet.
	(focusable()[0] ?? node).focus();
	node.addEventListener('keydown', onKeydown);

	return {
		destroy() {
			node.removeEventListener('keydown', onKeydown);
			if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
				previouslyFocused.focus();
			}
		}
	};
}
