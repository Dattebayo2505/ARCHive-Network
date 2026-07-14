<script>
	/**
	 * The album's hashtags, as pills. The canonical section tag (one of the six) is a solid
	 * brand-green pill; everything else is a neutral chip. Six competing hues in a header
	 * would be noise, so only "which section is this" gets colour.
	 *
	 * The canonical pill is deliberately SOLID (`bg-primary-700` + `text-primary-50`) rather
	 * than the tinted `bg-primary-100` + `text-primary-800` pairing. The surface ramp inverts
	 * under `.dark` but the primary ramp keeps its identity, so a pale-tint/dark-ink pairing
	 * collapses to dark-green-on-dark-green at night (measured 1.24:1 — invisible). Both of
	 * these tokens are theme-stable, so the pill reads identically in light and dark.
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
			? 'bg-primary-700 text-primary-50'
			: 'bg-surface-200 text-surface-700'}"
	>
		#{tag}
	</span>
{/each}
