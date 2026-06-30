<script>
	let { result, onClose } = $props();
</script>

<div class="fixed inset-0 grid place-items-center bg-black/50" role="dialog" aria-modal="true">
	<div class="card bg-surface-100-900 w-full max-w-lg space-y-2 p-6">
		<h2 class="h3">Build complete</h2>
		<p>Media files copied: {result.copied}</p>
		<p>Albums written: {result.albums_written}</p>
		<p>Orphans: {result.orphans.length}</p>
		<pre class="pre max-h-64 overflow-auto">{result.summary}</pre>
		<button class="btn preset-filled" type="button" onclick={onClose}>Back to gallery</button>
	</div>
</div>
