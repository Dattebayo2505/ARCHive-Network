/**
 * The floci half of the Dev panel: the upload-target switch, the container lifecycle
 * controls, and the post-upload tab.
 *
 * `$lib/api.js` is mocked wholesale — every one of the panel's mount-time effects calls it,
 * and none of them is the subject here. The database half is stubbed as "not configured", so
 * the DB-gated block collapses and the assertions below only ever see the floci section.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
	devStatus: vi.fn(),
	devRows: vi.fn(),
	s3Status: vi.fn(),
	uploadToS3: vi.fn(),
	dockerStatus: vi.fn(),
	dockerFloci: vi.fn(),
	flociUiTarget: vi.fn(),
	autoCurate: vi.fn(),
	devSchema: vi.fn(),
	devLoad: vi.fn(),
	devValidate: vi.fn(),
	devDatabase: vi.fn(),
	devDatabaseCreate: vi.fn(),
	devDatabaseDrop: vi.fn(),
	storeUrl: (key) => `/store/${key}`
}));

vi.mock('$lib/api.js', () => api);

import DevPanel from './DevPanel.svelte';
import { flociAutoOpen, s3Target } from '$lib/s3target.svelte.js';

const EXPLORER = 'http://127.0.0.1:4500/cloud-explorer/aws/storage';
const POLLER = 'http://127.0.0.1:4566/_floci/ui';

const FLOCI_UP = {
	aws: { enabled: true, bucket: 'prod-bucket', region: 'ap-southeast-1' },
	floci: {
		enabled: true,
		bucket: 'archivenetwork-dev',
		region: 'ap-southeast-1',
		endpoint_url: 'http://127.0.0.1:4566',
		reachable: true
	}
};

const dockerState = (over = {}) => ({
	installed: true,
	engine_up: true,
	compose_available: true,
	compose_file: true,
	available: true,
	container: 'running',
	running: true,
	exists: true,
	service: 'floci',
	container_name: 'archivenetwork-floci',
	reason: null,
	...over
});

const result = (over = {}) => ({
	uploaded: 137,
	skipped: 0,
	orphans: [],
	errors: [],
	target: 'floci',
	bucket: 'archivenetwork-dev',
	region: 'ap-southeast-1',
	endpoint_url: 'http://127.0.0.1:4566',
	...over
});

/** Click Upload and step through the second-step ConfirmDialog. */
async function upload() {
	await fireEvent.click(screen.getByRole('button', { name: /^Upload to/ }));
	const dialog = await screen.findByRole('dialog');
	const [confirm] = [...dialog.querySelectorAll('button')].filter((b) =>
		/^Upload to/.test(b.textContent.trim())
	);
	await fireEvent.click(confirm);
}

