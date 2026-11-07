<script>
	/**
	 * One Publish result (`PublishResult.as_dict()`): Preflight, Upload + load, Verify, each with
	 * per-check pass/fail. Overall green only when `result.ok`. A step that never ran (`null`) says
	 * "Not run" rather than vanishing, so a failed preflight visibly stopped everything after it.
	 */
	let { result } = $props();

	const preflight = $derived(result?.steps?.preflight ?? null);
	const load = $derived(result?.steps?.publish ?? null);
	const verify = $derived(result?.steps?.verify ?? null);

	// A changed object size is expected (re-captured posters, FB re-encodes) and never overwritten,
	// so it is worth seeing but must not read as a failure.
	const SIZE_DIFFERS = /size differs/i;
	const statusOf = (c) => (!c.ok ? 'fail' : SIZE_DIFFERS.test(c.detail ?? '') ? 'warn' : 'pass');

	const loadStats = $derived(
		load
			? [
					{ label: 'Albums', value: `+${load.albums_inserted}`, sub: `${load.albums_updated} updated` },
					{
						label: 'Media',
						value: `+${load.media_inserted}`,
						sub:
							`${load.media_updated} updated` +
							(load.skipped_deleted?.length ? ` · ${load.skipped_deleted.length} tombstoned` : '')
					},
					{ label: 'Files stored', value: load.files_stored, sub: `${load.files_skipped} already there` },
					{
						label: 'Orphans',
						value: load.orphans?.length ?? 0,
						sub: load.orphans?.length ? 'uri with no file' : 'none',
						warn: (load.orphans?.length ?? 0) > 0
					}
				]
			: []
	);
	const loadErrors = $derived([...(load?.errors ?? []), ...(load?.failed ?? [])]);

	const STEP_CHIP = {
		pass: ['Passed', 'bg-success-100 text-success-800'],
		fail: ['Failed', 'bg-error-100 text-error-800'],
		skip: ['Not run', 'bg-surface-200 text-surface-700']
	};
	const stepState = (step) => (step === null ? 'skip' : step.ok ? 'pass' : 'fail');
</script>

