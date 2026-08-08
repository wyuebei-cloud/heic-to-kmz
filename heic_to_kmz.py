"""heic_to_kmz.py - Convert iPhone HEIC site-visit photos into a geolocated KMZ.

Pipeline:
  1. HEIC -> JPEG with STANDARD rebuilt EXIF (Apple HEIC GPS IFD is non-standard:
     missing GPSVersionID, garbage GPSProcessingMethod; direct EXIF copy breaks
     Google-ecosystem geolocation). Coordinates are extracted as exact rationals.
  2. Two image sizes per photo: browser-size (<=2048px long edge) + 128px thumbnail.
  3. Pack doc.kml + files/ + thumbs/ into a self-contained KMZ.

Usage:
  python heic_to_kmz.py <src_dir> <out.kmz> [--max-edge 2048] [--quality 85] [--thumb 128]

Dependencies: pillow, pillow-heif, exifread, piexif
"""
import argparse
import glob
import os
import struct
import zipfile
from fractions import Fraction

import exifread
import piexif
from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()

TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


# --------------------------------------------------------------------------
# Step 1: read HEIC EXIF as raw TIFF structures and rebuild a standard EXIF
# --------------------------------------------------------------------------

def _get_tiff(exif_bytes: bytes) -> bytes:
    if exif_bytes.startswith(b'Exif\x00\x00'):
        return exif_bytes[6:]
    return exif_bytes


def _parse_ifd(tiff: bytes, off: int, endian: str):
    n = struct.unpack(endian + 'H', tiff[off:off + 2])[0]
    entries = []
    for i in range(n):
        e = tiff[off + 2 + i * 12: off + 2 + (i + 1) * 12]
        if len(e) < 12:
            break
        tag = struct.unpack(endian + 'H', e[0:2])[0]
        typ = struct.unpack(endian + 'H', e[2:4])[0]
        cnt = struct.unpack(endian + 'I', e[4:8])[0]
        val = e[8:12]
        entries.append((tag, typ, cnt, val))
    return entries


def _read_raw(tiff: bytes, entry, endian: str):
    tag, typ, cnt, val = entry
    sz = TYPE_SIZES.get(typ, 1)
    nbytes = cnt * sz
    if nbytes > 4:
        off = struct.unpack(endian + 'I', val)[0]
        raw = tiff[off:off + nbytes]
    else:
        raw = val[:nbytes]
    return typ, raw


def _rationals(raw: bytes, endian: str):
    out = []
    for i in range(0, len(raw), 8):
        if i + 8 <= len(raw):
            num = struct.unpack(endian + 'I', raw[i:i + 4])[0]
            den = struct.unpack(endian + 'I', raw[i + 4:i + 8])[0]
            out.append((num, den))
    return out


def _ascii_str(raw: bytes):
    try:
        return raw.rstrip(b'\x00').decode('ascii')
    except Exception:
        return None