beforeEach(() => {
	localStorage.clear();
	s3Target.set('floci');
	flociAutoOpen.set(true);
	vi.clearAllMocks();
	api.devStatus.mockResolvedValue({ enabled: false });
	api.devRows.mockResolvedValue({ ok: false, body: null });
	api.s3Status.mockResolvedValue(FLOCI_UP);
	api.dockerStatus.mockResolvedValue(dockerState());
	api.uploadToS3.mockResolvedValue({ ok: true, status: 200, body: result() });
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

describe('the upload-target switch', () => {
	it('keeps each target its own result, so flipping never destroys the summary', async () => {
		render(DevPanel);
		await upload();
		await screen.findByText('Uploaded');
		expect(screen.getByText('137')).toBeTruthy();

		// The regression: this used to blank the stats grid permanently.
		await fireEvent.click(screen.getByRole('switch'));
		expect(screen.queryByText('137')).toBeNull();
		expect(screen.getByText(/flip the switch back to read it/i)).toBeTruthy();

		await fireEvent.click(screen.getByRole('switch'));
		expect(await screen.findByText('137')).toBeTruthy();
	});

	it('names the target the visible summary came from', async () => {
		render(DevPanel);
		await upload();
		// The footer's own link and bucket exist nowhere else on the page.
		expect(await screen.findByRole('link', { name: /View in Floci UI/ })).toBeTruthy();
		expect(screen.getByText('archivenetwork-dev')).toBeTruthy();
	});

	it('re-probes floci when the switch is flipped back to it', async () => {
		render(DevPanel);
		await waitFor(() => expect(api.s3Status).toHaveBeenCalled());
		api.s3Status.mockClear();

		await fireEvent.click(screen.getByRole('switch')); // → aws
		expect(api.s3Status).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('switch')); // → floci
		await waitFor(() => expect(api.s3Status).toHaveBeenCalled());
	});
});

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
		api.dockerStatus.mockResolvedValue(
			dockerState({ container: 'exited', running: false })
		);
		render(DevPanel);
		expect(await screen.findByText('Container exited')).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Start' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'Stop' })).toBeNull();
	});

	it('says so when the container has never been created', async () => {
		api.dockerStatus.mockResolvedValue(
			dockerState({ container: null, running: false, exists: false })
		);
		render(DevPanel);
		expect(await screen.findByText('Container not created yet')).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Create and start' })).toBeTruthy();
	});

	it('sends the verb and re-renders from the reply, not from optimism', async () => {
		api.dockerStatus.mockResolvedValue(dockerState());
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
		api.s3Status.mockResolvedValue({
			...FLOCI_UP,
			floci: { ...FLOCI_UP.floci, reachable: false }
		});
		render(DevPanel);
		// The terminal instruction is still the honest fallback when there is no button to press.
		expect(await screen.findByText(/docker compose up -d/)).toBeTruthy();
		expect(screen.queryByText(/^Container/)).toBeNull();
		expect(screen.queryByRole('button', { name: 'Rebuild image' })).toBeNull();
	});

	it('replaces the terminal instruction with a Start button when Docker is usable', async () => {
		api.dockerStatus.mockResolvedValue(dockerState({ container: 'exited', running: false }));
		api.s3Status.mockResolvedValue({
			...FLOCI_UP,
			floci: { ...FLOCI_UP.floci, reachable: false }
		});
		render(DevPanel);
		expect(await screen.findByRole('button', { name: 'Start floci' })).toBeTruthy();
		expect(screen.queryByText(/docker compose up -d/)).toBeNull();
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
		// :4500 refuses the connection until the sibling container exists, and the poller page
		// is the only thing that creates it — so a bare deep link would be worse than the
		// interstitial it replaces.
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

	it('uses the poller while the warm-up has not answered yet', async () => {
		api.flociUiTarget.mockReturnValue(new Promise(() => {})); // never resolves
		render(DevPanel);
		const link = await screen.findByRole('link', { name: /Floci UI/ });
		expect(link.getAttribute('href')).toBe(POLLER);
	});

	it('does not try to warm a UI whose emulator is down', async () => {
		api.s3Status.mockResolvedValue({
			...FLOCI_UP,
			floci: { ...FLOCI_UP.floci, reachable: false }
		});
		render(DevPanel);
		await screen.findByRole('link', { name: /Floci UI/ });
		await waitFor(() => expect(api.s3Status).toHaveBeenCalled());
		expect(api.flociUiTarget).not.toHaveBeenCalled();
	});

	it('opens a tab when the upload actually adds objects', async () => {
		render(DevPanel);
		await upload();
		// No 'noopener' feature: it makes window.open return null on SUCCESS, which is the same
		// signal a popup blocker gives — the panel then claimed a tab it had just opened was
		// blocked. Observed live before this was pinned.
		await waitFor(() => expect(window.open).toHaveBeenCalledWith(EXPLORER, '_blank'));
		expect(window.open.mock.calls[0]).toHaveLength(2);
		expect(screen.queryByText(/blocked the new tab/i)).toBeNull();
	});

	it('does not steal a tab when the build was already uploaded', async () => {
		api.uploadToS3.mockResolvedValue({
			ok: true,
			status: 200,
			body: result({ uploaded: 0, skipped: 137 })
		});
		render(DevPanel);
		await upload();
		await screen.findByText('Uploaded');
		expect(window.open).not.toHaveBeenCalled();
	});

	it('opens a tab again once a re-autocurated build uploads new keys', async () => {
		api.uploadToS3.mockResolvedValue({
			ok: true,
			status: 200,
			body: result({ uploaded: 6, skipped: 131 })
		});
		render(DevPanel);
		await upload();
		await waitFor(() => expect(window.open).toHaveBeenCalled());
	});

	it('respects the opt-out', async () => {
		flociAutoOpen.set(false);
		render(DevPanel);
		await upload();
		await screen.findByText('Uploaded');
		expect(window.open).not.toHaveBeenCalled();
	});

	it('turns a blocked popup into a visible instruction, not silence', async () => {
		vi.stubGlobal('open', vi.fn().mockReturnValue(null));
		render(DevPanel);
		await upload();
		expect(await screen.findByText(/blocked the new tab/i)).toBeTruthy();
	});

	it('never auto-opens for an AWS upload', async () => {
		s3Target.set('aws');
		api.uploadToS3.mockResolvedValue({
			ok: true,
			status: 200,
			body: result({ target: 'aws', endpoint_url: null, bucket: 'prod-bucket' })
		});
		render(DevPanel);
		await upload();
		await screen.findByText('Uploaded');
		expect(window.open).not.toHaveBeenCalled();
	});
});

describe('who owns the Start button', () => {
	it('shows exactly one Start while the emulator is down and the container is stopped', async () => {
		api.dockerStatus.mockResolvedValue(dockerState({ container: 'exited', running: false }));
		api.s3Status.mockResolvedValue({
			...FLOCI_UP,
			floci: { ...FLOCI_UP.floci, reachable: false }
		});
		render(DevPanel);
		await screen.findByRole('button', { name: 'Start floci' });
		expect(screen.queryByRole('button', { name: 'Start' })).toBeNull();
		expect(screen.getAllByRole('button', { name: /^(Start|Create and start)/ })).toHaveLength(1);
	});

	it('offers Restart, not Start, when the container runs but the endpoint is unreachable', async () => {
		// A port conflict or an overridden endpoint — starting an already-running container
		// would fix nothing, so the warning must not pretend otherwise.
		api.dockerStatus.mockResolvedValue(dockerState());
		api.s3Status.mockResolvedValue({
			...FLOCI_UP,
			floci: { ...FLOCI_UP.floci, reachable: false }
		});
		render(DevPanel);
		expect(await screen.findByRole('button', { name: 'Restart' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: /^Start/ })).toBeNull();
		expect(screen.getByRole('button', { name: 'Re-check' })).toBeTruthy();
		// And the copy must not tell them to start something that is already started.
		expect(screen.getByText(/nothing is answering at/)).toBeTruthy();
	});
});
