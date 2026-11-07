import { createEvent, fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import TypeToConfirmDialog from './TypeToConfirmDialog.svelte';

const DETAILS = [
	{ label: 'Environment', value: 'Prod (AWS)' },
	{ label: 'Bucket', value: 's3://archers-network-media-prod' },
	{ label: 'Tables', value: 'archers-network-prod-*' },
	{ label: 'Signed in as', value: 'arn:aws:sts::x:assumed-role/Curators/me' },
	{ label: 'Albums', value: '22' },
	{ label: 'Media', value: '158' }
];

const props = (over = {}) => ({
	open: true,
	word: 'prod',
	title: 'Publish to prod?',
	details: DETAILS,
	confirmLabel: 'Publish to prod',
	onConfirm: vi.fn(),
	onCancel: vi.fn(),
	...over
});

const field = () => screen.getByRole('textbox');
const confirmBtn = () => screen.getByRole('button', { name: 'Publish to prod' });

describe('TypeToConfirmDialog', () => {
	it('keeps confirm disabled until the field equals the word exactly', async () => {
		render(TypeToConfirmDialog, props());
		expect(confirmBtn().disabled).toBe(true);
		for (const near of ['Prod', 'prod ', ' prod', 'pro', 'PROD']) {
			await fireEvent.input(field(), { target: { value: near } });
			expect(confirmBtn().disabled).toBe(true);
		}
		await fireEvent.input(field(), { target: { value: 'prod' } });
		expect(confirmBtn().disabled).toBe(false);
	});

	it('blocks paste so the word has to be typed', async () => {
		render(TypeToConfirmDialog, props());
		const paste = createEvent.paste(field());
		await fireEvent(field(), paste);
		expect(paste.defaultPrevented).toBe(true);
	});

	it('passes the typed word to onConfirm', async () => {
		const p = props();
		render(TypeToConfirmDialog, p);
		await fireEvent.input(field(), { target: { value: 'prod' } });
		await fireEvent.click(confirmBtn());
		expect(p.onConfirm).toHaveBeenCalledWith('prod');
		expect(p.onCancel).not.toHaveBeenCalled();
	});

	it('clears the field every time it reopens', async () => {
		const { rerender } = render(TypeToConfirmDialog, props());
		await fireEvent.input(field(), { target: { value: 'prod' } });
		await rerender(props({ open: false }));
		expect(screen.queryByRole('textbox')).toBeNull();
		await rerender(props({ open: true }));
		expect(field().value).toBe('');
		expect(confirmBtn().disabled).toBe(true);
	});

	it('aborts on Escape, backdrop click and Cancel, never confirming', async () => {
		const p = props();
		render(TypeToConfirmDialog, p);
		await fireEvent.input(field(), { target: { value: 'prod' } });

		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		await fireEvent.click(screen.getByRole('dialog'));
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

		expect(p.onCancel).toHaveBeenCalledTimes(3);
		expect(p.onConfirm).not.toHaveBeenCalled();
	});

	it('does not confirm when Enter is pressed before the word matches', async () => {
		const p = props();
		render(TypeToConfirmDialog, p);
		await fireEvent.input(field(), { target: { value: 'Prod' } });
		await fireEvent.submit(field().closest('form'));
		expect(p.onConfirm).not.toHaveBeenCalled();
	});

	it('labels the button with the action and renders every detail', () => {
		const { container } = render(TypeToConfirmDialog, props());
		expect(confirmBtn().textContent.trim()).toBe('Publish to prod');
		for (const { label, value } of DETAILS) {
			expect(container.textContent).toContain(label);
			expect(container.textContent).toContain(value);
		}
	});

	it('names the word to type', () => {
		render(TypeToConfirmDialog, props());
		expect(screen.getByText('prod', { selector: 'code, kbd, strong, span' })).toBeTruthy();
	});
});

describe('TypeToConfirmDialog with no word', () => {
	it('never enables confirm on an empty field when the word is empty', () => {
		// Review round 1 #7: '' === '' must not arm the button.
		render(TypeToConfirmDialog, props({ word: '' }));
		expect(confirmBtn().disabled).toBe(true);
	});
});
