import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import AlbumCaption from './AlbumCaption.svelte';

const album = (over = {}) => ({
	fb_album_id: '111',
	description: 'Animo Fest, day two.',
	hashtags: ['ARCHEVT'],
	caption_edited: false,
	...over
});

const openEditor = async () => {
	await fireEvent.click(screen.getByLabelText('Edit caption'));
	return screen.getByLabelText('Album caption');
};

describe('AlbumCaption', () => {
	it('shows the caption with an edit affordance', () => {
		render(AlbumCaption, { props: { album: album() } });
		expect(screen.getByText('Animo Fest, day two.')).toBeTruthy();
		expect(screen.getByLabelText('Edit caption')).toBeTruthy();
	});

	it('teaches the empty state instead of hiding the slot', () => {
		render(AlbumCaption, { props: { album: album({ description: null }) } });
		expect(screen.getByText('No caption yet.')).toBeTruthy();
		expect(screen.getByLabelText('Add caption')).toBeTruthy();
	});

	it('renders nothing for a read-only album with no caption', () => {
		const { container } = render(AlbumCaption, {
			props: { album: album({ description: null }), editable: false }
		});
		expect(container.querySelector('div')).toBeNull();
	});

	it('gives a read-only album no edit button', () => {
		render(AlbumCaption, { props: { album: album(), editable: false } });
		expect(screen.queryByLabelText('Edit caption')).toBeNull();
	});

	it('saves the edited prose', async () => {
		const onSave = vi.fn();
		render(AlbumCaption, { props: { album: album(), onSave } });

		const box = await openEditor();
		await fireEvent.input(box, { target: { value: 'Animo Fest, day three.' } });
		await fireEvent.click(screen.getByText('Save caption'));

		expect(onSave).toHaveBeenCalledWith('Animo Fest, day three.');
	});

	it('promises the hashtags survive the edit', async () => {
		render(AlbumCaption, { props: { album: album() } });
		await openEditor();
		expect(screen.getByText(/Hashtags stay attached/)).toBeTruthy();
	});

	it('cancels without saving, and keeps the original caption', async () => {
		const onSave = vi.fn();
		render(AlbumCaption, { props: { album: album(), onSave } });

		const box = await openEditor();
		await fireEvent.input(box, { target: { value: 'Something else' } });
		await fireEvent.click(screen.getByText('Cancel'));

		expect(onSave).not.toHaveBeenCalled();
		expect(screen.getByText('Animo Fest, day two.')).toBeTruthy();
	});

	it('escapes out of the editor', async () => {
		const onSave = vi.fn();
		render(AlbumCaption, { props: { album: album(), onSave } });

		const box = await openEditor();
		await fireEvent.keyDown(box, { key: 'Escape' });

		expect(onSave).not.toHaveBeenCalled();
		expect(screen.getByLabelText('Edit caption')).toBeTruthy();
	});

	it('saves on Ctrl+Enter', async () => {
		const onSave = vi.fn();
		render(AlbumCaption, { props: { album: album(), onSave } });

		const box = await openEditor();
		await fireEvent.input(box, { target: { value: 'Quick fix.' } });
		await fireEvent.keyDown(box, { key: 'Enter', ctrlKey: true });

		expect(onSave).toHaveBeenCalledWith('Quick fix.');
	});

	it('offers Reset only once the caption has been edited', async () => {
		const onReset = vi.fn();
		const { rerender } = render(AlbumCaption, { props: { album: album(), onReset } });

		await openEditor();
		expect(screen.queryByText('Reset to original')).toBeNull();
		await fireEvent.click(screen.getByText('Cancel'));

		await rerender({ album: album({ caption_edited: true }), onReset });
		await openEditor();
		await fireEvent.click(screen.getByText('Reset to original'));
		expect(onReset).toHaveBeenCalled();
	});

	it('refuses to save past the length the API enforces', async () => {
		const onSave = vi.fn();
		render(AlbumCaption, { props: { album: album({ description: 'x'.repeat(2001) }), onSave } });

		await openEditor();
		await fireEvent.click(screen.getByText('Save caption'));

		expect(onSave).not.toHaveBeenCalled();
		expect(screen.getByText('2001 / 2000')).toBeTruthy();
	});
});
