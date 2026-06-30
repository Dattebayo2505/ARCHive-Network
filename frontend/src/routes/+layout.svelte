<script>
	import '../app.css';

	let { children } = $props();
</script>

<header class="bg-primary-500 text-white p-4">
	<strong class="text-lg">Streamlinify — Archers Network</strong>
</header>

<main class="p-4">
	{@render children()}
</main>