def rebuild_exif_from_heic(path: str) -> bytes:
    """Extract exact GPS/DateTime values from Apple HEIC EXIF and rebuild a
    standards-compliant EXIF block (adds GPSVersionID, legal GPSProcessingMethod).
    Returns raw EXIF bytes ready for JPEG save.
    """
    img = Image.open(path)
    exif_bytes = img.info.get("exif")
    if not exif_bytes:
        raise ValueError("no EXIF in HEIC")
    tiff = _get_tiff(exif_bytes)
    endian = '<' if tiff[:2] == b'II' else '>'
    ifd0_off = struct.unpack(endian + 'I', tiff[4:8])[0]
    entries0 = _parse_ifd(tiff, ifd0_off, endian)

    gps_off = None
    exif_ifd_off = None
    make = model = None
    for tag, typ, cnt, val in entries0:
        if tag == 0x010F:
            raw = _read_raw(tiff, (tag, typ, cnt, val), endian)[1]
            make = _ascii_str(raw)
        elif tag == 0x0110:
            raw = _read_raw(tiff, (tag, typ, cnt, val), endian)[1]
            model = _ascii_str(raw)
        elif tag == 0x8825:
            gps_off = struct.unpack(endian + 'I', val)[0]
        elif tag == 0x8769:
            exif_ifd_off = struct.unpack(endian + 'I', val)[0]

    dt_orig = None
    if exif_ifd_off:
        for tag, typ, cnt, val in _parse_ifd(tiff, exif_ifd_off, endian):
            if tag == 0x9003:
                raw = _read_raw(tiff, (tag, typ, cnt, val), endian)[1]
                dt_orig = _ascii_str(raw)

    gps = {}
    if gps_off:
        for e in _parse_ifd(tiff, gps_off, endian):
            tag = e[0]
            typ, raw = _read_raw(tiff, e, endian)
            gps[tag] = (typ, raw)

    gps_ifd = {}
    gps_ifd[piexif.GPSIFD.GPSVersionID] = (2, 0, 0, 0)  # required by spec
    for tag in (0x0001, 0x0003):  # lat/lon refs
        if tag in gps:
            gps_ifd[tag] = _ascii_str(gps[tag][1]) or 'N'
    for tag in (0x0002, 0x0004):  # lat/lon rationals
        if tag in gps:
            gps_ifd[tag] = [(n, d) for n, d in _rationals(gps[tag][1], endian)]
    if 0x0006 in gps:  # altitude
        gps_ifd[0x0006] = [(n, d) for n, d in _rationals(gps[0x0006][1], endian)]
    gps_ifd[piexif.GPSIFD.GPSAltitudeRef] = 0
    if 0x0007 in gps:  # time
        gps_ifd[0x0007] = [(n, d) for n, d in _rationals(gps[0x0007][1], endian)]
    if 0x001D in gps:  # date
        gps_ifd[piexif.GPSIFD.GPSDateStamp] = _ascii_str(gps[0x001D][1]) or "2026:01:01"
    if 0x0011 in gps:
        gps_ifd[piexif.GPSIFD.GPSImgDirectionRef] = _ascii_str(gps[0x0011][1]) or 'T'
    if 0x0012 in gps:
        gps_ifd[0x0012] = [(n, d) for n, d in _rationals(gps[0x0012][1], endian)]
    gps_ifd[piexif.GPSIFD.GPSProcessingMethod] = b"GPS"  # legal ASCII

    zeroth = {}
    if make:
        zeroth[piexif.ImageIFD.Make] = make.encode()
    if model:
        zeroth[piexif.ImageIFD.Model] = model.encode()
    zeroth[piexif.ImageIFD.Software] = b"heic-to-kmz"

    exif_ifd = {}
    if dt_orig:
        exif_ifd[piexif.ExifIFD.DateTimeOriginal] = dt_orig.encode()
        exif_ifd[piexif.ExifIFD.DateTimeDigitized] = dt_orig.encode()

    exif_dict = {"0th": zeroth, "Exif": exif_ifd, "GPS": gps_ifd,
                 "1st": {}, "thumbnail": None}
    return piexif.dump(exif_dict)


# --------------------------------------------------------------------------
# GPS read-back (for coordinates + verification)
# --------------------------------------------------------------------------

def read_gps_jpeg(path: str):
    """Return (lat, lon, datetime_str) from a standard-EXIF JPEG, or None."""
    with open(path, 'rb') as fh:
        tags = exifread.process_file(fh, details=True)
    lat = tags.get('GPS GPSLatitude')
    lon = tags.get('GPS GPSLongitude')
    if not lat or not lon:
        return None
    latref = str(tags.get('GPS GPSLatitudeRef', 'N')).strip()
    lonref = str(tags.get('GPS GPSLongitudeRef', 'W')).strip()
    dt = str(tags.get('EXIF DateTimeOriginal', '')).strip()

    def to_float(vals):
        fr = [Fraction(int(str(x.num)), int(str(x.den))) for x in vals.values]
        return float(fr[0]) + float(fr[1]) / 60 + float(fr[2]) / 3600

    la, lo = to_float(lat), to_float(lon)
    if latref in ('S', 's'):
        la = -la
    if lonref in ('W', 'w'):
        lo = -lo
    return la, lo, dt


# --------------------------------------------------------------------------
# Step 2 + 3: dual-size images, KML, KMZ packaging
# --------------------------------------------------------------------------

