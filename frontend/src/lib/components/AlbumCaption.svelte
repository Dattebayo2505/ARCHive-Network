<script>
	/**
	 * The active album's caption, and its editor.
	 *
	 * The caption a volunteer edits is **prose only** — the hashtag pills live in their own
	 * row above and are re-attached server-side, so a typo fix can never delete the canonical
	 * `#ARCH…` section tag that routes the album's photos downstream. The editor says so
	 * out loud, because a rotating volunteer has no way to know it otherwise.
	 *
	 * Read-only albums (the archive) render the caption without any edit affordance; an
	 * editable album with no caption still renders the block, so "the caption lives here"
	 * is learnable from the empty state rather than discoverable only by accident.
	 */
	let {
		album,
		editable = true,
		/** Squares the bottom corners so the docked selection strip reads as one attached block. */
		attached = false,
		onSave,
		onReset
	} = $props();

	const MAX_LEN = 2000;

	let editing = $state(false);
	let draft = $state('');
	let saving = $state(false);
	let expanded = $state(false);
	let textarea = $state(null);

	let caption = $derived(album?.description ?? '');
	let isLong = $derived(caption.length > 120 || caption.split('\n').length > 2);
	let tooLong = $derived(draft.length > MAX_LEN);

	// Switching albums must never carry one album's draft into another's editor.
	$effect(() => {
		album?.fb_album_id;
		editing = false;
		expanded = false;
	});

	function startEdit() {
		draft = caption;
		editing = true;
		// Focus after the textarea mounts; select nothing so the caret lands at the end.
		queueMicrotask(() => {
			textarea?.focus();
			textarea?.setSelectionRange(draft.length, draft.length);
		});
	}

	function cancel() {
		editing = false;
		draft = '';
	}

	async function save() {
		if (saving || tooLong) return;
		if (draft.trim() === caption.trim()) return cancel();
		saving = true;
		await onSave?.(draft);
		saving = false;
		editing = false;
	}

	async function reset() {
		if (saving) return;
		saving = true;
		await onReset?.();
		saving = false;
		editing = false;
	}

	function onKeydown(event) {
		if (event.key === 'Escape') {
			event.stopPropagation(); // never let Esc fall through and close the gallery's overlays
			cancel();
		} else if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
			event.preventDefault();
			save();
		}
	}
</script>

{#if caption || editable}
	<div
		class="relative mt-1.5 rounded-md bg-surface-200 px-2.5 py-1.5 text-xs text-surface-600 transition-[border-radius] duration-200"
		class:rounded-b-none={attached}
	>
		{#if editing}
			<label class="sr-only" for="album-caption-input">Album caption</label>
			<textarea
				id="album-caption-input"
				bind:this={textarea}
				bind:value={draft}
				onkeydown={onKeydown}
				rows="4"
				disabled={saving}
				placeholder="Describe this album — what it covers, when, who."
				class="w-full resize-y rounded border border-surface-300 bg-surface-50 px-2 py-1.5 text-xs leading-relaxed text-surface-900 placeholder:text-surface-600 focus:border-primary-600 focus:outline-2 focus:outline-offset-0 focus:outline-primary-600 disabled:opacity-60"
			></textarea>

			<div class="mt-1.5 flex flex-wrap items-center justify-between gap-2">
				<p class="text-surface-600">
					{#if album?.hashtags?.length}
						Hashtags stay attached — you only edit the wording.
					{:else}
						Saved for this workspace only. The original export is never changed.
					{/if}
				</p>
				<div class="flex items-center gap-1.5">
					{#if tooLong}
						<span class="font-medium text-error-700 tabular-nums">
							{draft.length} / {MAX_LEN}
						</span>
					{/if}
					{#if album?.caption_edited}
						<button
							type="button"
							class="rounded px-2 py-1 font-medium text-surface-700 transition-colors hover:bg-surface-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:opacity-50"
							disabled={saving}
							onclick={reset}
						>
							Reset to original
						</button>
					{/if}
					<button
						type="button"
						class="rounded px-2 py-1 font-medium text-surface-700 transition-colors hover:bg-surface-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:opacity-50"
						disabled={saving}
						onclick={cancel}
					>
						Cancel
					</button>
					<button
						type="button"
						class="rounded bg-primary-700 px-2.5 py-1 font-semibold text-primary-50 transition-colors hover:bg-primary-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:opacity-50"
						disabled={saving || tooLong}
						onclick={save}
					>
						{saving ? 'Saving…' : 'Save caption'}
					</button>
				</div>
			</div>
		{:else}
			<!-- pr-8 keeps wrapped text clear of the edit button pinned in the corner. -->
			<div class:pr-8={editable}>
				{#if caption}
					<p
						class="leading-relaxed break-words whitespace-pre-wrap"
						class:line-clamp-2={isLong && !expanded}
					>
						{caption}
					</p>
					{#if isLong}
						<button
							type="button"
							class="mt-0.5 font-medium text-primary-600 hover:text-primary-700 hover:underline dark:text-primary-300 dark:hover:text-primary-200"
							onclick={() => (expanded = !expanded)}
						>
							{expanded ? 'See less' : 'Read more'}
						</button>
					{/if}
				{:else}
					<p class="text-surface-600 italic">No caption yet.</p>
				{/if}
			</div>

			{#if editable}
				<button
					type="button"
					class="absolute top-1 right-1 grid size-7 place-items-center rounded text-surface-600 transition-colors hover:bg-surface-300 hover:text-surface-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
					title={caption ? 'Edit caption' : 'Add caption'}
					aria-label={caption ? 'Edit caption' : 'Add caption'}
					onclick={startEdit}
				>
					<svg
						viewBox="0 0 24 24"
						class="size-3.5"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
						<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4Z" />
					</svg>
				</button>
			{/if}
		{/if}
	</div>
{/if}

<style>
	@media (prefers-reduced-motion: reduce) {
		/* The block's radius tween is the only motion here; drop it rather than crossfade. */
		div {
			transition: none;
		}
	}
</style>
