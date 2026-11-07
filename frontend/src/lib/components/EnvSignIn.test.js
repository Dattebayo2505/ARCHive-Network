import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
	envLogin: vi.fn(),
	envLoginState: vi.fn(),
	envLogout: vi.fn()
}));
vi.mock('$lib/api.js', () => api);

import EnvSignIn from './EnvSignIn.svelte';

const dev = { name: 'dev', label: 'Dev (AWS)', kind: 'aws', configured: true };
const DEVICE = {
	verification_uri_complete: 'https://device.sso.example/?user_code=WXYZ-1234',
	user_code: 'WXYZ-1234',
	expires_in: 10,
	interval: 2
};
const state = (s) => ({ ok: true, status: 200, body: { state: s } });

beforeEach(() => {
	vi.useFakeTimers();
	vi.clearAllMocks();
	api.envLogin.mockResolvedValue({ ok: true, status: 200, body: DEVICE });
	api.envLogout.mockResolvedValue(state('signed_out'));
	vi.stubGlobal('open', vi.fn().mockReturnValue({}));
});

afterEach(() => {
	vi.useRealTimers();
	vi.unstubAllGlobals();
});

describe('EnvSignIn', () => {
	it('offers Sign in while signed out', () => {
		render(EnvSignIn, { env: dev, login: 'signed_out', identity: null });
		expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy();
	});

	it('shows the identity and Sign out while signed in', async () => {
		const onSignOut = vi.fn();
		const { container } = render(EnvSignIn, {
			env: dev,
			login: 'signed_in',
			identity: 'arn:aws:sts::x:assumed-role/Curators/me',
			onSignOut
		});
		expect(container.textContent).toContain('arn:aws:sts::x:assumed-role/Curators/me');
		await fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
		await vi.waitFor(() => expect(onSignOut).toHaveBeenCalled());
		expect(api.envLogout).toHaveBeenCalledWith('dev');
	});

	it('opens the verification page, shows the code, and polls until signed in', async () => {
		const onSignIn = vi.fn();
		api.envLoginState
			.mockResolvedValueOnce(state('pending'))
			.mockResolvedValueOnce(state('signed_in'));
		render(EnvSignIn, { env: dev, login: 'signed_out', identity: null, onSignIn });

		await fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
		await vi.waitFor(() =>
			expect(window.open).toHaveBeenCalledWith(DEVICE.verification_uri_complete, '_blank', 'noopener')
		);
		expect(await screen.findByText('WXYZ-1234')).toBeTruthy();

		await vi.advanceTimersByTimeAsync(2000);
		expect(api.envLoginState).toHaveBeenCalledTimes(1);
		expect(onSignIn).not.toHaveBeenCalled();

		await vi.advanceTimersByTimeAsync(2000);
		expect(api.envLoginState).toHaveBeenCalledTimes(2);
		expect(api.envLoginState).toHaveBeenCalledWith('dev');
		await vi.waitFor(() => expect(onSignIn).toHaveBeenCalledTimes(1));
		expect(screen.queryByText('WXYZ-1234')).toBeNull();
	});

	it('ends polling on an expired device code and offers Sign in again, no spinner', async () => {
		// Review focus 4: the tab was closed and the code ran out.
		api.envLoginState.mockResolvedValueOnce(state('pending')).mockResolvedValue(state('expired'));
		render(EnvSignIn, { env: dev, login: 'signed_out', identity: null });

		await fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
		await screen.findByText('WXYZ-1234');
		await vi.advanceTimersByTimeAsync(4000);

		expect(await screen.findByText(/code expired/i)).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy();
		expect(screen.queryByTestId('signin-waiting')).toBeNull();
		expect(screen.queryByText('WXYZ-1234')).toBeNull();

		const calls = api.envLoginState.mock.calls.length;
		await vi.advanceTimersByTimeAsync(20000);
		expect(api.envLoginState).toHaveBeenCalledTimes(calls);
	});

	it('gives up locally once expires_in passes, even if the server keeps saying pending', async () => {
		api.envLoginState.mockResolvedValue(state('pending'));
		render(EnvSignIn, { env: dev, login: 'signed_out', identity: null });
		await fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
		await screen.findByText('WXYZ-1234');

		await vi.advanceTimersByTimeAsync(12000);
		expect(await screen.findByText(/code expired/i)).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy();
		const calls = api.envLoginState.mock.calls.length;
		await vi.advanceTimersByTimeAsync(10000);
		expect(api.envLoginState).toHaveBeenCalledTimes(calls);
	});

	it('says so when the sign-in is denied', async () => {
		api.envLoginState.mockResolvedValue(state('denied'));
		render(EnvSignIn, { env: dev, login: 'signed_out', identity: null });
		await fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
		await screen.findByText('WXYZ-1234');
		await vi.advanceTimersByTimeAsync(2000);
		expect(await screen.findByText(/denied/i)).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy();
	});

	it('shows the CLI command for a profile env instead of a device code', async () => {
		api.envLogin.mockResolvedValue({
			ok: false,
			status: 409,
			body: { error: 'profile_login', detail: 'Run: aws sso login --profile personal' }
		});
		render(EnvSignIn, { env: { ...dev, name: 'personal' }, login: 'signed_out', identity: null });
		await fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
		expect(await screen.findByText('Run: aws sso login --profile personal')).toBeTruthy();
		expect(window.open).not.toHaveBeenCalled();
		expect(api.envLoginState).not.toHaveBeenCalled();
	});

	it('shows a notice handed down by the panel, e.g. an expired login', async () => {
		render(EnvSignIn, {
			env: dev,
			login: 'signed_out',
			identity: null,
			notice: 'Your AWS login expired — sign in again.'
		});
		await waitFor(() =>
			expect(screen.getByText('Your AWS login expired — sign in again.')).toBeTruthy()
		);
	});
});

