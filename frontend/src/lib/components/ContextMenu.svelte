<script>
	import { tick } from 'svelte';

	/**
	 * A single shared right-click menu. The page owns one instance and feeds it
	 * coordinates + items; rendering one menu (instead of one per tile) keeps it
	 * out of every tile's clipped/overflow box.
	 *
	 * items: { label, icon?, hint?, disabled?, onSelect }[]
	 */
	let { open = false, x = 0, y = 0, items = [], onClose } = $props();

	let menuEl = $state();
	let itemEls = $state([]);
	let pos = $state({ left: 0, top: 0 });
	let shown = $state(false); // drives the enter animation once placed
	let openSub = $state(null); // index of the item whose submenu is open (keyboard)
	let subEls = $state({}); // submenu button refs, keyed `${itemIndex}:${subIndex}`

	const firstEnabled = () => items.findIndex((i) => !i.disabled);

	function reducedMotion() {
		return (
			typeof window !== 'undefined' &&
			window.matchMedia('(prefers-reduced-motion: reduce)').matches
		);
	}

	// Place the menu at the cursor, then nudge it back inside the viewport so a
	// right-click near an edge never spills off-screen.
	async function place() {
		shown = false;
		await tick();
		const m = 8;
		const w = menuEl?.offsetWidth ?? 0;
		const h = menuEl?.offsetHeight ?? 0;
		const vw = window.innerWidth;
		const vh = window.innerHeight;
		pos = {
			left: Math.max(m, Math.min(x, vw - w - m)),
			top: Math.max(m, Math.min(y, vh - h - m))
		};
		shown = true;
		openSub = null;
		itemEls[firstEnabled()]?.focus();
	}

	const enabledSubs = (i) =>
		(items[i]?.subItems ?? [])
			.map((s, si) => (s.disabled ? -1 : si))
			.filter((si) => si >= 0);

	function openSubmenu(i) {
		const enabled = enabledSubs(i);
		if (!enabled.length) return;
		openSub = i;
		tick().then(() => subEls[`${i}:${enabled[0]}`]?.focus());
	}

	function onSubKey(e, i, si) {
		const enabled = enabledSubs(i);
		const at = enabled.indexOf(si);
		if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
			e.preventDefault();
			const step = e.key === 'ArrowDown' ? 1 : -1;
			subEls[`${i}:${enabled[(at + step + enabled.length) % enabled.length]}`]?.focus();
		} else if (e.key === 'ArrowLeft' || e.key === 'Escape') {
			e.preventDefault();
			openSub = null;
			itemEls[i]?.focus();
		} else if (e.key === 'Home') {
			e.preventDefault();
			subEls[`${i}:${enabled[0]}`]?.focus();
		} else if (e.key === 'End') {
			e.preventDefault();
			subEls[`${i}:${enabled[enabled.length - 1]}`]?.focus();
		}
	}

	function close() {
		shown = false;
		onClose?.();
	}

	function activate(item) {
		if (item.disabled) return;
		close();
		item.onSelect?.();
	}

	function onKey(e, i) {
		const enabled = items.map((it, idx) => (it.disabled ? -1 : idx)).filter((idx) => idx >= 0);
		const at = enabled.indexOf(i);
		if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
			e.preventDefault();
			openSub = null;
			const step = e.key === 'ArrowDown' ? 1 : -1;
			const next = enabled[(at + step + enabled.length) % enabled.length];
			itemEls[next]?.focus();
		} else if (e.key === 'ArrowRight') {
			if (items[i]?.subItems) {
				e.preventDefault();
				openSubmenu(i);
			}
		} else if (e.key === 'Home') {
			e.preventDefault();
			itemEls[enabled[0]]?.focus();
		} else if (e.key === 'End') {
			e.preventDefault();
			itemEls[enabled[enabled.length - 1]]?.focus();
		} else if (e.key === 'Escape') {
			e.preventDefault();
			close();
		}
	}

	$effect(() => {
		if (open) {
			place();
			const onDown = (e) => {
				if (menuEl && !menuEl.contains(e.target)) close();
			};
			const onScroll = (e) => {
				if (menuEl && menuEl.contains(e.target)) return;
				close();
			};
			
			window.addEventListener('pointerdown', onDown, true);
			window.addEventListener('scroll', onScroll, true);
			window.addEventListener('resize', close);
			
			return () => {
				window.removeEventListener('pointerdown', onDown, true);
				window.removeEventListener('scroll', onScroll, true);
				window.removeEventListener('resize', close);
			};
		}
	});
