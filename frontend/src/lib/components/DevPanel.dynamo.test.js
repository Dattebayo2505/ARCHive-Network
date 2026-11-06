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
	devTables: vi.fn(),
	devTablesCreate: vi.fn(),
	devTablesDelete: vi.fn(),
	storeUrl: (key) => `/store/${key}`
}));

vi.mock('$lib/api.js', () => api);

import DevPanel from './DevPanel.svelte';

const ENDPOINT = 'http://127.0.0.1:4566';
const PREFIX = 'p';
const KINDS = [
	'album',
	'media',
	'credit',
	'featuring',
	'staffer',
	'staff_term',
	'department',
	'category',
	'channel',
	'service',
	'users'
];
const tableName = (kind) => `${PREFIX}-${kind === 'staff_term' ? 'staff-term' : kind}`;
const TABLES = Object.fromEntries(KINDS.map((k) => [k, tableName(k)]));
const COUNTS = Object.fromEntries(KINDS.map((k) => [k, 0]));

const status = (over = {}) => ({
	enabled: true,
	endpoint: ENDPOINT,
	on_emulator: true,
	endpoint_reachable: true,
	prefix: PREFIX,
	tables: TABLES,
	missing: [],
	table_exists: true,
	refused: false,
	reason: null,
	counts: { ...COUNTS, album: 3, media: 12 },
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
	api.devTables.mockResolvedValue({
		endpoint_reachable: true,
		table_exists: true,
		prefix: PREFIX,
		tables: TABLES,
		missing: []
	});
	api.devTablesCreate.mockResolvedValue({
		ok: true,
		status: 200,
		body: { ...status(), created: [...KINDS], reset: false }
	});
});

describe('Dev panel on DynamoDB', () => {
	it('names the prefix setting when dev mode is off', async () => {
		api.devStatus.mockResolvedValue({
			enabled: false,
			endpoint_reachable: false,
			table_exists: false,
			reason: 'ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX is not set'
		});
		const { container } = render(DevPanel);
		await screen.findByText('Dev mode is not configured');
		expect(container.textContent).toContain('ARCHIVENETWORK_DYNAMODB_TABLE_PREFIX');
	});

	it('points at docker compose when floci is unreachable', async () => {
		api.devStatus.mockResolvedValue(
			status({ endpoint_reachable: false, table_exists: false, counts: {}, reason: 'refused' })
		);
		const { container } = render(DevPanel);
		await screen.findByText("Can't reach DynamoDB");
		expect(container.textContent).toContain('docker compose up -d');
	});

	it('offers Create tables when the tables are missing', async () => {
		api.devStatus.mockResolvedValue(
			status({ table_exists: false, missing: [...KINDS], counts: {} })
		);
		render(DevPanel);
		await screen.findByText("The tables don't exist yet");
		await fireEvent.click(screen.getByRole('button', { name: 'Create tables' }));
		await waitFor(() => expect(api.devTablesCreate).toHaveBeenCalledWith(false));
		await screen.findByText('Created 11 tables.');
	});

	it('names the missing tables', async () => {
		api.devStatus.mockResolvedValue({
			enabled: true,
			endpoint: ENDPOINT,
			endpoint_reachable: true,
			prefix: PREFIX,
			table_exists: false,
			refused: false,
			missing: ['credit'],
			tables: TABLES,
			on_emulator: true,
			counts: {}
		});
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
		const { container } = render(DevPanel);
		await screen.findByText('Connected');
		expect(screen.getByText('album items')).toBeTruthy();
		expect(screen.getByText('media items')).toBeTruthy();
		expect(container.textContent).not.toContain('PostgreSQL');
	});

	it('lists every probed table with its count', async () => {
		render(DevPanel);
		await screen.findByText('Connected');
		const list = screen.getByTestId('table-list');
		for (const name of Object.values(TABLES)) expect(list.textContent).toContain(name);
		expect(list.querySelectorAll('li')).toHaveLength(11);
	});

	it('offers Reset and Delete tables on the emulator', async () => {
		render(DevPanel);
		await screen.findByText('Connected');
		expect(screen.getByRole('button', { name: 'Reset tables' })).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Delete tables' })).toBeTruthy();
	});

	it('hides Reset and Delete on real AWS', async () => {
		api.devStatus.mockResolvedValue(status({ on_emulator: false, endpoint: 'AWS (ap-southeast-1)' }));
		render(DevPanel);
		await screen.findByText('Connected');
		// The emulator test above proves these labels exist, so null here is not vacuous.
		expect(screen.queryByRole('button', { name: 'Reset tables' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'Delete tables' })).toBeNull();
	});

	it('does not offer Create tables when DynamoDB refused', async () => {
		api.devStatus.mockResolvedValue(
			status({ table_exists: false, refused: true, counts: {}, reason: 'AccessDenied' })
		);
		render(DevPanel);
		await screen.findByText('DynamoDB refused the request');
		expect(screen.queryByRole('button', { name: 'Create tables' })).toBeNull();
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
				skipped_deleted: ['media:g01'],
				counts: { ...COUNTS, album: 1, media: 2 }
			}
		});
		const { container } = render(DevPanel);
		await screen.findByText('Connected');
		await fireEvent.click(screen.getByRole('button', { name: 'Run load' }));
		await screen.findByText('What was skipped');
		expect(container.textContent).toContain('tombstoned: media:g01');
		expect(container.textContent).toContain('1 tombstoned');
	});

	describe('JSON view', () => {
		const item = {
			id: 'g01',
			media_type: 'photo',
			album_id: 'g01',
			storage_path: 'fb-exports/archevt/headline-one/g01.jpg',
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
