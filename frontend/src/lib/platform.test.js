import { describe, it, expect } from 'vitest';
import { isMac, isWindows, fileManagerName, revealLabel } from './platform.js';

describe('platform helper', () => {
	it('exports boolean flags for mac and windows', () => {
		expect(typeof isMac).toBe('boolean');
		expect(typeof isWindows).toBe('boolean');
	});

	it('exports appropriate file manager name and reveal label', () => {
		if (isMac) {
			expect(fileManagerName).toBe('Finder');
			expect(revealLabel).toBe('Show in Finder');
		} else if (isWindows) {
			expect(fileManagerName).toBe('File Explorer');
			expect(revealLabel).toBe('Show in File Explorer');
		} else {
			expect(fileManagerName).toBe('File Manager');
			expect(revealLabel).toBe('Show in File Manager');
		}
	});
});
