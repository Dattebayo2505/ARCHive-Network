/**
 * The DynamoDB half of the Dev panel: table status, create/reset/delete, load stats.
 *
 * `$lib/api.js` is mocked wholesale, as in `DevPanel.floci.test.js`; floci and Docker are
 * stubbed as unavailable so only the table section varies between tests.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
	devStatus: vi.fn(),
	devRows: vi.fn(),
	s3Status: vi.fn(),
	uploadToS3: vi.fn(),
	dockerStatus: vi.fn(),
	dockerFloci: vi.fn(),
	flociUiTarget: vi.fn(),
	autoCurate: vi.fn(),
	devLoad: vi.fn(),
	devValidate: vi.fn(),
	devTable: vi.fn(),
	devTableCreate: vi.fn(),
	devTableDelete: vi.fn(),
	storeUrl: (key) => `/store/${key}`
}));

vi.mock('$lib/api.js', () => api);

import DevPanel from './DevPanel.svelte';

const ENDPOINT = 'http://127.0.0.1:4566';

const status = (over = {}) => ({
	enabled: true,
	endpoint: ENDPOINT,
	on_emulator: true,
	endpoint_reachable: true,
	table: 'archers-network-dev',
	table_exists: true,
	refused: false,
	reason: null,
	counts: { album: 3, media: 12 },
	media_root: 'workspace/store',
	media_base_url: '/store',
	...over
});

beforeEach(() => {
	vi.clearAllMocks();
	api.devStatus.mockResolvedValue(status());
	api.devRows.mockResolvedValue({
		ok: true,
		body: { type: 'media', total: 0, limit: 10, offset: 0, rows: [] }
	});
	api.s3Status.mockResolvedValue({ aws: { enabled: false }, floci: { enabled: false } });
	api.dockerStatus.mockResolvedValue({ available: false, installed: false });
	api.flociUiTarget.mockResolvedValue({ ready: false });
	api.devTable.mockResolvedValue({ endpoint_reachable: true, table_exists: true });
	api.devTableCreate.mockResolvedValue({
		ok: true,
		status: 200,
		body: { ...status(), created: true, reset: false }
	});
});

describe('Dev panel on DynamoDB', () => {
	it('names the table setting when dev mode is off', async () => {
		api.devStatus.mockResolvedValue({
			enabled: false,
			endpoint_reachable: false,
			table_exists: false,
			reason: 'ARCHIVENETWORK_DYNAMODB_TABLE is not set'
		});
		const { container } = render(DevPanel);
		await screen.findByText('Dev mode is not configured');
		expect(container.textContent).toContain('ARCHIVENETWORK_DYNAMODB_TABLE');
	});

	it('points at docker compose when floci is unreachable', async () => {
		api.devStatus.mockResolvedValue(
			status({ endpoint_reachable: false, table_exists: false, counts: {}, reason: 'refused' })
		);
		const { container } = render(DevPanel);
		await screen.findByText("Can't reach DynamoDB");
		expect(container.textContent).toContain('docker compose up -d');
	});

	it('offers Create table when the table is missing', async () => {
		api.devStatus.mockResolvedValue(status({ table_exists: false, counts: {} }));
		render(DevPanel);
		await screen.findByText("The table doesn't exist yet");
		await fireEvent.click(screen.getByRole('button', { name: 'Create table' }));
		await waitFor(() => expect(api.devTableCreate).toHaveBeenCalledWith(false));
	});

	it('shows item counts and never says PostgreSQL when ready', async () => {
		const { container } = render(DevPanel);
		await screen.findByText('Connected');
		expect(screen.getByText('album items')).toBeTruthy();
		expect(screen.getByText('media items')).toBeTruthy();
		expect(container.textContent).not.toContain('PostgreSQL');
	});

	it('hides Reset and Delete on real AWS', async () => {
		api.devStatus.mockResolvedValue(status({ on_emulator: false, endpoint: 'AWS (ap-southeast-1)' }));
		render(DevPanel);
		await screen.findByText('Connected');
		expect(screen.queryByRole('button', { name: 'Reset table' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'Delete table' })).toBeNull();
	});

	it('does not offer Create table when DynamoDB refused', async () => {
		api.devStatus.mockResolvedValue(
			status({ table_exists: false, refused: true, counts: {}, reason: 'AccessDenied' })
		);
		render(DevPanel);
		await screen.findByText('DynamoDB refused the request');
		expect(screen.queryByRole('button', { name: 'Create table' })).toBeNull();
	});

	it('lists tombstoned items under What was skipped', async () => {
		api.devLoad.mockResolvedValue({
			ok: true,
			status: 200,
			body: {
				albums_inserted: 1,
				albums_updated: 0,
				media_inserted: 2,
				media_updated: 0,
				files_stored: 2,
				files_skipped: 0,
				orphans: [],
				errors: [],
				skipped_deleted: ['MEDIA#g01'],
				counts: { album: 1, media: 2 }
			}
		});
		const { container } = render(DevPanel);
		await screen.findByText('Connected');
		await fireEvent.click(screen.getByRole('button', { name: 'Run load' }));
		await screen.findByText('What was skipped');
		expect(container.textContent).toContain('tombstoned: MEDIA#g01');
		expect(container.textContent).toContain('1 tombstoned');
	});

	describe('JSON view', () => {
		const item = {
			PK: 'MEDIA#g01',
			SK: '#META',
			id: 'g01',
			media_type: 'photo',
			storage_path: 'fb-exports/archevt/headline-one/g01.jpg',
			GSI1PK: 'ALBUM#g01',
			overrides: { title: 'CMS title' }
		};

		beforeEach(() => {
			api.devRows.mockResolvedValue({
				ok: true,
				body: { type: 'media', total: 1, limit: 10, offset: 0, rows: [item] }
			});
		});

		it('starts on the table view', async () => {
			render(DevPanel);
			await screen.findByRole('table');
			expect(screen.getByRole('button', { name: 'Table' }).getAttribute('aria-pressed')).toBe(
				'true'
			);
			expect(screen.queryByTestId('rows-json')).toBeNull();
		});

		it('shows every attribute of the page as formatted JSON', async () => {
			render(DevPanel);
			await screen.findByRole('table');
			await fireEvent.click(screen.getByRole('button', { name: 'JSON' }));
			const pre = await screen.findByTestId('rows-json');
			expect(JSON.parse(pre.textContent)).toEqual([item]);
			// Attributes outside the curated columns are exactly what this view is for.
			expect(pre.textContent).toContain('"GSI1PK": "ALBUM#g01"');
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
