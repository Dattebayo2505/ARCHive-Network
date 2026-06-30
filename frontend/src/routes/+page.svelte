<script>
	import { goto } from '$app/navigation';
	import { ingestFolder, ingestUpload } from '$lib/api.js';

	let folder = $state('');
	let files = $state(null);
	let errors = $state([]);
	let busy = $state(false);

	async function onResult(result) {
		busy = false;
		if (result.ok) await goto('/gallery');
		else errors = result.errors;
	}

	async function submitUpload(e) {
		e.preventDefault();
		if (!files?.[0]) return;
		busy = true;
		errors = [];
		await onResult(await ingestUpload(files[0]));
	}

	async function submitFolder(e) {
		e.preventDefault();
		busy = true;
		errors = [];
		await onResult(await ingestFolder(folder));
	}
</script>

<section class="max-w-xl space-y-4">
	<form class="card p-4 space-y-2" onsubmit={submitUpload}>
		<label class="label">
			<span>Drop export .zip</span>
			<input class="input" type="file" accept=".zip" bind:files required />
		</label>
		<button class="btn preset-filled" type="submit" disabled={busy}>Upload</button>
	</form>

	<form class="card p-4 space-y-2" onsubmit={submitFolder}>
		<label class="label">
			<span>or folder path</span>
			<input class="input" type="text" bind:value={folder} size="60" required />
		</label>
		<button class="btn preset-filled" type="submit" disabled={busy}>Load</button>
	</form>

	{#if errors.length}
		<ul class="text-error-500">
			{#each errors as e}<li>Missing: {e}</li>{/each}
		</ul>
	{/if}
</section>
