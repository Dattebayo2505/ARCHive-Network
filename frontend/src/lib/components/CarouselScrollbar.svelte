<script>
	let { container, vertical = false } = $props();

	let progress = $state(0);
	let isDragging = $state(false);
	let trackEl = $state();
	
	let canScroll = $state(false);

	function updateFromScroll() {
		if (!container) return;
		const max = vertical 
			? container.scrollHeight - container.clientHeight
			: container.scrollWidth - container.clientWidth;
		canScroll = max > 0;
		if (!isDragging) {
			const scrollPos = vertical ? container.scrollTop : container.scrollLeft;
			progress = max > 0 ? scrollPos / max : 0;
		}
	}

	$effect(() => {
		if (!container) return;
		
		const onScroll = () => updateFromScroll();
		const ro = new ResizeObserver(onScroll);
		
		container.addEventListener('scroll', onScroll, { passive: true });
		ro.observe(container);
		for (const child of container.children) {
			ro.observe(child);
		}
		
		updateFromScroll();
		
		return () => {
			container.removeEventListener('scroll', onScroll);
			ro.disconnect();
		};
	});

	function updateFromEvent(e) {
		if (!trackEl || !container) return;
		const rect = trackEl.getBoundingClientRect();
		const newProgress = Math.max(0, Math.min(
			vertical ? (e.clientY - rect.top) / rect.height : (e.clientX - rect.left) / rect.width, 
			1
		));
		
		const max = vertical 
			? container.scrollHeight - container.clientHeight
			: container.scrollWidth - container.clientWidth;

		if (vertical) {
			container.scrollTop = newProgress * max;
		} else {
			container.scrollLeft = newProgress * max;
		}
		progress = newProgress;
	}

	function onPointerDown(e) {
		if (e.button !== 0 || !canScroll) return;
		e.preventDefault();
		isDragging = true;
		updateFromEvent(e);
		window.addEventListener('pointermove', onPointerMove);
		window.addEventListener('pointerup', onPointerUp);
	}

	function onPointerMove(e) {
		if (!isDragging) return;
		updateFromEvent(e);
	}

	function onPointerUp(e) {
		isDragging = false;
		window.removeEventListener('pointermove', onPointerMove);
		window.removeEventListener('pointerup', onPointerUp);
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
{#if vertical}
<div 
	class="relative flex w-5 h-full cursor-pointer justify-center transition-opacity [touch-action:none]"
	class:opacity-0={!canScroll}
	class:pointer-events-none={!canScroll}
	bind:this={trackEl}
	onpointerdown={onPointerDown}
>
	<div class="absolute w-[2px] h-full bg-primary-600/30 rounded-full"></div>
	
	<div 
		class="absolute top-0 w-1 bg-primary-600 rounded-full pointer-events-none" 
		style="height: {progress * 100}%;"
	></div>
	
	<div 
		class="absolute top-0 w-3 h-6 rounded-[2px] bg-primary-600 shadow-sm pointer-events-none transition-transform"
		class:scale-110={isDragging}
		style="top: {progress * 100}%; transform: translateY(-50%);"
	></div>
</div>
{:else}
<div 
	class="relative flex h-5 w-full cursor-pointer items-center transition-opacity [touch-action:none]"
	class:opacity-0={!canScroll}
	class:pointer-events-none={!canScroll}
	bind:this={trackEl}
	onpointerdown={onPointerDown}
>
	<div class="absolute left-0 h-[2px] w-full bg-primary-600/30 rounded-full"></div>
	
	<div 
		class="absolute left-0 h-1 bg-primary-600 rounded-full pointer-events-none" 
		style="width: {progress * 100}%;"
	></div>
	
	<div 
		class="absolute left-0 h-3 w-6 rounded-[2px] bg-primary-600 shadow-sm pointer-events-none transition-transform"
		class:scale-110={isDragging}
		style="left: {progress * 100}%; transform: translateX(-50%);"
	></div>
</div>
{/if}
