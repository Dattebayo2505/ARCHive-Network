/**
 * The floci half of the Dev panel on the `local` env: the container lifecycle controls, the
 * Floci UI link, and the post-Publish tab.
 *
 * `$lib/api.js` is mocked wholesale with the shapes in contract.md. floci's S3 and DynamoDB share
 * one endpoint, so `devStatus().endpoint_reachable` is what says whether floci is up.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$lib/api.js', async () => {
	const { vi: v } = await import('vitest');
	return (await import('./DevPanel.fixtures.js')).apiMocks(v);
});

import * as api from '$lib/api.js';
import { envChoice } from '$lib/env.svelte.js';
import { flociAutoOpen } from '$lib/floci.svelte.js';
import DevPanel from './DevPanel.svelte';
import {
	BUILD,
	DEV,
	EXPLORER,
	POLLER,
	dockerState,
	envList,
	publishResult,
	status
} from './DevPanel.fixtures.js';

const FLOCI_DOWN = status({ endpoint_reachable: false, table_exists: false, counts: {} });

/** Click Publish on local, which has no confirm dialog. */
async function publishLocal() {
	const btn = await screen.findByRole('button', { name: 'Publish to Local (floci)' });
	await waitFor(() => expect(btn.disabled).toBe(false));
	await fireEvent.click(btn);
}

beforeEach(() => {
	localStorage.clear();
	envChoice.set('local');
	localStorage.clear();
	flociAutoOpen.set(true);
	vi.clearAllMocks();
	api.listEnvs.mockResolvedValue(envList());
	api.devStatus.mockResolvedValue(status());
	api.devRows.mockResolvedValue({ ok: false, status: 500, body: {} });
	api.getCurrentReadyBuild.mockResolvedValue(BUILD);
	api.dockerStatus.mockResolvedValue(dockerState());
	api.publish.mockResolvedValue({ ok: true, status: 200, body: publishResult() });
	api.flociUiTarget.mockResolvedValue({
		ready: true,
		url: EXPLORER,
		explorer: EXPLORER,
		poller: POLLER,
		reason: null
	});
	vi.stubGlobal('open', vi.fn().mockReturnValue({}));
});

afterEach(() => vi.unstubAllGlobals());

describe('the container controls', () => {
	it('offers restart and stop while the container is running', async () => {
		render(DevPanel);
		expect(await screen.findByText('Container running')).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Restart' })).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Stop' })).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Rebuild image' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'Start' })).toBeNull();
	});

	it('offers start — not stop — while the container is down', async () => {
		api.dockerStatus.mockResolvedValue(dockerState({ container: 'exited', running: false }));
		render(DevPanel);
		expect(await screen.findByText('Container exited')).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Start' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'Stop' })).toBeNull();
	});

	it('says so when the container has never been created', async () => {
		api.dockerStatus.mockResolvedValue(dockerState({ container: null, running: false, exists: false }));
		render(DevPanel);
		expect(await screen.findByText('Container not created yet')).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Create and start' })).toBeTruthy();
	});

	it('sends the verb and re-renders from the reply, not from optimism', async () => {
		api.dockerFloci.mockResolvedValue({
			ok: true,
			status: 200,
			body: {
				action: 'stop',
				ok: true,
				output: 'Container archivenetwork-floci Stopped',
				docker: dockerState({ container: 'exited', running: false })
			}
		});
		render(DevPanel);
		await fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));
		expect(api.dockerFloci).toHaveBeenCalledWith('stop');
		expect(await screen.findByText('Container exited')).toBeTruthy();
	});

	it('surfaces a failed command with its own output', async () => {
		api.dockerFloci.mockResolvedValue({
			ok: true,
			status: 200,
			body: {
				action: 'start',
				ok: false,
				output: 'Error: port 4566 is already allocated',
				docker: dockerState({ container: 'exited', running: false })
			}
		});
		api.dockerStatus.mockResolvedValue(dockerState({ container: 'exited', running: false }));
		render(DevPanel);
		await fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
		expect(await screen.findByText(/didn't succeed/)).toBeTruthy();
		expect(screen.getByText(/already allocated/)).toBeTruthy();
	});

	it('hides the controls entirely when Docker is not usable', async () => {
		api.dockerStatus.mockResolvedValue(
			dockerState({
				installed: false,
				engine_up: false,
				compose_available: false,
				available: false,
				container: null,
				running: false,
				exists: false,
				reason: "Docker isn't installed"
			})
		);
		api.devStatus.mockResolvedValue(FLOCI_DOWN);
		render(DevPanel);
		// The terminal instruction is still the honest fallback when there is no button to press.
		expect((await screen.findAllByText(/docker compose up -d/)).length).toBeGreaterThan(0);
		expect(screen.queryByText(/^Container/)).toBeNull();
		expect(screen.queryByRole('button', { name: 'Rebuild image' })).toBeNull();
	});

	it('replaces the terminal instruction with a Start button when Docker is usable', async () => {
		api.dockerStatus.mockResolvedValue(dockerState({ container: 'exited', running: false }));
		api.devStatus.mockResolvedValue(FLOCI_DOWN);
		render(DevPanel);
		expect(await screen.findByRole('button', { name: 'Start floci' })).toBeTruthy();
		expect(screen.queryByText(/docker compose up -d/)).toBeNull();
	});

	it('only appears on a floci env', async () => {
		localStorage.setItem('archive-env', 'dev');
		api.devStatus.mockResolvedValue(status({ env: 'dev', kind: 'aws', on_emulator: false }));
		render(DevPanel);
		await waitFor(() => expect(api.devStatus).toHaveBeenCalledWith('dev'));
		await screen.findByText('Connected');
		expect(screen.queryByText('Container running')).toBeNull();
		expect(screen.queryByRole('link', { name: /Floci UI/ })).toBeNull();
	});
});

