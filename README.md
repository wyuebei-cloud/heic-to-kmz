# heic-to-kmz

Turn iPhone HEIC site-visit photos into a geolocated Google Earth KMZ — one command.
把 iPhone HEIC 工地/现场照片变成一张带地理标记的 Google Earth 地图 —— 一条命令搞定。

![Screenshot](assets/screenshot.png)

## What it does / 功能

Scans a folder of iPhone HEIC photos, rebuilds standards-compliant EXIF (fixing Apple's broken GPS IFD), generates dual-size images (2048px browser image + 128px thumbnail), and packages everything into a single self-contained KMZ for Google Earth Pro.

扫描 iPhone HEIC 照片文件夹，重建符合标准的 EXIF（修复苹果 GPS IFD 缺陷），生成双尺寸图片（2048px 浏览图 + 128px 缩略图），打包成单个自包含 KMZ，用 Google Earth Pro 打开。

- 21 geotagged placemarks with photo thumbnails as map icons / 21 个带地理标记的标记点，照片缩略图作为地图图标
- Click a pin → 800px photo in balloon with filename, timestamp, coordinates / 点击标记 → 弹窗显示 800px 照片 + 文件名 + 时间 + 坐标
- Self-contained: photos live inside the KMZ / 自包含：照片打包在 KMZ 内部

## Why this exists / 为什么做这个

1. **Apple HEIC GPS EXIF is non-standard** — the GPS IFD lacks `GPSVersionID` and contains garbage `GPSProcessingMethod` bytes. Copying HEIC EXIF into JPEG breaks geolocation in Google Photos / My Maps (silent failure). This tool REBUILDS the EXIF instead of copying it.

   苹果 HEIC 的 GPS EXIF 不符合标准 —— GPS IFD 缺少 `GPSVersionID`，`GPSProcessingMethod` 是垃圾字节。直接把 HEIC 的 EXIF 拷进 JPEG 会导致 Google Photos / My Maps 无法定位（静默失败）。本工具重建 EXIF，而非拷贝。

2. **Google Earth Pro cannot decode HEIC** — embedding HEIC directly in KMZ shows red-X placeholders. Photos must be converted to JPEG first.

   Google Earth Pro 无法解码 HEIC —— 直接把 HEIC 塞进 KMZ 会显示红叉。必须先转成 JPEG。

3. **Dual image sizes are the standard performance pattern** — 128px thumbnails as map icons (21 icons ≈ 90KB) keep the map fast; 2048px images load one at a time in balloons on click.

   双尺寸图片是标准性能模式 —— 128px 缩略图当地图图标（21 个图标 ≈ 90KB）保证地图流畅；2048px 大图在点击时按需加载。

## Quick start / 快速开始

```bash
# Install / 安装依赖
pip install -r requirements.txt

# Run / 运行
python heic_to_kmz.py <photos_folder> <output.kmz>
```

Example / 示例:

```bash
python heic_to_kmz.py ./site_visit_2026-07-31 ./site_visit.kmz
```

Then double-click the `.kmz` to open in Google Earth Pro (desktop). / 然后双击 `.kmz` 用 Google Earth Pro（桌面版）打开。

Options / 可选参数:

```bash
python heic_to_kmz.py <src_dir> <out.kmz> [--max-edge 2048] [--quality 85] [--thumb 128]
```

## Output / 输出结构

```
output.kmz  (= a ZIP archive / 本质是 ZIP 压缩包)
├── doc.kml                # 21 placemarks: coordinates + image refs
├── files/                 # 21 browser-size JPEGs (≤2048px)
└── thumbs/                # 21 128px thumbnails (map icons)
```

## Requirements / 环境要求

- Python 3.8+
- Dependencies: `pillow`, `pillow-heif`, `exifread`, `piexif`
- Google Earth Pro (desktop) to view — the web version does not support embedded images in placemark descriptions
  Google Earth Pro（桌面版）查看 —— 网页版不支持标记弹窗内嵌图片

## Ecosystem comparison / 生态对比

Existing tools either don't support HEIC, don't rebuild the broken Apple EXIF, or don't embed both image sizes. This project does all three. See SKILL.md for details.

现有工具要么不支持 HEIC，要么不重建苹果损坏的 EXIF，要么不内嵌双尺寸图片。本项目三者都做了。详见 SKILL.md。

## Install as a Hermes/Claude skill / 作为 Agent skill 安装

```bash
hermes skills install "https://github.com/wyuebei-cloud/heic-to-kmz/raw/refs/heads/main/SKILL.md"
```

Or copy the repo's `SKILL.md` + `scripts/` into your agent's skills directory.

或把仓库里的 `SKILL.md` + `scripts/` 复制到你的 agent skills 目录。

## License / 许可证

MIT — see [LICENSE](LICENSE). / MIT —— 见 [LICENSE](LICENSE)。
