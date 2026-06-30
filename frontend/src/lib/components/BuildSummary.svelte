<script>
	let { result, onClose } = $props();
</script>

<button class="btn preset-filled" type="button" onclick={onClose}>Close ({result.copied} copied)</button>
