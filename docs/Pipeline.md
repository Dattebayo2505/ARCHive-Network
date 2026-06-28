1. FB Export info
- Manual weekly chore 
- Store in local first

2. Preprocess raw exports
- remove unnecessary .json files
- handpick at most 10 images per album, retain all no-album photos
	- Filter picked images from .json files

X. Upload to AWS S3
X. Add to db
Things to Consider
- Python FastAPI (uv) for streamlining process
	- Dropping zip file, unzipping
		- if file picker pointed at folder already, determine if matching needed structure (posts, album, media, json files, etc.)
	- showing image thru thumbnail for selection
	- Transforming-making new folder — ready to upload and query items using script, retain original for backup purposes