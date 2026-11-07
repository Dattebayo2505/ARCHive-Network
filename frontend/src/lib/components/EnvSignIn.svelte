<script>
	import { envLogin, envLoginState, envLogout } from '$lib/api.js';
	/**
	 * The sign-in row for an AWS env: app-scoped SSO through the backend's device flow.
	 *
	 * Props: env, login (LoginState — the string, or `{state}`), identity, onSignIn(), onSignOut(),
	 * and notice (a message the panel hands down, e.g. after a 401 elsewhere).
	 *
	 * Every way a sign-in can end without success (denied, expired, the local deadline, an error)
	 * lands back on a plain Sign in button with a sentence saying why. Nothing is left spinning.
	 */
	let {
		env,
		login = 'signed_out',
		identity = null,
		notice = '',
		onSignIn = () => {},
		onSignOut = () => {}
	} = $props();

	const serverState = $derived(typeof login === 'string' ? login : (login?.state ?? 'signed_out'));

	// `pending` holds the live device flow; `message` explains the last flow that ended badly.
	let pending = $state(null); // { code, url } | null
	let message = $state('');
	let command = $state(''); // a profile env's CLI sign-in, shown verbatim
	let signedInHere = $state(false);
	let busy = $state(false);

	let timer = 0;
	let flowId = 0; // bumps on every start/stop, so a late poll from an old flow is ignored

	function stop() {
		clearTimeout(timer);
		timer = 0;
		flowId += 1;
		pending = null;
	}

	// The panel's word wins whenever it changes: a 401 elsewhere means this login is gone.
	$effect(() => {
		void serverState;
		void notice;
		signedInHere = false;
	});

	// Switching env (or unmounting) must never leave the old env's poll running.
	$effect(() => {
		void env?.name;
		return () => stop();
	});

	const signedIn = $derived(!pending && (signedInHere || serverState === 'signed_in'));

	function end(text) {
		stop();
		message = text;
	}

	const ENDED = {
		denied: 'Sign-in was denied in the browser. Sign in again to retry.',
		expired: 'The sign-in code expired before it was approved. Sign in again for a new code.',
		signed_out: "The sign-in didn't complete. Sign in again to retry."
	};

	async function signIn() {
		stop();
		message = '';
		command = '';
		busy = true;
		let res;
		try {
			res = await envLogin(env.name);
		} catch {
			busy = false;
			return end("Couldn't reach the API to start sign-in.");
		}
		busy = false;
		if (res.status === 409 && res.body?.error === 'profile_login') {
			command = res.body.detail ?? '';
			return;
		}
		if (!res.ok) return end(res.body?.detail ?? "Sign-in couldn't start.");

		const { verification_uri_complete: url, user_code: code, expires_in, interval } = res.body;
		window.open(url, '_blank', 'noopener');
		pending = { code, url };
		const id = flowId;
		const deadline = Date.now() + (expires_in ?? 600) * 1000;
		const every = Math.max(1, interval ?? 5) * 1000;

		const poll = async () => {
			if (id !== flowId) return;
			if (Date.now() >= deadline) return end(ENDED.expired);
			let r;
			try {
				r = await envLoginState(env.name);
			} catch {
				r = null;
			}
			if (id !== flowId) return;
			const s = r?.ok ? r.body?.state : null;
			if (s === 'signed_in') {
				stop();
				signedInHere = true;
				onSignIn();
				return;
			}
			if (s && s !== 'pending') return end(ENDED[s] ?? ENDED.signed_out);
			if (!r?.ok) return end(r?.body?.detail ?? "Couldn't check the sign-in. Sign in again to retry.");
			timer = setTimeout(poll, every);
		};
		timer = setTimeout(poll, every);
	}

	async function signOut() {
		busy = true;
		try {
			await envLogout(env.name);
		} finally {
			busy = false;
			signedInHere = false;
			onSignOut();
		}
	}

	const btn =
		'rounded-lg px-3.5 py-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50';
	const primary = `${btn} bg-primary-700 font-semibold text-primary-50 shadow-sm hover:bg-primary-800`;
	const secondary = `${btn} border border-surface-300 bg-surface-50 font-medium text-surface-800 hover:bg-surface-200`;
</script>

<div class="flex flex-wrap items-start justify-between gap-3" data-testid="env-signin">
	{#if pending}
		<div class="min-w-0 max-w-prose" aria-live="polite">
			<p class="flex items-center gap-2 text-sm font-medium text-surface-900" data-testid="signin-waiting">
				<span class="size-2.5 shrink-0 animate-pulse rounded-full bg-warning-500" aria-hidden="true"></span>
				Waiting for you to approve the sign-in
			</p>
			<p class="mt-1.5 text-xs leading-relaxed text-surface-600">
				A sign-in page opened in a new tab. Check that it shows this code, then approve it:
			</p>
			<p
				class="mt-2 w-fit rounded-lg border border-surface-300 bg-surface-100 px-3 py-1.5 font-mono text-lg font-semibold tracking-wider text-surface-900"
			>
				{pending.code}
			</p>
			<p class="mt-2 text-xs text-surface-600">
				No tab?
				<a
					href={pending.url}
					target="_blank"
					rel="noopener noreferrer"
					class="font-medium text-surface-800 underline decoration-primary-500 underline-offset-2 hover:text-surface-900"
					>Open the sign-in page</a
				>.
			</p>
		</div>
		<button type="button" class={secondary} onclick={() => end('Sign-in cancelled.')}>Cancel</button>
	{:else if signedIn}
		<div class="flex min-w-0 items-start gap-2.5">
			<span class="mt-1.5 size-2.5 shrink-0 rounded-full bg-success-500" aria-hidden="true"></span>
			<p class="min-w-0 text-sm text-surface-800">
				<span class="font-medium text-surface-900">Signed in</span>
				{#if identity}
					as <span class="font-mono text-xs break-all text-surface-700">{identity}</span>
				{/if}
			</p>
		</div>
		<button type="button" class={secondary} disabled={busy} onclick={signOut}>Sign out</button>
	{:else}
		<div class="min-w-0 max-w-prose">
			<p class="flex items-center gap-2.5 text-sm font-medium text-surface-900">
				<span class="size-2.5 shrink-0 rounded-full bg-surface-400" aria-hidden="true"></span>
				Not signed in to {env.label}
			</p>
			{#if command}
				<p class="mt-1.5 text-xs leading-relaxed text-surface-600">
					This env signs in through an AWS CLI profile. Run this in a terminal, then Re-check:
				</p>
				<code
					class="mt-1.5 block w-fit rounded bg-surface-200 px-2 py-1 font-mono text-xs break-all text-surface-800"
					>{command}</code
				>
			{:else if message || notice}
				<p class="mt-1.5 text-xs leading-relaxed text-warning-800" role="status">{message || notice}</p>
			{:else}
				<p class="mt-1.5 text-xs leading-relaxed text-surface-600">
					Sign in once with your AWS access portal account. Envs that share a portal share the login.
				</p>
			{/if}
		</div>
		<!-- A profile env's login happens in the terminal, so Re-check asks the panel to re-read the
		     env list rather than POSTing a login that can only 409 again. -->
		<button type="button" class={primary} disabled={busy} onclick={command ? onSignIn : signIn}>
			{command ? 'Re-check' : 'Sign in'}
		</button>
	{/if}
</div>
