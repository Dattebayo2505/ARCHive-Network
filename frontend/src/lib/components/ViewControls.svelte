<script>
	import { VIEW_SIZES, sizeCols } from '$lib/viewSizes.js';

	let { size, onSize } = $props();

	let btns = $state([]);
	let cols = $derived(typeof size === 'number' ? size : sizeCols(size));
	let sliderValue = $derived(10 - cols);

	function onSliderInput(e) {
		onSize(10 - parseFloat(e.target.value));
	}

	// Arrow-key roving within the segmented control (WAI-ARIA radiogroup pattern):
	// Left/Up = previous, Right/Down = next, Home/End = ends. Selection follows focus.
	function onKey(e, i) {
		const last = VIEW_SIZES.length - 1;
		let next = null;
		if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = i < last ? i + 1 : 0;
		else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = i > 0 ? i - 1 : last;
		else if (e.key === 'Home') next = 0;
		else if (e.key === 'End') next = last;
		if (next === null) return;
		e.preventDefault();
		onSize(VIEW_SIZES[next].cols);
		btns[next]?.focus();
	}
</script>

<div class="flex flex-col items-end gap-2">
	<div class="flex flex-wrap items-center justify-end gap-2">
		<div
		class="flex items-center gap-2 rounded-lg border border-surface-300 bg-surface-50 py-1 pr-1 pl-2.5"
	>
		<span class="text-xs font-medium text-surface-600 select-none" id="size-label">Size</span>
		<div
			class="flex items-center gap-0.5"
			role="radiogroup"
			aria-labelledby="size-label"
		>
			{#each VIEW_SIZES as s, i (s.id)}
				{@const active = cols === s.cols}
				<button
					bind:this={btns[i]}
					type="button"
					role="radio"
					aria-checked={active}
					aria-label={`${s.name} thumbnails`}
					title={`${s.name} thumbnails`}
					tabindex={active ? 0 : -1}
					class="grid h-7 min-w-[1.85rem] place-items-center rounded-md px-1.5 text-xs font-semibold tabular-nums transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
					class:bg-primary-700={active}
					class:text-primary-50={active}
					class:shadow-sm={active}
					class:text-surface-600={!active}
					class:hover:bg-surface-200={!active}
					onclick={() => onSize(s.cols)}
					onkeydown={(e) => onKey(e, i)}
				>
					{s.label}
				</button>
			{/each}
		</div>
	</div>
</div>

	<div class="flex w-full max-w-[200px] items-center px-1">
		<input 
			type="range" 
			min="0" 
			max="8" 
			step="0.01"
			value={sliderValue}
			oninput={onSliderInput}
			class="slider-custom w-full cursor-pointer"
			style="--slider-percent: {(sliderValue / 8) * 100}%;"
		/>
	</div>
</div>

<style>
	input[type="range"].slider-custom {
		-webkit-appearance: none;
		appearance: none;
		background: transparent;
	}

	/* Track */
	input[type="range"].slider-custom::-webkit-slider-runnable-track {
		height: 6px;
		border-radius: 9999px;
		background: linear-gradient(to right, var(--color-primary-500) var(--slider-percent), var(--color-surface-200) var(--slider-percent));
	}
	input[type="range"].slider-custom::-moz-range-track {
		height: 6px;
		border-radius: 9999px;
		background: var(--color-surface-200);
	}
	input[type="range"].slider-custom::-moz-range-progress {
		height: 6px;
		border-radius: 9999px;
		background: var(--color-primary-500);
	}

	/* Thumb */
	input[type="range"].slider-custom::-webkit-slider-thumb {
		-webkit-appearance: none;
		appearance: none;
		height: 16px;
		width: 16px;
		border-radius: 50%;
		background-color: white;
		border: 1px solid var(--color-surface-300);
		box-shadow: 0 1px 3px rgba(0,0,0,0.1);
		margin-top: -5px; /* (Track height / 2) - (Thumb height / 2) = 3 - 8 = -5 */
		transition: transform 0.1s;
	}
	input[type="range"].slider-custom::-moz-range-thumb {
		height: 16px;
		width: 16px;
		border-radius: 50%;
		background-color: white;
		border: 1px solid var(--color-surface-300);
		box-shadow: 0 1px 3px rgba(0,0,0,0.1);
		transition: transform 0.1s;
	}

	input[type="range"].slider-custom:active::-webkit-slider-thumb {
		transform: scale(1.2);
	}
	input[type="range"].slider-custom:active::-moz-range-thumb {
		transform: scale(1.2);
	}
</style>
