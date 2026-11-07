import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import EnvPicker from './EnvPicker.svelte';

const ENVS = [
	{ name: 'local', label: 'Local (floci)', kind: 'floci', configured: true },
	{ name: 'dev', label: 'Dev (AWS)', kind: 'aws', configured: true },
	{ name: 'prod', label: 'Prod (AWS)', kind: 'aws', confirm: true, configured: false }
];

describe('EnvPicker', () => {
	it('shows each env by label with the selected one checked', () => {
		render(EnvPicker, { envs: ENVS, selected: 'dev', onSelect: vi.fn() });
		expect(screen.getByRole('radio', { name: /Local \(floci\)/ }).checked).toBe(false);
		expect(screen.getByRole('radio', { name: /Dev \(AWS\)/ }).checked).toBe(true);
	});

	it('disables an unconfigured env and says how to configure it', () => {
		const { container } = render(EnvPicker, { envs: ENVS, selected: 'local', onSelect: vi.fn() });
		expect(screen.getByRole('radio', { name: /Prod \(AWS\)/ }).disabled).toBe(true);
		expect(screen.getByRole('radio', { name: /Dev \(AWS\)/ }).disabled).toBe(false);
		expect(container.textContent).toContain(
			"Add this env's sign-in values to environments.local.toml (see the AWS guide)"
		);
	});

	it('reports a pick, and never an unconfigured one', async () => {
		const onSelect = vi.fn();
		render(EnvPicker, { envs: ENVS, selected: 'local', onSelect });
		await fireEvent.click(screen.getByRole('radio', { name: /Dev \(AWS\)/ }));
		expect(onSelect).toHaveBeenCalledWith('dev');
		await fireEvent.click(screen.getByRole('radio', { name: /Prod \(AWS\)/ }));
		expect(onSelect).not.toHaveBeenCalledWith('prod');
	});

	it('locks every option while disabled', () => {
		render(EnvPicker, { envs: ENVS, selected: 'local', disabled: true, onSelect: vi.fn() });
		for (const r of screen.getAllByRole('radio')) expect(r.disabled).toBe(true);
	});
});
