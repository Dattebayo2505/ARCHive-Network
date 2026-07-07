// Thumbnail-density scale for the gallery grid. One source of truth shared by the
// size control (ViewControls) and the grid (PhotoGrid). `min` is the grid track
// floor fed to `repeat(auto-fill, minmax(<min>, 1fr))`; `m` matches the long-standing
// default so nothing shifts for a volunteer who never touches the control.
export const VIEW_SIZES = [
	{ id: 'xs', label: 'XS', name: 'Extra small', min: '6.5rem' },
	{ id: 's', label: 'S', name: 'Small', min: '8.5rem' },
	{ id: 'm', label: 'M', name: 'Medium', min: '11rem' },
	{ id: 'l', label: 'L', name: 'Large', min: '14rem' },
	{ id: 'xl', label: 'XL', name: 'Extra large', min: '18rem' }
];

export const DEFAULT_SIZE = 'm';

export const SIZE_STORAGE_KEY = 'archivenetwork:gallery-size';

export function sizeMin(id) {
	return (VIEW_SIZES.find((s) => s.id === id) ?? VIEW_SIZES[2]).min;
}
