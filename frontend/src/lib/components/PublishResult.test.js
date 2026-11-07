import { render, screen, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import PublishResult from './PublishResult.svelte';

const check = (name, ok = true, detail = '') => ({ name, ok, detail });

const result = (over = {}) => ({
	env: 'dev',
	kind: 'aws',
	identity: 'arn:aws:sts::x:assumed-role/Curators/me',
	bucket: 'archers-network-media-dev',
	table_prefix: 'archers-network-dev',
	workspace_id: 'facebook-page-2026-11-01',
	ok: true,
	steps: {
		preflight: { ok: true, checks: [check('credentials resolve'), check('bucket reachable')] },
		publish: {
			ok: true,
			albums_inserted: 2,
			albums_updated: 20,
			media_inserted: 8,
			media_updated: 150,
			files_stored: 8,
			files_skipped: 150,
			orphans: [],
			errors: [],
			skipped_deleted: [],
			failed: []
		},
		verify: { ok: true, checks: [check('media items present'), check('objects in bucket')] }
	},
	...over
});

const section = (name) => screen.getByRole('region', { name });

describe('PublishResult', () => {
	it('summarises a clean publish without the re-run line', () => {
		const { container } = render(PublishResult, { result: result() });
		expect(screen.getByTestId('publish-summary').dataset.ok).toBe('true');
		expect(container.textContent).not.toContain('Re-running Publish is safe.');
		for (const name of ['Preflight', 'Upload + load', 'Verify']) expect(section(name)).toBeTruthy();
		expect(within(section('Upload + load')).getByText('+8')).toBeTruthy();
	});

	it('marks the later steps Not run after a failed preflight', () => {
		const r = result({
			ok: false,
			steps: {
				preflight: {
					ok: false,
					checks: [check('credentials resolve'), check('tables exist', false, 'missing: p-media')]
				},
				publish: null,
				verify: null
			}
		});
		const { container } = render(PublishResult, { result: r });
		expect(within(section('Upload + load')).getByText('Not run')).toBeTruthy();
		expect(within(section('Verify')).getByText('Not run')).toBeTruthy();
		expect(within(section('Preflight')).getByText('missing: p-media')).toBeTruthy();
		expect(container.textContent).toContain('Re-running Publish is safe.');
		expect(screen.getByTestId('publish-summary').dataset.ok).toBe('false');
	});

	it('shows a failed verify check as failed and the whole run as not green', () => {
		const r = result({ ok: false });
		r.steps.verify = {
			ok: false,
			checks: [check('media items present'), check('objects in bucket', false, '3 objects missing')]
		};
		render(PublishResult, { result: r });
		const failed = within(section('Verify')).getByText('objects in bucket').closest('li');
		expect(failed.dataset.status).toBe('fail');
		expect(within(failed).getByText('Fail')).toBeTruthy();
		expect(screen.getByTestId('publish-summary').dataset.ok).toBe('false');
		expect(screen.getByText('Re-running Publish is safe.')).toBeTruthy();
	});

	it('renders a size-differs detail as a warning, not a failure', () => {
		const r = result();
		r.steps.verify.checks[1] = check(
			'objects in bucket',
			true,
			'size differs: fb-exports/archevt/a/g01.jpg (local 120 B, bucket 118 B)'
		);
		render(PublishResult, { result: r });
		const row = within(section('Verify')).getByText('objects in bucket').closest('li');
		expect(row.dataset.status).toBe('warn');
		expect(within(row).getByText('Warning')).toBeTruthy();
		expect(within(row).getByText(/size differs/)).toBeTruthy();
		expect(screen.getByTestId('publish-summary').dataset.ok).toBe('true');
	});

	it('lists orphans, per-file errors and tombstoned items when present', () => {
		const r = result({ ok: false });
		r.steps.publish = {
			...r.steps.publish,
			ok: false,
			orphans: ['posts/media/x.jpg'],
			errors: ['g07: AccessDenied on PutObject'],
			skipped_deleted: ['g02']
		};
		const { container } = render(PublishResult, { result: r });
		expect(container.textContent).toContain('posts/media/x.jpg');
		expect(container.textContent).toContain('g07: AccessDenied on PutObject');
		expect(container.textContent).toContain('g02');
	});
});