describe('the Floci UI', () => {
	it('links straight to the storage explorer once the UI container is up', async () => {
		render(DevPanel);
		const link = await screen.findByRole('link', { name: /Floci UI/ });
		await waitFor(() => expect(link.getAttribute('href')).toBe(EXPLORER));
		expect(link.getAttribute('target')).toBe('_blank');
		expect(link.getAttribute('rel')).toContain('noopener');
	});

	it('falls back to the poller rather than a dead deep link when the UI is cold', async () => {
		// :4500 refuses the connection until the sibling container exists, and only the poller
		// page creates it.
		api.flociUiTarget.mockResolvedValue({
			ready: false,
			url: POLLER,
			explorer: EXPLORER,
			poller: POLLER,
			reason: 'not started'
		});
		render(DevPanel);
		const link = await screen.findByRole('link', { name: /Floci UI/ });
		await waitFor(() => expect(link.getAttribute('href')).toBe(POLLER));
	});

	it('builds the poller link from the env’s endpoint_url while the warm-up is pending', async () => {
		api.flociUiTarget.mockReturnValue(new Promise(() => {})); // never resolves
		render(DevPanel);
		const link = await screen.findByRole('link', { name: /Floci UI/ });
		expect(link.getAttribute('href')).toBe(POLLER);
	});

	it('does not try to warm a UI whose emulator is down', async () => {
		api.devStatus.mockResolvedValue(FLOCI_DOWN);
		render(DevPanel);
		await screen.findByRole('link', { name: /Floci UI/ });
		await waitFor(() => expect(api.devStatus).toHaveBeenCalled());
		expect(api.flociUiTarget).not.toHaveBeenCalled();
	});

	it('opens a tab when the publish actually stores objects', async () => {
		render(DevPanel);
		await publishLocal();
		// No 'noopener' feature: it makes window.open return null on SUCCESS, the same signal a
		// popup blocker gives.
		await waitFor(() => expect(window.open).toHaveBeenCalledWith(EXPLORER, '_blank'));
		expect(window.open.mock.calls[0]).toHaveLength(2);
		expect(screen.queryByText(/blocked the new tab/i)).toBeNull();
	});

	it('does not steal a tab when everything was already published', async () => {
		api.publish.mockResolvedValue({ ok: true, status: 200, body: publishResult({}, 0) });
		render(DevPanel);
		await publishLocal();
		await screen.findByTestId('publish-summary');
		expect(window.open).not.toHaveBeenCalled();
	});

	it('opens a tab again once a re-autocurated build stores new keys', async () => {
		api.publish.mockResolvedValue({ ok: true, status: 200, body: publishResult({}, 6) });
		render(DevPanel);
		await publishLocal();
		await waitFor(() => expect(window.open).toHaveBeenCalled());
	});

	it('respects the opt-out', async () => {
		flociAutoOpen.set(false);
		render(DevPanel);
		await publishLocal();
		await screen.findByTestId('publish-summary');
		expect(window.open).not.toHaveBeenCalled();
	});

	it('turns a blocked popup into a visible instruction, not silence', async () => {
		vi.stubGlobal('open', vi.fn().mockReturnValue(null));
		render(DevPanel);
		await publishLocal();
		expect(await screen.findByText(/blocked the new tab/i)).toBeTruthy();
	});

	it('never auto-opens for an AWS env', async () => {
		localStorage.setItem('archive-env', 'dev');
		api.devStatus.mockResolvedValue(status({ env: 'dev', kind: 'aws', on_emulator: false }));
		api.publish.mockResolvedValue({
			ok: true,
			status: 200,
			body: publishResult({ env: 'dev', kind: 'aws', bucket: DEV.s3_bucket })
		});
		render(DevPanel);
		const btn = await screen.findByRole('button', { name: 'Publish to Dev (AWS)' });
		await waitFor(() => expect(btn.disabled).toBe(false));
		await fireEvent.click(btn);
		await screen.findByTestId('publish-summary');
		expect(window.open).not.toHaveBeenCalled();
	});
});

