// Shared fixtures for the DevPanel tests, shaped to the HTTP contract (contract.md C2–C5).
export const ENDPOINT = 'http://127.0.0.1:4566';
export const EXPLORER = 'http://127.0.0.1:4500/cloud-explorer/aws/storage';
export const POLLER = 'http://127.0.0.1:4566/_floci/ui';

export const LOCAL = {
	name: 'local',
	label: 'Local (floci)',
	kind: 'floci',
	region: 'ap-southeast-1',
	s3_bucket: 'archivenetwork-dev',
	table_prefix: 'archers-network-local',
	confirm: false,
	configured: true,
	signed_in: false,
	login: 'signed_out',
	identity: null,
	endpoint_url: ENDPOINT
};

const aws = (name, over = {}) => ({
	name,
	label: `${name[0].toUpperCase()}${name.slice(1)} (AWS)`,
	kind: 'aws',
	region: 'ap-southeast-1',
	s3_bucket: `archers-network-media-${name}`,
	table_prefix: `archers-network-${name}`,
	confirm: false,
	configured: true,
	signed_in: true,
	login: 'signed_in',
	identity: `arn:aws:sts::000000000000:assumed-role/Curators/${name}-me`,
	...over
});

export const DEV = aws('dev');
export const PROD = aws('prod', { confirm: true });

export const envList = (envs = [LOCAL, DEV, PROD], over = {}) => ({
	default: 'local',
	envs,
	stale_settings: [],
	errors: [],
	...over
});

export const KINDS = [
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

export function status(over = {}, prefix = 'p') {
	const tables = Object.fromEntries(
		KINDS.map((k) => [k, `${prefix}-${k === 'staff_term' ? 'staff-term' : k}`])
	);
	return {
		enabled: true,
		env: 'local',
		kind: 'floci',
		endpoint: ENDPOINT,
		on_emulator: true,
		endpoint_reachable: true,
		prefix,
		tables,
		missing: [],
		table_exists: true,
		refused: false,
		reason: null,
		counts: { ...Object.fromEntries(KINDS.map((k) => [k, 0])), album: 3, media: 12 },
		...over
	};
}

export const BUILD = { id: 'facebook-page-2026-11-01', albums: 3, photos: 10, videos: 2 };

export function publishResult(over = {}, stored = 137) {
	return {
		env: 'local',
		kind: 'floci',
		identity: 'floci',
		bucket: 'archivenetwork-dev',
		table_prefix: 'archers-network-local',
		workspace_id: BUILD.id,
		ok: true,
		steps: {
			preflight: { ok: true, checks: [{ name: 'credentials resolve', ok: true, detail: '' }] },
			publish: {
				ok: true,
				albums_inserted: 3,
				albums_updated: 0,
				media_inserted: 12,
				media_updated: 0,
				files_stored: stored,
				files_skipped: 0,
				orphans: [],
				errors: [],
				skipped_deleted: [],
				failed: []
			},
			verify: { ok: true, checks: [{ name: 'media items present', ok: true, detail: '' }] }
		},
		...over
	};
}

export const dockerState = (over = {}) => ({
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

/** Every api.js export the panel calls, as fresh mocks. */
export function apiMocks(vi) {
	return {
		autoCurate: vi.fn(),
		devRows: vi.fn(),
		devStatus: vi.fn(),
		devTables: vi.fn(),
		devTablesCreate: vi.fn(),
		devTablesDelete: vi.fn(),
		devValidate: vi.fn(),
		dockerFloci: vi.fn(),
		dockerStatus: vi.fn(),
		envLogin: vi.fn(),
		envLoginState: vi.fn(),
		envLogout: vi.fn(),
		flociUiTarget: vi.fn(),
		getCurrentReadyBuild: vi.fn(),
		listEnvs: vi.fn(),
		publish: vi.fn()
	};
}