def build_kmz(src_dir: str, out_kmz: str, max_edge: int = 2048,
              quality: int = 85, thumb_size: int = 128) -> dict:
    heics = sorted(set(glob.glob(os.path.join(src_dir, "*.HEIC")) +
                       glob.glob(os.path.join(src_dir, "*.heic"))))
    if not heics:
        raise FileNotFoundError("no HEIC files in " + src_dir)

    tmp = os.path.join(os.path.dirname(out_kmz), "_kmz_build")
    files_dir = os.path.join(tmp, "files")
    thumbs_dir = os.path.join(tmp, "thumbs")
    os.makedirs(files_dir, exist_ok=True)
    os.makedirs(thumbs_dir, exist_ok=True)

    placemarks = []
    stats = {"converted": 0, "no_gps": [], "errors": []}

    for heic in heics:
        name = os.path.splitext(os.path.basename(heic))[0]
        try:
            # Step 1: HEIC -> standard-EXIF JPEG (browser size)
            img = Image.open(heic)
            w, h = img.size
            scale = min(1.0, max_edge / max(w, h))
            if scale < 1.0:
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            big = img.convert('RGB')
            exif_bytes = rebuild_exif_from_heic(heic)
            big_jpg = os.path.join(files_dir, name + ".jpg")
            big.save(big_jpg, 'JPEG', quality=quality, exif=exif_bytes,
                     optimize=True)

            gps = read_gps_jpeg(big_jpg)
            if gps is None:
                stats["no_gps"].append(name)
                continue
            la, lo, dt = gps

            # Step 2: thumbnail
            thumb = img.convert('RGB')
            thumb.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
            thumb_jpg = os.path.join(thumbs_dir, name + "_thumb.jpg")
            thumb.save(thumb_jpg, 'JPEG', quality=quality, optimize=True)

            big_rel = f"files/{name}.jpg"
            thumb_rel = f"thumbs/{name}_thumb.jpg"

            desc = (f"<![CDATA[<img src=\"{big_rel}\" width=\"800\">"
                    f"<br/><b>{name}</b><br/>{dt}<br/>"
                    f"{la:.6f}, {lo:.6f}]]>")
            pm = f"""    <Placemark>
      <name>{name}</name>
      <description>{desc}</description>
      <Style>
        <IconStyle>
          <scale>1.0</scale>
          <Icon>
            <href>{thumb_rel}</href>
          </Icon>
        </IconStyle>
      </Style>
      <Point>
        <coordinates>{lo:.6f},{la:.6f},0</coordinates>
      </Point>
    </Placemark>"""
            placemarks.append(pm)
            stats["converted"] += 1
        except Exception as e:
            stats["errors"].append(f"{name}: {e}")

    if not placemarks:
        raise RuntimeError("no placemarks produced (all photos missing GPS?)")

    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{os.path.basename(out_kmz)}</name>
    <description>{len(placemarks)} geotagged photos from HEIC</description>
{chr(10).join(placemarks)}
  </Document>
</kml>
"""
    with open(os.path.join(tmp, "doc.kml"), "w", encoding="utf-8") as fh:
        fh.write(kml)

    with zipfile.ZipFile(out_kmz, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(os.path.join(tmp, "doc.kml"), "doc.kml")
        for jpg in sorted(glob.glob(os.path.join(files_dir, "*.jpg"))):
            zf.write(jpg, "files/" + os.path.basename(jpg))
        for jpg in sorted(glob.glob(os.path.join(thumbs_dir, "*.jpg"))):
            zf.write(jpg, "thumbs/" + os.path.basename(jpg))

    # verify
    with zipfile.ZipFile(out_kmz) as zf:
        bad = zf.testzip()
        names = zf.namelist()
        kml_check = zf.read('doc.kml').decode('utf-8')
    stats["zip_integrity"] = "OK" if bad is None else f"CORRUPT: {bad}"
    stats["entries"] = len(names)
    stats["placemarks"] = len(placemarks)
    stats["size_mb"] = round(os.path.getsize(out_kmz) / 1024 / 1024, 2)
    import re
    refs = re.findall(r'src="([^"]+)"', kml_check) + re.findall(r'<href>([^<]+)</href>', kml_check)
    stats["missing_refs"] = [r for r in refs if r not in names]
    return stats


def main():
    ap = argparse.ArgumentParser(description="HEIC site-visit photos -> geolocated KMZ")
    ap.add_argument("src_dir", help="folder containing iPhone HEIC photos")
    ap.add_argument("out_kmz", help="output KMZ path")
    ap.add_argument("--max-edge", type=int, default=2048)
    ap.add_argument("--quality", type=int, default=85)
    ap.add_argument("--thumb", type=int, default=128)
    args = ap.parse_args()

    stats = build_kmz(args.src_dir, args.out_kmz, args.max_edge,
                      args.quality, args.thumb)
    print(f"KMZ written: {args.out_kmz}")
    print(f"Placemarks: {stats['converted']}")
    print(f"No-GPS skipped: {stats['no_gps']}")
    print(f"Errors: {stats['errors']}")
    print(f"Entries: {stats['entries']}, size: {stats['size_mb']} MB")
    print(f"ZIP integrity: {stats['zip_integrity']}")
    print(f"Missing refs: {stats['missing_refs']}")


if __name__ == "__main__":
    main()