describe('who owns the Start button', () => {
	it('shows exactly one Start while the emulator is down and the container is stopped', async () => {
		api.dockerStatus.mockResolvedValue(dockerState({ container: 'exited', running: false }));
		api.devStatus.mockResolvedValue(FLOCI_DOWN);
		render(DevPanel);
		await screen.findByRole('button', { name: 'Start floci' });
		expect(screen.queryByRole('button', { name: 'Start' })).toBeNull();
		expect(screen.getAllByRole('button', { name: /^(Start|Create and start)/ })).toHaveLength(1);
	});

	it('offers Restart, not Start, when the container runs but the endpoint is unreachable', async () => {
		api.devStatus.mockResolvedValue(FLOCI_DOWN);
		render(DevPanel);
		expect(await screen.findByRole('button', { name: 'Restart' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: /^Start/ })).toBeNull();
		expect(screen.getByRole('button', { name: 'Re-check' })).toBeTruthy();
		expect(screen.getByText(/nothing is answering at/)).toBeTruthy();
	});

	it('re-probes the env when Re-check is pressed', async () => {
		api.devStatus.mockResolvedValue(FLOCI_DOWN);
		render(DevPanel);
		await fireEvent.click(await screen.findByRole('button', { name: 'Re-check' }));
		await waitFor(() => expect(api.devStatus.mock.calls.length).toBeGreaterThan(1));
		expect(api.devStatus.mock.calls.every(([name]) => name === 'local')).toBe(true);
	});
});

describe('what the banner blames', () => {
	it.each([
		['Docker unusable', { available: false, running: false, exists: false }],
		['container down', { running: false, exists: true }],
		['container up but silent', { running: true, exists: true }]
	])('names Docker in the %s message, matching the 502', async (_label, over) => {
		api.devStatus.mockResolvedValue(FLOCI_DOWN);
		api.dockerStatus.mockResolvedValue(dockerState(over));
		const { unmount } = render(DevPanel);
		await waitFor(() => expect(screen.getByRole('status').textContent).toMatch(/Docker/));
		unmount();
	});

	it('blames the API, not Docker, when the backend never answered', async () => {
		api.devStatus.mockRejectedValue(new TypeError('Failed to fetch'));
		api.dockerStatus.mockResolvedValue(dockerState({ available: false, running: false }));
		render(DevPanel);
		const banner = await screen.findByRole('status');
		await waitFor(() => expect(banner.textContent).toMatch(/API isn't answering/i));
		expect(banner.textContent).not.toMatch(/Docker isn't running/i);
	});
});
