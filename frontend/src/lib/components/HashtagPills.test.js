import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import HashtagPills from './HashtagPills.svelte';

describe('HashtagPills', () => {
	it('renders a pill per tag, prefixed with #', () => {
		render(HashtagPills, { props: { tags: ['ARCHEVT', 'ArchersNetwork'] } });
		expect(screen.getByText('#ARCHEVT')).toBeTruthy();
		expect(screen.getByText('#ArchersNetwork')).toBeTruthy();
	});

	it('brand-tints the canonical tag and leaves the rest neutral', () => {
		render(HashtagPills, { props: { tags: ['ARCHEVT', 'ArchersNetwork'] } });
		expect(screen.getByText('#ARCHEVT').className).toContain('bg-primary-100');
		expect(screen.getByText('#ArchersNetwork').className).toContain('bg-surface-200');
	});

	it('matches the canonical tag case-insensitively', () => {
		render(HashtagPills, { props: { tags: ['archnews'] } });
		expect(screen.getByText('#archnews').className).toContain('bg-primary-100');
	});

	it('renders nothing for an empty list', () => {
		const { container } = render(HashtagPills, { props: { tags: [] } });
		expect(container.querySelector('span')).toBeNull();
	});
});
