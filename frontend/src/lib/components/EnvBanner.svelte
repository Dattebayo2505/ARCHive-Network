<script>
	import { bannerTone } from '$lib/env.svelte.js';
	/**
	 * The always-visible "you are not on floci". Nothing on a floci env; a warning band on AWS and
	 * the error/alarm band on a `confirm` env, matching the prod confirm dialog. The warning and
	 * error ramps do not invert under `.dark`, so these pale-tint/dark-ink pairs hold in both themes.
	 */
	let { env, identity = null } = $props();

	const tone = $derived(bannerTone(env));
</script>

{#if tone !== 'none'}
	<div
		data-testid="env-banner"
		data-tone={tone}
		class="flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5 {tone === 'prod'
			? 'border-error-400 bg-error-50 text-error-900'
			: 'border-warning-400 bg-warning-50 text-warning-900'}"
	>
		<svg
			viewBox="0 0 24 24"
			class="mt-0.5 size-4 shrink-0"
			fill="none"
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"
		>
			<path d="M17.5 19a4.5 4.5 0 1 0-1.4-8.78A6 6 0 1 0 6 16.5" />
			<path d="M12 13v8M9 18l3 3 3-3" />
		</svg>
		<div class="min-w-0">
			<p class="text-sm font-semibold break-words">
				AWS · {env.label} · <span class="font-mono font-medium">s3://{env.s3_bucket}</span> ·
				<span class="font-mono font-medium">{env.table_prefix}-*</span>
			</p>
			<p class="mt-0.5 text-xs leading-relaxed">
				{tone === 'prod'
					? 'Production. Every Publish here asks you to type the environment name first.'
					: 'Real AWS, not the local emulator. Publish writes to this bucket and these tables.'}
				{#if identity}
					Signed in as <span class="font-mono break-all">{identity}</span>.
				{/if}
			</p>
		</div>
	</div>
{/if}
