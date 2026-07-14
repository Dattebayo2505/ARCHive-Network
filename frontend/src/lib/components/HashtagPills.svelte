<script>
	/**
	 * The album's hashtags, as pills. The canonical section tag (one of the six) is
	 * brand-tinted; everything else is a neutral chip. Six competing hues in a header
	 * would be noise, so only "which section is this" gets colour.
	 *
	 * The caption arrives already stripped from the API — this component is the only
	 * place a hashtag is ever rendered.
	 */
	const CANONICAL = new Set([
		'ARCHEVT',
		'ARCHADS',
		'ARCHNEWS',
		'ARCHSPORTS',
		'ARCHCULTURE',
		'ARCHENT'
	]);

	let { tags = [] } = $props();
</script>

{#each tags as tag (tag)}
	{@const canonical = CANONICAL.has(tag.toUpperCase())}
	<span
		class="rounded-full px-2 py-0.5 text-[0.65rem] font-semibold tracking-wide {canonical
			? 'bg-primary-100 text-primary-800'
			: 'bg-surface-200 text-surface-700'}"
	>
		#{tag}
	</span>
{/each}
