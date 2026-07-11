import { describe, it, expect } from 'vitest';
import { computeStats, formatDateRange, formatSize } from './stats.js';

const photo = (over = {}) => ({
	fbid: 'p',
	exists: true,
	file_size_bytes: 1000,
	creation_at: null,
	post_timestamp: null,
	taken_timestamp: null,
	...over
});

const INV = {
	albums: [
		{
			fb_album_id: 'a1',
			origin: null,
			count_selected: 3,
			photos: [
				photo({ taken_timestamp: '2026-07-01T10:00:00', file_size_bytes: 2_000_000 }),
				photo({ post_timestamp: '2026-07-03T10:00:00', file_size_bytes: 1_000_000 })
			]
		},
		{
			fb_album_id: 'a2',
			origin: 'Mobile uploads',
			count_selected: 1,
			photos: [photo({ taken_timestamp: '2026-06-29T08:00:00', file_size_bytes: 500_000 })]
		}
	],
	archived_albums: [
		{ fb_album_id: 'z1', origin: null, count_selected: 0, photos: [photo({ file_size_bytes: 100 })] }
	],
	non_album: [photo({ creation_at: '2026-07-05T20:00:00', file_size_bytes: 300_000 })],
	archive: [photo({ post_timestamp: '2026-07-04T12:00:00', file_size_bytes: 400_000 })],
	videos: [
		// videos carry the THUMBNAIL size in file_size_bytes — must not join the media sum
		photo({ post_timestamp: '2026-07-02T09:00:00', file_size_bytes: 999_999_999 })
	]
};

describe('computeStats', () => {
	const s = computeStats(INV);

	it('splits main vs derived vs archived albums', () => {
		expect(s.mainAlbums).toBe(1);
		expect(s.derivedAlbums).toBe(1);
		expect(s.archivedAlbums).toBe(1);
	});

	it('counts every photo everywhere, and videos separately', () => {
		expect(s.totalPhotos).toBe(6); // 3 in albums, 1 archived-album, 1 non-album, 1 archive
		expect(s.totalVideos).toBe(1);
	});

	it('sums photo bytes only (video field is the thumbnail size)', () => {
		expect(s.mediaBytes).toBe(2_000_000 + 1_000_000 + 500_000 + 100 + 300_000 + 400_000);
	});

	it('finds the date range across photos AND videos', () => {
		expect(s.dateRange.start).toBe('2026-06-29T08:00:00');
		expect(s.dateRange.end).toBe('2026-07-05T20:00:00');
	});

	it('totals curation progress across albums', () => {
		expect(s.selectedCount).toBe(4);
		expect(s.albumCount).toBe(2);
	});

	it('degrades gracefully on an empty/absent inventory', () => {
		const empty = computeStats({});
		expect(empty.totalPhotos).toBe(0);
		expect(empty.dateRange).toBeNull();
	});
});

describe('formatDateRange', () => {
	const now = new Date('2026-07-11T00:00:00');

	it('formats a same-year range without years', () => {
		expect(
			formatDateRange({ start: '2026-06-29T08:00:00', end: '2026-07-05T20:00:00' }, now)
		).toBe('Jun 29 (Mon) – Jul 5 (Sun)');
	});

	it('adds years when the range is not the current year', () => {
		expect(
			formatDateRange({ start: '2025-06-30T08:00:00', end: '2025-07-06T20:00:00' }, now)
		).toBe('Jun 30 (Mon), 2025 – Jul 6 (Sun), 2025');
	});

	it('adds years when the range spans two years', () => {
		expect(
			formatDateRange({ start: '2025-12-29T08:00:00', end: '2026-01-04T20:00:00' }, now)
		).toBe('Dec 29 (Mon), 2025 – Jan 4 (Sun), 2026');
	});

	it('collapses a single-day range to one date', () => {
		expect(
			formatDateRange({ start: '2026-07-05T08:00:00', end: '2026-07-05T20:00:00' }, now)
		).toBe('Jul 5 (Sun)');
	});

	it('returns null for a missing range', () => {
		expect(formatDateRange(null, now)).toBeNull();
	});
});

describe('formatSize', () => {
	it('formats MB with one decimal', () => {
		expect(formatSize(4_200_000)).toBe('4.0 MB');
		expect(formatSize(536_870_912)).toBe('512.0 MB');
	});

	it('steps up to GB past 1024 MB', () => {
		expect(formatSize(1.5 * 1024 * 1024 * 1024)).toBe('1.50 GB');
	});
});
