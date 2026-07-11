// Thumbnail-density scale for the gallery grid. One source of truth shared by the
// size control (ViewControls) and the grid (PhotoGrid). `cols` is the grid track
// floor fed to `repeat({cols}, 1fr)`; `m` matches the long-standing
// default so nothing shifts for a volunteer who never touches the control.
export const VIEW_SIZES = [
	{ id: 'xs', label: 'XS', name: 'Extra small', cols: 10 },
	{ id: 's', label: 'S', name: 'Small', cols: 8 },
	{ id: 'm', label: 'M', name: 'Medium', cols: 6 },
	{ id: 'l', label: 'L', name: 'Large', cols: 4 },
	{ id: 'xl', label: 'XL', name: 'Extra large', cols: 2 }
];

export const DEFAULT_SIZE = 'm';

export const SIZE_STORAGE_KEY = 'archivenetwork:gallery-size';

export function sizeCols(val) {
	if (typeof val === 'number') return val;
	return (VIEW_SIZES.find((s) => s.id === val) ?? VIEW_SIZES[2]).cols;
}
