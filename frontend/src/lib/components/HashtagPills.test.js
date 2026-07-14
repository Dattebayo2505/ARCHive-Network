import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import HashtagPills from './HashtagPills.svelte';

describe('HashtagPills', () => {
	it('renders a pill per tag, prefixed with #', () => {
		render(HashtagPills, { props: { tags: ['ARCHEVT', 'ArchersNetwork'] } });
		expect(screen.getByText('#ARCHEVT')).toBeTruthy();
		expect(screen.getByText('#ArchersNetwork')).toBeTruthy();
	});

	it('gives the canonical tag a solid brand pill and leaves the rest neutral', () => {
		render(HashtagPills, { props: { tags: ['ARCHEVT', 'ArchersNetwork'] } });
		const canonical = screen.getByText('#ARCHEVT').className;
		// Solid green + light ink, NOT the pale bg-primary-100 / text-primary-800 pairing:
		// the primary ramp does not invert under `.dark`, so that pairing collapses to
		// dark-green-on-dark-green (1.24:1) at night.
		expect(canonical).toContain('bg-primary-700');
		expect(canonical).toContain('text-primary-50');
		expect(canonical).not.toContain('bg-primary-100');
		expect(screen.getByText('#ArchersNetwork').className).toContain('bg-surface-200');
	});

	it('matches the canonical tag case-insensitively', () => {
		render(HashtagPills, { props: { tags: ['archnews'] } });
		expect(screen.getByText('#archnews').className).toContain('bg-primary-700');
	});

	it('renders nothing for an empty list', () => {
		const { container } = render(HashtagPills, { props: { tags: [] } });
		expect(container.querySelector('span')).toBeNull();
	});
});
