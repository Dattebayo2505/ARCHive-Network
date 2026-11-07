import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import EnvBanner from './EnvBanner.svelte';

const local = { name: 'local', label: 'Local (floci)', kind: 'floci', s3_bucket: 'b', table_prefix: 'p' };
const dev = {
	name: 'dev',
	label: 'Dev (AWS)',
	kind: 'aws',
	confirm: false,
	s3_bucket: 'archers-network-media-dev',
	table_prefix: 'archers-network-dev'
};
const prod = {
	...dev,
	name: 'prod',
	label: 'Prod (AWS)',
	confirm: true,
	s3_bucket: 'archers-network-media-prod',
	table_prefix: 'archers-network-prod'
};

describe('EnvBanner', () => {
	it('renders nothing on floci', () => {
		const { container } = render(EnvBanner, { env: local, identity: null });
		expect(container.textContent.trim()).toBe('');
	});

	it('names the bucket and table prefix on an AWS env', () => {
		render(EnvBanner, { env: dev, identity: null });
		const banner = screen.getByTestId('env-banner');
		expect(banner.textContent).toContain(
			'AWS · Dev (AWS) · s3://archers-network-media-dev · archers-network-dev-*'
		);
		expect(banner.dataset.tone).toBe('aws');
	});

	it('uses the prod tone on a confirm env', () => {
		render(EnvBanner, { env: prod, identity: 'arn:aws:sts::x:assumed-role/Curators/me' });
		const banner = screen.getByTestId('env-banner');
		expect(banner.dataset.tone).toBe('prod');
		expect(banner.className).toContain('bg-error-50');
		expect(banner.textContent).toContain('arn:aws:sts::x:assumed-role/Curators/me');
	});
});