</script>

{#if open}
	<div
		bind:this={menuEl}
		role="menu"
		tabindex="-1"
		aria-orientation="vertical"
		class="fixed z-[70] min-w-[12rem] origin-top-left rounded-lg border border-surface-300 bg-surface-50 p-1 shadow-[0_12px_32px_oklch(0.16_0.006_172/0.18)] transition duration-100 ease-out motion-reduce:transition-none"
		class:opacity-0={!shown}
		class:scale-95={!shown}
		style="left: {pos.left}px; top: {pos.top}px;"
	>
		{#each items as item, i (item.label)}
			{#if item.subItems}
				<div class="group/submenu relative">
					<button
						bind:this={itemEls[i]}
						type="button"
						role="menuitem"
						tabindex="-1"
						disabled={item.disabled}
						aria-haspopup="menu"
						aria-expanded={openSub === i}
						class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm text-surface-800 transition-colors hover:bg-primary-100 focus-visible:bg-primary-100 focus-visible:outline-none disabled:cursor-not-allowed disabled:text-surface-400 disabled:hover:bg-transparent"
						onclick={() => activate(item)}
						onkeydown={(e) => onKey(e, i)}
					>
						<span class="grid size-4 shrink-0 place-items-center text-surface-500" aria-hidden="true">
							{#if item.icon === 'rename'}
								<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2"
									stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" /><path d="m15 5 4 4" /></svg>
							{/if}
						</span>
						<span class="flex-1 truncate">{item.label}</span>
						<svg viewBox="0 0 24 24" class="size-4 shrink-0 text-surface-400" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
					</button>
					<div
						class="absolute left-full top-0 hidden min-w-[12rem] rounded-lg border border-surface-300 bg-surface-50 p-1 shadow-[0_12px_32px_oklch(0.16_0.006_172/0.18)] group-hover/submenu:block before:absolute before:inset-y-0 before:-left-2 before:w-2"
						class:!block={openSub === i}
						role="menu"
					>
						{#each item.subItems as sub, si}
							<button
								bind:this={subEls[`${i}:${si}`]}
								type="button"
								role="menuitem"
								tabindex="-1"
								disabled={sub.disabled}
								class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm text-surface-800 transition-colors hover:bg-primary-100 focus-visible:bg-primary-100 focus-visible:outline-none disabled:cursor-not-allowed disabled:text-surface-400 disabled:hover:bg-transparent"
								onclick={() => activate(sub)}
								onkeydown={(e) => onSubKey(e, i, si)}
							>
								<span class="flex-1 truncate">{sub.label}</span>
							</button>
						{/each}
					</div>
				</div>
			{:else}
				<button
					bind:this={itemEls[i]}
					type="button"
					role="menuitem"
					tabindex="-1"
					disabled={item.disabled}
					class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm text-surface-800 transition-colors hover:bg-primary-100 focus-visible:bg-primary-100 focus-visible:outline-none disabled:cursor-not-allowed disabled:text-surface-400 disabled:hover:bg-transparent"
					onclick={() => activate(item)}
					onkeydown={(e) => onKey(e, i)}
				>
					<span class="grid size-4 shrink-0 place-items-center text-surface-500" aria-hidden="true">
						{#if item.icon === 'preview'}
							<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2"
								stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6" /><path d="M9 21H3v-6" /><path d="M21 3l-7 7" /><path d="M3 21l7-7" /></svg>
						{:else if item.icon === 'folder'}
							<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="1.85"
								stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1h-7.5l-2-2H4a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1Z" /></svg>
						{:else if item.icon === 'rename'}
							<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2"
								stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" /><path d="m15 5 4 4" /></svg>
						{:else if item.icon === 'archive'}
							<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2"
								stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="4" rx="1" /><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4" /></svg>
						{:else if item.icon === 'unlock'}
							<svg viewBox="0 0 24 24" class="size-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 9.9-1" /></svg>
						{/if}
					</span>
					<span class="flex-1 truncate">{item.label}</span>
					{#if item.hint}
						<span class="shrink-0 text-xs text-surface-600">{item.hint}</span>
					{/if}
				</button>
			{/if}
		{/each}
	</div>
{/if}