describe('EnvSignIn review round 1', () => {
	it('resumes a sign-in the backend already has pending and collects the approval', async () => {
		// #9: a flow started before a reload or in another tab arrives as login: 'pending'.
		const onSignIn = vi.fn();
		api.envLoginState.mockResolvedValueOnce(state('pending')).mockResolvedValue(state('signed_in'));
		render(EnvSignIn, { env: dev, login: 'pending', identity: null, onSignIn });
		expect(screen.getByTestId('signin-waiting')).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'Sign in' })).toBeNull();
		await vi.advanceTimersByTimeAsync(10000);
		await vi.waitFor(() => expect(onSignIn).toHaveBeenCalledTimes(1));
		expect(api.envLogin).not.toHaveBeenCalled();
	});

	it('reports whether a device flow is in flight', async () => {
		const onPendingChange = vi.fn();
		api.envLoginState.mockResolvedValue(state('expired'));
		render(EnvSignIn, { env: dev, login: 'signed_out', identity: null, onPendingChange });
		await fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
		await screen.findByText('WXYZ-1234');
		expect(onPendingChange).toHaveBeenLastCalledWith(true);
		await vi.advanceTimersByTimeAsync(2000);
		await screen.findByText(/code expired/i);
		expect(onPendingChange).toHaveBeenLastCalledWith(false);
	});

	it('releases the picker lock when unmounted mid-flow', async () => {
		const onPendingChange = vi.fn();
		api.envLoginState.mockResolvedValue(state('pending'));
		const view = render(EnvSignIn, { env: dev, login: 'signed_out', identity: null, onPendingChange });
		await fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
		await screen.findByText('WXYZ-1234');
		expect(onPendingChange).toHaveBeenLastCalledWith(true);
		view.unmount();
		expect(onPendingChange).toHaveBeenLastCalledWith(false);
	});

	it('says so, and stays signed in, when sign-out is refused', async () => {
		// #12: a non-OK logout must not be reported as done.
		const onSignOut = vi.fn();
		api.envLogout.mockResolvedValue({ ok: false, status: 500, body: { detail: 'cache locked' } });
		render(EnvSignIn, { env: dev, login: 'signed_in', identity: 'me', onSignOut });
		await fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
		expect(await screen.findByText(/cache locked/)).toBeTruthy();
		expect(onSignOut).not.toHaveBeenCalled();
		expect(screen.getByRole('button', { name: 'Sign out' })).toBeTruthy();
	});

	it('turns a rejected sign-out into a message, not an unhandled rejection', async () => {
		api.envLogout.mockRejectedValue(new TypeError('Failed to fetch'));
		render(EnvSignIn, { env: dev, login: 'signed_in', identity: 'me' });
		await fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
		expect(await screen.findByText(/Couldn't sign out/)).toBeTruthy();
	});
});
