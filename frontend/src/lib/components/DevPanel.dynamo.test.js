/**
 * The environment-scoped half of the Dev panel: the env picker, sign-in, Publish (and its strict
 * prod confirm), and the DynamoDB table status / admin / item browser.
 *
 * `$lib/api.js` is mocked wholesale with the shapes in contract.md; Docker is stubbed as
 * unavailable so only the env and table sections vary between tests.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$lib/api.js', async () => {
	const { vi: v } = await import('vitest');
	return (await import('./DevPanel.fixtures.js')).apiMocks(v);
});

import * as api from '$lib/api.js';
import { envChoice } from '$lib/env.svelte.js';
import DevPanel from './DevPanel.svelte';
import {
	BUILD,
	DEV,
	ENDPOINT,
	KINDS,
	LOCAL,
	PROD,
	envList,
	publishResult,
	status
} from './DevPanel.fixtures.js';

const EXPIRED = 'Your AWS login expired — sign in again.';
const awsStatus = (env, over = {}) =>
	status(
		{ env: env.name, kind: 'aws', on_emulator: false, endpoint: 'AWS (ap-southeast-1)', ...over },
		env.table_prefix
	);

function statusFor(over = {}) {
	return (name) =>
		Promise.resolve(
			name === 'local' ? status(over.local) : awsStatus(name === 'dev' ? DEV : PROD, over[name])
		);
}

beforeEach(() => {
	vi.clearAllMocks();
	localStorage.clear();
	envChoice.set('local');
	localStorage.clear();
	api.listEnvs.mockResolvedValue(envList());
	api.devStatus.mockImplementation(statusFor());
	api.getCurrentReadyBuild.mockResolvedValue(BUILD);
	api.devRows.mockResolvedValue({
		ok: true,
		status: 200,
		body: { type: 'media', total: 0, limit: 10, offset: 0, rows: [] }
	});
	api.dockerStatus.mockResolvedValue({ available: false, installed: false });
	api.flociUiTarget.mockResolvedValue({ ready: false });
	api.publish.mockResolvedValue({ ok: true, status: 200, body: publishResult() });
	api.devTables.mockResolvedValue({
		endpoint_reachable: true,
		table_exists: true,
		prefix: 'p',
		tables: status().tables,
		missing: []
	});
	api.devTablesCreate.mockResolvedValue({
		ok: true,
		status: 200,
		body: { ...status(), created: [...KINDS], reset: false }
	});
	vi.stubGlobal('open', vi.fn().mockReturnValue({}));
});

afterEach(() => vi.unstubAllGlobals());

const publishBtn = (label) => screen.getByRole('button', { name: `Publish to ${label}` });

async function renderOn(name) {
	if (name !== 'local') localStorage.setItem('archive-env', name);
	const view = render(DevPanel);
	await waitFor(() => expect(api.devStatus).toHaveBeenCalledWith(name));
	await screen.findByText('Connected');
	return view;
}

describe('the environment picker', () => {
	it('selects local on a fresh browser', async () => {
		render(DevPanel);
		await waitFor(() => expect(api.devStatus).toHaveBeenCalledWith('local'));
		expect(screen.getByRole('radio', { name: /Local \(floci\)/ }).checked).toBe(true);
		expect(api.devStatus).not.toHaveBeenCalledWith('dev');
		expect(api.devStatus).not.toHaveBeenCalledWith('prod');
		expect(screen.queryByTestId('env-banner')).toBeNull();
	});

	it('falls back to the default when the stored env is no longer configured', async () => {
		localStorage.setItem('archive-env', 'dev');
		api.listEnvs.mockResolvedValue(envList([LOCAL, { ...DEV, configured: false }, PROD]));
		render(DevPanel);
		await waitFor(() => expect(api.devStatus).toHaveBeenCalledWith('local'));
		expect(screen.getByRole('radio', { name: /Local \(floci\)/ }).checked).toBe(true);
		expect(screen.getByRole('radio', { name: /Dev \(AWS\)/ }).disabled).toBe(true);
	});

	it('re-probes the new env and clears the old one’s results on a switch', async () => {
		await renderOn('local');
		await fireEvent.click(publishBtn('Local (floci)'));
		await screen.findByTestId('publish-summary');

		await fireEvent.click(screen.getByRole('radio', { name: /Dev \(AWS\)/ }));
		await waitFor(() => expect(api.devStatus).toHaveBeenCalledWith('dev'));
		expect(screen.queryByTestId('publish-summary')).toBeNull();
		expect(screen.getByTestId('env-banner').textContent).toContain('s3://archers-network-media-dev');

		await fireEvent.click(screen.getByRole('radio', { name: /Local \(floci\)/ }));
		await waitFor(() => expect(screen.queryByTestId('env-banner')).toBeNull());
		expect(screen.queryByTestId('publish-summary')).toBeNull();
	});

	it('names stale .env settings and overlay errors', async () => {
		api.listEnvs.mockResolvedValue(
			envList(undefined, {
				stale_settings: ['ARCHIVENETWORK_S3_BUCKET', 'ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX'],
				errors: ['environments.local.toml: env.personal: missing s3_bucket']
			})
		);
		render(DevPanel);
		const notices = await screen.findByTestId('env-notices');
		expect(notices.textContent).toContain('ARCHIVENETWORK_S3_BUCKET');
		expect(notices.textContent).toContain('ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX');
		expect(notices.textContent).toContain('env.personal: missing s3_bucket');
	});
});

describe('Publish', () => {
	it('publishes local with no dialog and a null confirm', async () => {
		await renderOn('local');
		await fireEvent.click(publishBtn('Local (floci)'));
		await waitFor(() => expect(api.publish).toHaveBeenCalledWith('local', null));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect((await screen.findByTestId('publish-summary')).dataset.ok).toBe('true');
	});

	it('does not publish to prod until the exact name is typed and confirmed', async () => {
		await renderOn('local');
		await fireEvent.click(screen.getByRole('radio', { name: /Prod \(AWS\)/ }));
		await waitFor(() => expect(api.devStatus).toHaveBeenCalledWith('prod'));
		await screen.findByText('Connected');

		await fireEvent.click(publishBtn('Prod (AWS)'));
		const dialog = await screen.findByRole('dialog');
		expect(api.publish).not.toHaveBeenCalled();

		// The dialog states what will be written, counts included.
		for (const text of ['Prod (AWS)', 's3://archers-network-media-prod', 'archers-network-prod-*', PROD.identity, '12'])
			expect(dialog.textContent).toContain(text);

		const field = within(dialog).getByRole('textbox');
		const confirm = within(dialog).getByRole('button', { name: 'Publish to prod' });
		await fireEvent.input(field, { target: { value: 'Prod' } });
		expect(confirm.disabled).toBe(true);
		await fireEvent.click(confirm);
		expect(api.publish).not.toHaveBeenCalled();

		await fireEvent.input(field, { target: { value: 'prod' } });
		await fireEvent.click(confirm);
		await waitFor(() => expect(api.publish).toHaveBeenCalledWith('prod', 'prod'));
		expect(api.publish).toHaveBeenCalledTimes(1);
	});

	it('never publishes when the prod dialog is cancelled', async () => {
		await renderOn('prod');
		await fireEvent.click(publishBtn('Prod (AWS)'));
		const dialog = await screen.findByRole('dialog');
		await fireEvent.input(within(dialog).getByRole('textbox'), { target: { value: 'prod' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(api.publish).not.toHaveBeenCalled();
	});

	it('flips the sign-in row to signed out on a 401', async () => {
		api.publish.mockResolvedValue({
			ok: false,
			status: 401,
			body: {
				error: 'signed_out',
				env: 'dev',
				detail: 'Your AWS login expired during Publish. Sign in again; re-running Publish is safe.'
			}
		});
		await renderOn('dev');
		await fireEvent.click(publishBtn('Dev (AWS)'));
		expect(await screen.findByText(EXPIRED)).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy();
		expect(screen.getByText(/re-running Publish is safe/)).toBeTruthy();
		expect(publishBtn('Dev (AWS)').disabled).toBe(true);
	});

	it('treats a 401 from the table probe the same way', async () => {
		api.devStatus.mockImplementation((name) =>
			Promise.resolve(name === 'dev' ? { error: 'signed_out', env: 'dev' } : status())
		);
		localStorage.setItem('archive-env', 'dev');
		render(DevPanel);
		expect(await screen.findByText(EXPIRED)).toBeTruthy();
	});

	it('is disabled with a reason until the workspace is built', async () => {
		api.getCurrentReadyBuild.mockResolvedValue(null);
		await renderOn('local');
		expect(publishBtn('Local (floci)').disabled).toBe(true);
		expect(screen.getByText('Build the ready folder from the gallery first.')).toBeTruthy();
	});

	it('names a Publish already running in another tab', async () => {
		api.publish.mockResolvedValue({
			ok: false,
			status: 409,
			body: { error: 'publish_running', env: 'local' }
		});
		await renderOn('local');
		await fireEvent.click(publishBtn('Local (floci)'));
		expect(await screen.findByText(/already running/)).toBeTruthy();
	});

	it('has no Upload or Load controls any more', async () => {
		await renderOn('local');
		expect(screen.queryByText('Upload to S3')).toBeNull();
		expect(screen.queryByText('Upload to floci')).toBeNull();
		expect(screen.queryByRole('button', { name: 'Run load' })).toBeNull();
		expect(screen.queryByRole('switch')).toBeNull();
	});
});

describe('the DynamoDB tables', () => {
	it('points at docker compose when floci is unreachable', async () => {
		api.devStatus.mockResolvedValue(
			status({ endpoint_reachable: false, table_exists: false, counts: {}, reason: 'refused' })
		);
		const { container } = render(DevPanel);
		await screen.findByText("Can't reach DynamoDB");
		expect(container.textContent).toContain('docker compose up -d');
	});

	it('offers Create tables when the tables are missing', async () => {
		api.devStatus.mockResolvedValue(status({ table_exists: false, missing: [...KINDS], counts: {} }));
		render(DevPanel);
		await screen.findByText("The tables don't exist yet");
		await fireEvent.click(screen.getByRole('button', { name: 'Create tables' }));
		await waitFor(() => expect(api.devTablesCreate).toHaveBeenCalledWith('local', false));
		await screen.findByText('Created 11 tables.');
	});

	it('names the missing tables', async () => {
		api.devStatus.mockResolvedValue(
			status({ table_exists: false, missing: ['credit'], counts: {}, endpoint: ENDPOINT })
		);
		const { container } = render(DevPanel);
		await screen.findByText('1 of 11 tables is missing');
		expect(container.textContent).toContain('p-credit');
		const credit = [...screen.getByTestId('table-list').querySelectorAll('li')].find((li) =>
			li.textContent.includes('p-credit')
		);
		expect(credit.textContent).toContain('missing');
		expect(screen.getByRole('button', { name: 'Create tables' })).toBeTruthy();
	});

	it('shows item counts and never says PostgreSQL when ready', async () => {
		const { container } = await renderOn('local');
		expect(screen.getByText('album items')).toBeTruthy();
		expect(screen.getByText('media items')).toBeTruthy();
		expect(container.textContent).not.toContain('PostgreSQL');
	});

	it('lists every probed table with its count', async () => {
		await renderOn('local');
		const list = screen.getByTestId('table-list');
		for (const name of Object.values(status().tables)) expect(list.textContent).toContain(name);
		expect(list.querySelectorAll('li')).toHaveLength(11);
	});

	it('offers Reset and Delete tables on floci', async () => {
		await renderOn('local');
		expect(screen.getByRole('button', { name: 'Reset tables' })).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Delete tables' })).toBeTruthy();
	});

	it('hides table admin on an AWS env', async () => {
		await renderOn('dev');
		// The floci test above proves these labels exist, so null here is not vacuous.
		expect(screen.queryByRole('button', { name: 'Reset tables' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'Delete tables' })).toBeNull();
	});

	it('never offers Create tables on an AWS env', async () => {
		api.devStatus.mockImplementation(
			statusFor({ dev: { table_exists: false, missing: ['media'], counts: {} } })
		);
		localStorage.setItem('archive-env', 'dev');
		render(DevPanel);
		await screen.findByText('1 of 11 tables is missing');
		expect(screen.queryByRole('button', { name: 'Create tables' })).toBeNull();
		expect(screen.getByText(/created by hand/)).toBeTruthy();
	});

	it('does not offer Create tables when DynamoDB refused', async () => {
		api.devStatus.mockResolvedValue(
			status({ table_exists: false, refused: true, counts: {}, reason: 'AccessDenied' })
		);
		render(DevPanel);
		await screen.findByText('DynamoDB refused the request');
		expect(screen.queryByRole('button', { name: 'Create tables' })).toBeNull();
	});

	describe('the item browser', () => {
		const item = {
			id: 'g01',
			media_type: 'photo',
			album_id: 'g01',
			storage_path: 'fb-exports/archevt/headline-one/g01.jpg',
			preview_url: 'http://127.0.0.1:4566/archivenetwork-dev/fb-exports/archevt/headline-one/g01.jpg?X-Amz-Signature=abc',
			overrides: { title: 'CMS title' }
		};

		beforeEach(() => {
			api.devRows.mockResolvedValue({
				ok: true,
				status: 200,
				body: { type: 'media', total: 1, limit: 10, offset: 0, rows: [item] }
			});
		});

		it('names the env when paging rows', async () => {
			render(DevPanel);
			await screen.findByRole('table');
			expect(api.devRows).toHaveBeenCalledWith('local', 'media', 10, 0);
		});

		it('previews each media row from its presigned preview_url', async () => {
			const { container } = render(DevPanel);
			await screen.findByRole('table');
			expect(container.querySelector('tbody img').getAttribute('src')).toBe(item.preview_url);
		});

		it('starts on the table view', async () => {
			render(DevPanel);
			await screen.findByRole('table');
			expect(screen.getByRole('button', { name: 'Table' }).getAttribute('aria-pressed')).toBe('true');
			expect(screen.queryByTestId('rows-json')).toBeNull();
		});

		it('shows every attribute of the page as formatted JSON', async () => {
			render(DevPanel);
			await screen.findByRole('table');
			await fireEvent.click(screen.getByRole('button', { name: 'JSON' }));
			const pre = await screen.findByTestId('rows-json');
			expect(JSON.parse(pre.textContent)).toEqual([item]);
			expect(pre.textContent).toContain('"album_id": "g01"');
			expect(screen.queryByRole('table')).toBeNull();
		});

		it('keeps paging in the JSON view', async () => {
			const { container } = render(DevPanel);
			await screen.findByRole('table');
			await fireEvent.click(screen.getByRole('button', { name: 'JSON' }));
			await screen.findByTestId('rows-json');
			expect(container.textContent).toContain('1–1 of 1');
			expect(screen.getByRole('button', { name: 'Next' })).toBeTruthy();
		});
	});
});

describe('review round 1', () => {
	it('#1 enables Publish once the gallery reports a build, without leaving the panel', async () => {
		const view = render(DevPanel, { readyBuild: null });
		await screen.findByText('Connected');
		expect(publishBtn('Local (floci)').disabled).toBe(true);
		await view.rerender({ readyBuild: BUILD });
		await waitFor(() => expect(publishBtn('Local (floci)').disabled).toBe(false));
		// And the reverse: deleting the ready folder from the rail turns it off again.
		await view.rerender({ readyBuild: null });
		await waitFor(() => expect(publishBtn('Local (floci)').disabled).toBe(true));
	});

	it('#1 trusts the gallery prop instead of fetching its own build on mount', async () => {
		render(DevPanel, { readyBuild: BUILD });
		await screen.findByText('Connected');
		expect(api.getCurrentReadyBuild).not.toHaveBeenCalled();
		expect(publishBtn('Local (floci)').disabled).toBe(false);
	});

	it('#2 keeps this tab on its own env when another tab stored a different one', async () => {
		api.envLogout.mockResolvedValue({ ok: true, status: 200, body: { state: 'signed_out' } });
		await renderOn('dev');
		localStorage.setItem('archive-env', 'prod'); // another tab's pick
		await fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
		await waitFor(() => expect(api.listEnvs).toHaveBeenCalledTimes(2));
		expect(screen.getByRole('radio', { name: /Dev \(AWS\)/ }).checked).toBe(true);
		expect(screen.getByTestId('env-banner').dataset.tone).toBe('aws');
	});

	it('#2 routes a re-list that drops this tab’s env through a full switch', async () => {
		api.envLogout.mockResolvedValue({ ok: true, status: 200, body: { state: 'signed_out' } });
		await renderOn('dev');
		await fireEvent.click(publishBtn('Dev (AWS)'));
		await screen.findByTestId('publish-summary');
		api.listEnvs.mockResolvedValue(envList([LOCAL, { ...DEV, configured: false }, PROD]));
		await fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
		await waitFor(() => expect(api.devStatus).toHaveBeenLastCalledWith('local'));
		expect(screen.getByRole('radio', { name: /Local \(floci\)/ }).checked).toBe(true);
		// dev's result must not sit under local's bar: the switch clears it like a click would.
		expect(screen.queryByTestId('publish-summary')).toBeNull();
	});

	it('#2 keeps this tab’s env through an offline re-list', async () => {
		api.envLogout.mockResolvedValue({ ok: true, status: 200, body: { state: 'signed_out' } });
		await renderOn('dev');
		api.listEnvs.mockResolvedValue({
			api_reachable: false,
			default: 'local',
			envs: [],
			stale_settings: [],
			errors: []
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
		await waitFor(() => expect(api.listEnvs).toHaveBeenCalledTimes(2));
		expect(envChoice.name).toBe('dev');
		expect(localStorage.getItem('archive-env')).toBe('dev');
	});

	it('#3 one sign-in clears the expired mark on every env sharing the login', async () => {
		api.publish.mockResolvedValue({ ok: false, status: 401, body: { error: 'signed_out', env: 'dev' } });
		api.envLogin.mockResolvedValue({
			ok: true,
			status: 200,
			body: { verification_uri_complete: 'https://x/?c=1', user_code: 'AAAA-1111', expires_in: 60, interval: 1 }
		});
		api.envLoginState.mockResolvedValue({ ok: true, status: 200, body: { state: 'signed_in' } });
		await renderOn('dev');
		await fireEvent.click(publishBtn('Dev (AWS)'));
		await screen.findByText(EXPIRED);

		await fireEvent.click(screen.getByRole('radio', { name: /Prod \(AWS\)/ }));
		await waitFor(() => expect(api.devStatus).toHaveBeenCalledWith('prod'));
		api.publish.mockResolvedValue({ ok: false, status: 401, body: { error: 'signed_out', env: 'prod' } });
		await fireEvent.click(publishBtn('Prod (AWS)'));
		const dialog = await screen.findByRole('dialog');
		await fireEvent.input(within(dialog).getByRole('textbox'), { target: { value: 'prod' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Publish to prod' }));
		await screen.findByText(EXPIRED);

		await fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
		await waitFor(() => expect(screen.getByRole('button', { name: 'Sign out' })).toBeTruthy(), {
			timeout: 3000
		});
		await fireEvent.click(screen.getByRole('radio', { name: /Dev \(AWS\)/ }));
		await waitFor(() => expect(screen.getByRole('button', { name: 'Sign out' })).toBeTruthy());
		expect(screen.queryByText(EXPIRED)).toBeNull();
	});

	it('#4 shows why the rows failed instead of an endless skeleton', async () => {
		api.devRows.mockResolvedValue({
			ok: false,
			status: 403,
			body: { error: 'access_denied', detail: 'not authorized to perform: dynamodb:Scan' }
		});
		await renderOn('dev');
		expect(await screen.findByText(/dynamodb:Scan/)).toBeTruthy();
		expect(screen.getByTestId('rows-error')).toBeTruthy();
		expect(screen.queryByTestId('rows-skeleton')).toBeNull();
	});

	it('#4 names a 502 from the rows route on floci too', async () => {
		api.devRows.mockResolvedValue({
			ok: false,
			status: 502,
			body: { detail: "Can't reach DynamoDB at http://127.0.0.1:4566." }
		});
		await renderOn('local');
		expect(await screen.findByText(/Can't reach DynamoDB at/)).toBeTruthy();
		expect(screen.queryByTestId('rows-skeleton')).toBeNull();
	});

	it('#4 still shows the skeleton while rows are genuinely loading', async () => {
		api.devRows.mockReturnValue(new Promise(() => {}));
		await renderOn('local');
		expect(screen.getByTestId('rows-skeleton')).toBeTruthy();
		expect(screen.queryByTestId('rows-error')).toBeNull();
	});

	it('#8 a 401 from the rows route also flips the panel to signed out', async () => {
		api.devRows.mockResolvedValue({ ok: false, status: 401, body: { error: 'signed_out', env: 'dev' } });
		localStorage.setItem('archive-env', 'dev');
		render(DevPanel);
		await waitFor(() => expect(api.devRows).toHaveBeenCalledWith('dev', 'media', 10, 0));
		expect(await screen.findByText(EXPIRED)).toBeTruthy();
		await waitFor(() => expect(screen.queryByText('Connected')).toBeNull());
		expect(screen.queryByTestId('rows-skeleton')).toBeNull();
	});

	it('#11 the floci fixture is shaped like routes_envs.py’s floci entry', () => {
		expect(LOCAL).toMatchObject({ signed_in: true, login: 'signed_in', identity: 'floci' });
	});

	it('#6 does not open the prod dialog when the refreshed build is gone', async () => {
		await renderOn('prod');
		api.getCurrentReadyBuild.mockResolvedValue(null);
		await fireEvent.click(publishBtn('Prod (AWS)'));
		await waitFor(() => expect(api.getCurrentReadyBuild).toHaveBeenCalledTimes(2));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.getByText('Build the ready folder from the gallery first.')).toBeTruthy();
	});

	it('#6 does not open a dialog for an env switched to during the build refresh', async () => {
		await renderOn('prod');
		let release;
		api.getCurrentReadyBuild.mockReturnValue(new Promise((r) => (release = r)));
		await fireEvent.click(publishBtn('Prod (AWS)'));
		await fireEvent.click(screen.getByRole('radio', { name: /Local \(floci\)/ }));
		await waitFor(() => expect(api.devStatus).toHaveBeenLastCalledWith('local'));
		release(BUILD);
		await new Promise((r) => setTimeout(r, 50)); // let startPublish's await chain finish
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(api.publish).not.toHaveBeenCalled();
	});

	it('#8 drops the Connected card for an env whose login just expired', async () => {
		api.publish.mockResolvedValue({ ok: false, status: 401, body: { error: 'signed_out', env: 'dev' } });
		await renderOn('dev');
		await fireEvent.click(publishBtn('Dev (AWS)'));
		await screen.findByText(EXPIRED);
		expect(screen.queryByText('Connected')).toBeNull();
		expect(screen.getByText('Sign in to Dev (AWS) to see its tables.')).toBeTruthy();
	});

	it('#9 shows a backend-pending sign-in as pending and locks the picker meanwhile', async () => {
		api.listEnvs.mockResolvedValue(
			envList([LOCAL, { ...DEV, signed_in: false, login: 'pending', identity: null }, PROD])
		);
		api.envLoginState.mockResolvedValue({ ok: true, status: 200, body: { state: 'pending' } });
		localStorage.setItem('archive-env', 'dev');
		render(DevPanel);
		expect(await screen.findByTestId('signin-waiting')).toBeTruthy();
		await waitFor(() =>
			expect(screen.getByRole('radio', { name: /Local \(floci\)/ }).disabled).toBe(true)
		);
	});

	it('#10 not_configured mentions a missing AWS profile too', async () => {
		api.publish.mockResolvedValue({ ok: false, status: 409, body: { error: 'not_configured', env: 'dev' } });
		await renderOn('dev');
		await fireEvent.click(publishBtn('Dev (AWS)'));
		expect(await screen.findByText(/AWS profile/)).toBeTruthy();
	});
});
