---
name: heic-to-kmz
description: Use when iPhone HEIC photos must become a geolocated KMZ.
---

# HEIC Site-Visit Photos → Geolocated KMZ

Converts a folder of iPhone HEIC photos (the default format for site-visit photographs) into a single self-contained KMZ that opens in Google Earth Pro with geotagged placemarks, photo thumbnails as map icons, and display-size images in balloons.

## When to use

- User provides iPhone photos (.HEIC) from a site visit / field trip and wants them placed on a map
- Any request to "put these photos on Google Earth / My Maps / a map" where source files are HEIC
- Photos need to be imported into an open-source GIS (e.g. GeoLibre Geotagged Photos) that cannot read GPS from unmodified iPhone HEIC — the EXIF rebuild doubles as a preprocessing step
- Recurring site-visit workflow: photos land in a folder, deliverable is a KMZ

## Critical background (why this pipeline exists)

1. **Apple HEIC GPS EXIF is non-standard**: the GPS IFD lacks `GPSVersionID` and has incorrect `GPSProcessingMethod` data. Copying HEIC EXIF straight into JPEG breaks geolocation in Google Photos / My Maps (silent failure). The EXIF must be rebuilt, not copied.
2. **Google Earth Pro cannot decode HEIC**: embedding HEIC directly in KMZ shows red-X placeholders. Photos must be converted to JPEG (or PNG/GIF/BMP/TIFF).
3. **Google Earth web rejects KMZ-embedded images** in feature descriptions ("Only external images are currently supported") — the KMZ workflow targets **Google Earth Pro desktop**. Web version needs externally-hosted image URLs instead.
4. **Dual image sizes** are the standard performance pattern: small thumbnails as map icons keep the map responsive; display-size images are loaded on demand in balloons. 2048px also matches the Google Earth web image size limit if ever reused there.

## Pipeline (3 steps, all in one script)

Script: `scripts/heic_to_kmz.py`.

```bash
python heic_to_kmz.py <src_dir> <out.kmz> [--max-edge 2048] [--quality 85] [--thumb 128]
```

1. **Convert**: HEIC → JPEG via pillow_heif; EXIF rebuilt with piexif (exact rational coords, GPSVersionID=2.0.0.0, GPSProcessingMethod="GPS", DateTime preserved).
2. **Dual-size**: browser image ≤2048px long edge (quality 85) into `files/`; 128px thumbnail into `thumbs/`.
3. **Pack**: writes `doc.kml` (one Placemark per photo: coordinates `lon,lat,0` — NOTE longitude first; description = `<img src="files/x.jpg" width="800">`; IconStyle href = `thumbs/x_thumb.jpg`) and zips `doc.kml + files/ + thumbs/` into `.kmz`. Then verifies ZIP integrity + reference completeness.

## Usage workflow with user

1. Confirm the photos folder + desired KMZ output path.
2. Run the script; report the stats (placemarks count, skipped no-GPS files, errors, size).
3. Open KMZ in Google Earth Pro: either double-click the file or `File → Open`. Tell the user to click a pin to see the 800px photo.
4. If user wants to inspect the KMZ contents without Google Earth: right-click → Open with WinRAR, or copy + rename to `.zip` and browse in Explorer. A manifest can also be generated via `unzip -l`.

## Pitfalls

- **Windows case-insensitive globs**: `*.HEIC` + `*.heic` double-match on Windows — dedupe with `set()` or the placemark count doubles. Already handled in script.
- **Coordinate order**: KML wants `longitude,latitude,altitude`, NOT lat,lon. Getting this backwards places pins mirrored across the globe.
- **Do not copy HEIC EXIF bytes** into JPEG (`img.save(..., exif=heic_exif_bytes)`) — that propagates the broken GPS IFD. Always rebuild via piexif.
- **No-GPS photos** are skipped and reported; never fabricate coordinates.
- **Google Earth Pro desktop** is required for embedded images. If only web is available, the KML needs external image URLs (e.g., hosted photos) instead of `files/` paths — a different build path.
- **KMZ is just ZIP**: user can rename to `.zip` or open with WinRAR to inspect; images inside are resources for KML, not standalone deliverables.
- **Cleanup**: script leaves a `_kmz_build/` temp dir next to output; trash it after packaging (or keep for inspection).
- Photos with no GPS will fail silently in the map — always show the user the skip list.

## Verification checklist

- [ ] Placemark count == number of GPS-bearing photos (no duplicates)
- [ ] `files/` count == `thumbs/` count == placemark count
- [ ] ZIP integrity OK (`testzip()` returns None)
- [ ] No missing references (every `src=`/`href=` resolves inside archive)
- [ ] Coordinates sane for expected region (report lat/lon range to user)
