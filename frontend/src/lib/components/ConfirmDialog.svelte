<script>
	/**
	 * A styled confirmation dialog that replaces window.confirm().
	 *
	 * Props:
	 *   open      — show/hide the dialog
	 *   title     — heading text
	 *   message   — body text (supports HTML via {@html})
	 *   confirmLabel — text on the confirm button (default "Yes")
	 *   cancelLabel  — text on the cancel button (default "No")
	 *   onConfirm — called when the user clicks confirm
	 *   onCancel  — called when the user clicks cancel or presses Escape
	 */
	let {
		open = false,
		title = 'Are you sure?',
		message = '',
		confirmLabel = 'Yes',
		cancelLabel = 'No',
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
		class="fixed inset-0 z-[80] grid place-items-center bg-surface-950/50 p-4 backdrop-blur-[1px]"
		onclick={handleBackdrop}
		onkeydown={handleKey}
		role="dialog"
		aria-modal="true"
		aria-labelledby="confirm-title"
	>
		<div
			class="w-full max-w-sm overflow-hidden rounded-2xl border border-surface-300 bg-surface-50 shadow-xl animate-in"
		>
			<!-- Icon + heading -->
			<div class="flex items-start gap-3.5 p-6 pb-3">
				<span
					class="grid size-11 shrink-0 place-items-center rounded-full bg-warning-100 text-warning-700"
					aria-hidden="true"
				>
					<svg viewBox="0 0 24 24" class="size-6" fill="none" stroke="currentColor" stroke-width="2"
						stroke-linecap="round" stroke-linejoin="round">
						<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
						<line x1="12" y1="9" x2="12" y2="13" />
						<line x1="12" y1="17" x2="12.01" y2="17" />
					</svg>
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
					class="confirm-btn confirm-btn--cancel"
					onclick={() => onCancel?.()}
				>
					{cancelLabel}
				</button>
				<button
					type="button"
					class="confirm-btn confirm-btn--confirm"
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

	.confirm-btn {
		padding: 0.5rem 1.25rem;
		border-radius: 0.5rem;
		font-size: 0.875rem;
		font-weight: 600;
		transition: background-color 0.15s, color 0.15s, box-shadow 0.15s;
		cursor: pointer;
	}

	.confirm-btn:focus-visible {
		outline: 2px solid;
		outline-offset: 2px;
	}

	/* Cancel / "No" — neutral, turns green on hover */
	.confirm-btn--cancel {
		background-color: oklch(0.95 0.01 150);
		color: oklch(0.35 0.06 150);
	}

	.confirm-btn--cancel:hover {
		background-color: oklch(0.45 0.14 150);
		color: white;
	}

	.confirm-btn--cancel:focus-visible {
		outline-color: oklch(0.45 0.14 150);
	}

	/* Confirm / "Yes" — neutral, turns red on hover */
	.confirm-btn--confirm {
		background-color: oklch(0.95 0.01 25);
		color: oklch(0.40 0.10 25);
	}

	.confirm-btn--confirm:hover {
		background-color: oklch(0.50 0.18 25);
		color: white;
	}

	.confirm-btn--confirm:focus-visible {
		outline-color: oklch(0.50 0.18 25);
	}
</style>
