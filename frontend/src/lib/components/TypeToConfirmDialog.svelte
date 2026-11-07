<script>
	import { trapFocus } from '$lib/focusTrap.js';
	/**
	 * The strict confirm for a `confirm = true` environment: the button stays disabled until the
	 * field holds `word` exactly (case-sensitive, untrimmed), and paste is blocked so it is typed.
	 * Same shell, focus trap and Escape/backdrop handling as ConfirmDialog, in the error tone.
	 *
	 * Props:
	 *   open         — show/hide; the field is emptied every time it opens
	 *   word         — what must be typed (the env name)
	 *   title        — heading text
	 *   details      — [{label, value}] stating exactly what will be written
	 *   confirmLabel — the action, e.g. "Publish to prod" (never "OK")
	 *   onConfirm(typed) — receives the typed word, so the server can re-check the same value
	 *   onCancel     — Escape, backdrop click or Cancel
	 */
	let {
		open = false,
		word,
		title,
		details = [],
		confirmLabel,
		onConfirm,
		onCancel
	} = $props();

	let typed = $state('');
	// An empty word would make an empty field "match"; never arm the button on nothing.
	const matches = $derived(!!word && typed === word);

	// Nothing is remembered between publishes: a reopened dialog always starts empty.
	$effect.pre(() => {
		if (open) typed = '';
	});

	function handleKey(e) {
		if (e.key === 'Escape') onCancel?.();
	}

	function handleBackdrop(e) {
		if (e.target === e.currentTarget) onCancel?.();
	}

	function submit(e) {
		e.preventDefault();
		if (matches) onConfirm?.(typed);
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-[80] grid place-items-center bg-black/50 p-4 backdrop-blur-[1px]"
		onclick={handleBackdrop}
		onkeydown={handleKey}
		role="dialog"
		aria-modal="true"
		aria-labelledby="type-confirm-title"
		aria-describedby="type-confirm-lede"
		tabindex="-1"
		use:trapFocus
	>
		<form
			onsubmit={submit}
			class="animate-in w-full max-w-md overflow-hidden rounded-2xl border border-error-300 bg-surface-50 shadow-xl"
		>
			<div class="flex items-start gap-3.5 p-6 pb-4">
				<span
					class="grid size-11 shrink-0 place-items-center rounded-full bg-error-100 text-error-700"
					aria-hidden="true"
				>
					<svg viewBox="0 0 24 24" class="size-6" fill="none" stroke="currentColor" stroke-width="2"
						stroke-linecap="round" stroke-linejoin="round">
						<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
						<line x1="12" y1="9" x2="12" y2="13" />
						<line x1="12" y1="17" x2="12.01" y2="17" />
					</svg>
				</span>
				<div class="mt-0.5 min-w-0">
					<h2 id="type-confirm-title" class="text-lg font-semibold text-surface-900">{title}</h2>
					<p id="type-confirm-lede" class="mt-1 text-sm leading-relaxed text-surface-600">
						This writes to a live environment. Check every line below before you confirm.
					</p>
				</div>
			</div>

			<!-- Exactly what will be written. Hairline rows, not a card: the dialog is the card. -->
			<dl class="mx-6 divide-y divide-surface-200 rounded-lg border border-surface-200">
				{#each details as d (d.label)}
					<div class="flex items-baseline justify-between gap-4 px-3 py-2">
						<dt class="shrink-0 text-xs font-medium text-surface-600">{d.label}</dt>
						<dd class="min-w-0 text-right font-mono text-xs break-all text-surface-900">{d.value}</dd>
					</div>
				{/each}
			</dl>

			<div class="px-6 pt-4 pb-5">
				<label for="type-confirm-input" class="block text-sm text-surface-800">
					Type <code
						class="rounded bg-error-50 px-1.5 py-0.5 font-mono text-sm font-semibold text-error-800"
						>{word}</code
					> to confirm.
				</label>
				<!-- Paste is blocked on purpose: the point is that the name was read, not copied. -->
				<input
					id="type-confirm-input"
					type="text"
					bind:value={typed}
					onpaste={(e) => e.preventDefault()}
					ondrop={(e) => e.preventDefault()}
					autocomplete="off"
					autocapitalize="off"
					spellcheck="false"
					class="mt-2 w-full rounded-lg border border-surface-300 bg-surface-50 px-3 py-2 font-mono text-sm text-surface-900 transition-colors placeholder:text-surface-500 focus-visible:border-error-500 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-error-500"
				/>
			</div>

			<div class="flex justify-end gap-3 border-t border-surface-200 px-6 py-4">
				<button
					type="button"
					class="rounded-lg px-4 py-2 text-sm font-medium text-surface-700 transition-colors hover:bg-surface-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
					onclick={() => onCancel?.()}
				>
					Cancel
				</button>
				<button
					type="submit"
					disabled={!matches}
					class="rounded-lg bg-error-600 px-4 py-2 text-sm font-semibold text-primary-50 shadow-sm transition-colors hover:bg-error-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-error-600 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-error-600"
				>
					{confirmLabel}
				</button>
			</div>
		</form>
	</div>
{/if}

<style>
	.animate-in {
		animation: dialog-enter 0.15s ease-out;
	}

	@keyframes dialog-enter {
		from {
			opacity: 0;
			transform: scale(0.95) translateY(4px);
		}
		to {
			opacity: 1;
			transform: scale(1) translateY(0);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.animate-in {
			animation: none;
		}
	}
</style>