{#snippet chip(state)}
	<span class="shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold {STEP_CHIP[state][1]}"
		>{STEP_CHIP[state][0]}</span
	>
{/snippet}

{#snippet checkList(checks)}
	<ul class="divide-y divide-surface-200">
		{#each checks as c (c.name)}
			{@const s = statusOf(c)}
			<li class="flex items-start gap-3 py-2" data-status={s}>
				<!-- Icon + word: the verdict must never be carried by colour alone. -->
				<span
					class="mt-px grid size-4 shrink-0 place-items-center rounded-full {s === 'pass'
						? 'bg-success-100 text-success-700'
						: s === 'warn'
							? 'bg-warning-100 text-warning-800'
							: 'bg-error-100 text-error-700'}"
					aria-hidden="true"
				>
					<svg viewBox="0 0 24 24" class="size-3" fill="none" stroke="currentColor" stroke-width="3.5"
						stroke-linecap="round" stroke-linejoin="round">
						{#if s === 'pass'}<path d="M20 6 9 17l-5-5" />{:else if s === 'warn'}<path
								d="M12 7v6M12 17h.01"
							/>{:else}<path d="M18 6 6 18M6 6l12 12" />{/if}
					</svg>
				</span>
				<span class="min-w-0 flex-1">
					<span class="block text-sm text-surface-800">{c.name}</span>
					{#if c.detail}
						<span
							class="mt-0.5 block font-mono text-xs break-words {s === 'fail'
								? 'text-error-700'
								: s === 'warn'
									? 'text-warning-800'
									: 'text-surface-600'}">{c.detail}</span
						>
					{/if}
				</span>
				<span
					class="shrink-0 text-xs font-semibold {s === 'pass'
						? 'text-success-700'
						: s === 'warn'
							? 'text-warning-800'
							: 'text-error-700'}">{s === 'pass' ? 'Pass' : s === 'warn' ? 'Warning' : 'Fail'}</span
				>
			</li>
		{/each}
	</ul>
{/snippet}

{#snippet notRun()}
	<p class="py-2 text-sm text-surface-600">An earlier step failed, so nothing here ran.</p>
{/snippet}

{#snippet list(title, items)}
	<div class="mt-3">
		<p class="text-xs font-medium text-surface-700">{title}</p>
		<pre
			class="mt-1 max-h-40 overflow-auto rounded-lg bg-surface-100 p-2.5 font-mono text-xs leading-relaxed text-surface-700">{items.join(
				'\n'
			)}</pre>
	</div>
{/snippet}

{#if result}
	<div class="rounded-lg border border-surface-200" aria-live="polite">
		<div
			data-testid="publish-summary"
			data-ok={String(!!result.ok)}
			class="flex items-start gap-3 rounded-t-lg border-b px-4 py-3 {result.ok
				? 'border-success-200 bg-success-50'
				: 'border-error-200 bg-error-50'}"
		>
			<span
				class="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full {result.ok
					? 'bg-success-600 text-primary-50'
					: 'bg-error-600 text-primary-50'}"
				aria-hidden="true"
			>
				<svg viewBox="0 0 24 24" class="size-3.5" fill="none" stroke="currentColor" stroke-width="3"
					stroke-linecap="round" stroke-linejoin="round">
					{#if result.ok}<path d="M20 6 9 17l-5-5" />{:else}<path d="M18 6 6 18M6 6l12 12" />{/if}
				</svg>
			</span>
			<div class="min-w-0">
				<p class="text-sm font-semibold {result.ok ? 'text-success-900' : 'text-error-900'}">
					{result.ok
						? `Published to ${result.env}, and every check passed.`
						: `Publish to ${result.env} did not finish cleanly.`}
				</p>
				<p class="mt-0.5 text-xs break-words {result.ok ? 'text-success-800' : 'text-error-800'}">
					<span class="font-mono">s3://{result.bucket}</span> ·
					<span class="font-mono">{result.table_prefix}-*</span>
					{#if result.identity}· as <span class="font-mono break-all">{result.identity}</span>{/if}
				</p>
				{#if !result.ok}
					<p class="mt-1 text-xs font-medium text-error-800">Re-running Publish is safe.</p>
				{/if}
			</div>
		</div>

		<ol class="divide-y divide-surface-200">
			<li>
				<section class="px-4 py-3" aria-label="Preflight">
					<div class="flex items-center justify-between gap-3">
						<h3 class="text-sm font-semibold text-surface-900">
							<span class="mr-1.5 font-mono text-xs text-surface-500" aria-hidden="true">1</span>Preflight
						</h3>
						{@render chip(stepState(preflight))}
					</div>
					{#if preflight}{@render checkList(preflight.checks ?? [])}{:else}{@render notRun()}{/if}
				</section>
			</li>

			<li>
				<section class="px-4 py-3" aria-label="Upload + load">
					<div class="flex items-center justify-between gap-3">
						<h3 class="text-sm font-semibold text-surface-900">
							<span class="mr-1.5 font-mono text-xs text-surface-500" aria-hidden="true">2</span>Upload + load
						</h3>
						{@render chip(stepState(load))}
					</div>
					{#if load}
						<div
							class="mt-2 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-surface-200 bg-surface-200 sm:grid-cols-4"
						>
							{#each loadStats as stat (stat.label)}
								<div class="bg-surface-50 px-3 py-2.5">
									<p
										class="text-base font-semibold tabular-nums {stat.warn
											? 'text-warning-700'
											: 'text-surface-900'}"
									>
										{stat.value}
									</p>
									<p class="mt-0.5 text-xs font-medium text-surface-800">{stat.label}</p>
									<p class="text-xs text-surface-600">{stat.sub}</p>
								</div>
							{/each}
						</div>
						{#if loadErrors.length}{@render list(`Not written (${loadErrors.length})`, loadErrors)}{/if}
						{#if load.orphans?.length}{@render list('Orphans: uri with no file', load.orphans)}{/if}
						{#if load.skipped_deleted?.length}
							{@render list('Tombstoned in the CMS, left alone', load.skipped_deleted)}
						{/if}
					{:else}
						{@render notRun()}
					{/if}
				</section>
			</li>

			<li>
				<section class="px-4 py-3" aria-label="Verify">
					<div class="flex items-center justify-between gap-3">
						<h3 class="text-sm font-semibold text-surface-900">
							<span class="mr-1.5 font-mono text-xs text-surface-500" aria-hidden="true">3</span>Verify
						</h3>
						{@render chip(stepState(verify))}
					</div>
					{#if verify}{@render checkList(verify.checks ?? [])}{:else}{@render notRun()}{/if}
				</section>
			</li>
		</ol>
	</div>
{/if}
