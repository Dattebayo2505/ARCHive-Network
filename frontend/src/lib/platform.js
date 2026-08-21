export const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent || navigator.platform);
export const isWindows = typeof navigator !== 'undefined' && /Win/i.test(navigator.userAgent || navigator.platform);
export const fileManagerName = isMac ? 'Finder' : isWindows ? 'File Explorer' : 'File Manager';
export const revealLabel = isMac ? 'Show in Finder' : isWindows ? 'Show in File Explorer' : 'Show in File Manager';
