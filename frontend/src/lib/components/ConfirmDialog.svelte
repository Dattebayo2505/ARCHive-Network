<script>
	import { trapFocus } from '$lib/focusTrap.js';
	/**
	 * A styled confirmation dialog that replaces window.confirm().
	 *
	 * Props:
	 *   open      — show/hide the dialog
	 *   title     — heading text
	 *   message   — body text (plain text)
	 *   confirmLabel — text on the confirm button (default "Yes")
	 *   cancelLabel  — text on the cancel button (default "No")
	 *   destructive — when true, the confirm action reads as dangerous (red);
	 *                 otherwise it's the solid-green primary action. Reserve red
	 *                 for genuinely irreversible actions (e.g. deleting a workspace).
	 *   onConfirm — called when the user clicks confirm
	 *   onCancel  — called when the user clicks cancel or presses Escape
	 */
	let {
		open = false,
		title = 'Are you sure?',
		message = '',
		confirmLabel = 'Yes',
		cancelLabel = 'No',
		destructive = false,
		onConfirm,
		onCancel
	} = $props();

	function handleKey(e) {
		if (e.key === 'Escape') onCancel?.();
	}

	function handleBackdrop(e) {
		if (e.target === e.currentTarget) onCancel?.();
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
		aria-labelledby="confirm-title"
		tabindex="-1"
		use:trapFocus
	>
		<div
			class="w-full max-w-sm overflow-hidden rounded-2xl border border-surface-300 bg-surface-50 shadow-xl animate-in"
		>
			<!-- Icon + heading -->
			<div class="flex items-start gap-3.5 p-6 pb-3">
				<span
					class="grid size-11 shrink-0 place-items-center rounded-full {destructive
						? 'bg-error-100 text-error-700'
						: 'bg-primary-100 text-primary-700'}"
					aria-hidden="true"
				>
					{#if destructive}
						<svg viewBox="0 0 24 24" class="size-6" fill="none" stroke="currentColor" stroke-width="2"
							stroke-linecap="round" stroke-linejoin="round">
							<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
							<line x1="12" y1="9" x2="12" y2="13" />
							<line x1="12" y1="17" x2="12.01" y2="17" />
						</svg>
					{:else}
						<svg viewBox="0 0 24 24" class="size-6" fill="none" stroke="currentColor" stroke-width="2"
							stroke-linecap="round" stroke-linejoin="round">
							<circle cx="12" cy="12" r="10" />
							<path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
							<line x1="12" y1="17" x2="12.01" y2="17" />
						</svg>
					{/if}
				</span>
				<div class="mt-0.5">
					<h2 id="confirm-title" class="text-lg font-semibold text-surface-900">{title}</h2>
					<p class="mt-1 text-sm leading-relaxed text-surface-600">{message}</p>
				</div>
			</div>

			<!-- Action buttons -->
			<div class="flex justify-end gap-3 border-t border-surface-200 px-6 py-4">
				<button
					type="button"
					class="rounded-lg px-4 py-2 text-sm font-medium text-surface-700 transition-colors hover:bg-surface-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
					onclick={() => onCancel?.()}
				>
					{cancelLabel}
				</button>
				<button
					type="button"
					class="rounded-lg px-4 py-2 text-sm font-semibold text-primary-50 shadow-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 {destructive
						? 'bg-error-600 hover:bg-error-700 focus-visible:outline-error-600'
						: 'bg-primary-700 hover:bg-primary-800 focus-visible:outline-primary-600'}"
					onclick={() => onConfirm?.()}
				>
					{confirmLabel}
				</button>
			</div>
		</div>
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
