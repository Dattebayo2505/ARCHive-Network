<script>
	/**
	 * Which named environment the Dev panel acts on. Native radios styled as a segmented control,
	 * so arrow keys and screen readers behave as they would for any radio group.
	 *
	 * Props: envs (from /api/envs), selected (env name), disabled (e.g. while a Publish runs),
	 * onSelect(name). An unconfigured env is shown, disabled, with the fix spelled out.
	 */
	let { envs = [], selected, disabled = false, onSelect = () => {} } = $props();

	const HINT = "Add this env's sign-in values to environments.local.toml (see the AWS guide)";
	const unconfigured = $derived(envs.filter((e) => !e.configured));
</script>

<fieldset class="min-w-0">
	<legend class="text-xs font-medium text-surface-700">Environment</legend>
	<div
		class="mt-1.5 inline-flex max-w-full flex-wrap gap-0.5 rounded-lg border border-surface-300 bg-surface-100 p-0.5"
	>
		{#each envs as env (env.name)}
			{@const off = disabled || !env.configured}
			<label
				class="relative {off ? 'cursor-not-allowed' : 'cursor-pointer'}"
				title={env.configured ? env.name : HINT}
			>
				<input
					type="radio"
					name="dev-env"
					value={env.name}
					checked={selected === env.name}
					disabled={off}
					onchange={() => !off && onSelect(env.name)}
					class="peer sr-only"
				/>
				<span
					class="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium whitespace-nowrap text-surface-700 transition-colors peer-checked:bg-primary-700 peer-checked:font-semibold peer-checked:text-primary-50 peer-focus-visible:outline-2 peer-focus-visible:outline-offset-1 peer-focus-visible:outline-primary-600 peer-disabled:opacity-50 {off
						? ''
						: 'hover:bg-surface-200 peer-checked:hover:bg-primary-700'}"
				>
					{env.label}
					<!-- The kind in words, so floci vs AWS never rests on colour or label wording alone. -->
					<span class="font-mono text-[0.6875rem] font-normal opacity-80">{env.kind}</span>
				</span>
			</label>
		{/each}
	</div>
	{#if unconfigured.length}
		<p class="mt-1.5 text-xs leading-relaxed text-surface-600">
			<span class="font-medium text-surface-800">{unconfigured.map((e) => e.label).join(', ')}</span>:
			{HINT}.
		</p>
	{/if}
</fieldset>
