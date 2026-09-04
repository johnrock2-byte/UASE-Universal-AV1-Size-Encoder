# UASE — Universal AV1 Size Encoder

A smart PowerShell encoding pipeline that fits entire TV seasons or single movies to exact storage budgets (e.g., DVD-R, DVD-DL, BD-R, CD-R) using **SVT-AV1** and **Opus**.

Instead of guessing bitrates or hoping Constant Rate Factor (CRF) fits your physical media, UASE measures the actual visual complexity of every frame across your entire season and distributes bits proportionally. Action-heavy episodes get the bandwidth they need, dialogue-heavy scenes conserve space, and every file outputs as a standalone `.mkv` with intact chapters, audio, and subtitles.

---

## Why UASE?

* **The Problem with CRF:** Modern encoders prioritize CRF, which delivers consistent quality but completely unpredictable file sizes. You cannot reliably burn a season to a 4.7 GB disc using CRF.
* **The Problem with Standard 2-Pass:** Traditional batch scripts calculate a single average bitrate ($\frac{\text{Total Capacity}}{\text{Total Runtime}}$) and apply it universally. This over-allocates bits to quiet dialogue and starves chaotic action sequences or space battles of bandwidth.
* **The UASE Solution:** Revives the classic "compressibility check" concept popularized by AutoGK and adapts it for modern AV1 encoding. It performs a rapid 320p pre-scan across all files to build an entropy profile, dynamically calculates each episode's ideal share of the disc pool, and executes an optimal 2-pass encode.

---

## Architecture & How It Works

```text
[Source Media Files]
         │
         ▼
[Step 1: Hardware-Accelerated Proxy]
  Auto-detects: NVENC ──► AMF ──► QSV ──► CPU Fallback
  Generates clean, artifact-free 320p intermediate streams
         │
         ▼
[Step 2: Rapid AV1 Complexity Benchmark]
  Executes high-speed SVT-AV1 scan (Preset 11, CRF 32) at 500–700+ FPS
  Measures exact AV1 motion and structural compressibility per episode
         │
         ▼
[Step 3: Global Capacity Budgeting]
  Deducts total Opus audio overhead from user-defined capacity (e.g., 4300 MB)
  Dynamically assigns kbps to each file based on its measured complexity ratio
  Displays allocation table and pauses for user verification
         │
         ▼
[Step 4: Master 2-Pass CPU Render]
  10-bit SVT-AV1 encode directly from untouched master files
  Applies Lanczos scaling, optional BWDIF deinterlacing, and synthetic film grain
  Passes through original subtitles and preserves chapter markers

```

---

## Key Features

* **Hardware Auto-Detection:** Probes your system for NVIDIA NVENC, AMD AMF, Intel Quick Sync, or fast software encoding to run the 320p proxy generation as quickly as possible.
* **Global Season Bitrate Pooling:** Treats an entire season as a single shared bucket of bits rather than isolated files.
* **Preserves Individual Files:** Outputs clean, separate `.mkv` files directly into `.\encoded\`—no concatenating or manual splitting required.
* **Any Resolution or Target Size:** Supports presets (480p, 720p, 1080p, 4K) or arbitrary custom resolutions (`WIDTHxHEIGHT`) for custom aspect ratios and single feature films.
* **SVT-AV1 Film Grain Synthesis:** Strips heavy source grain during encoding and regenerates it synthetically on playback via film-grain tables, eliminating grain-induced bit starvation.
* **Opus Audio Compression:** High-efficiency multichannel Opus encoding (Mono, Stereo, 5.1, or 7.1 Surround).
* **Metadata & Subtitle Integrity:** Direct lossless stream copy for SRT, ASS, PGS, and VobSub subtitle tracks, alongside chapter marker retention.

---

## Prerequisites

1. **Windows PowerShell 5.1+** or **PowerShell 7+**
2. **FFmpeg & FFprobe:** Must be accessible in your system `PATH`.
* Ensure your FFmpeg build includes `libsvtav1`, `libopus`, and hardware encoding libraries (such as the Gyan.dev full build).


3. **GPU Drivers (Optional, for hardware proxying):**
* NVIDIA: Driver supporting NVENC API 13.0+
* AMD: Modern Adrenalin drivers supporting AMF
* Intel: Intel Graphics drivers supporting Quick Sync



---

## Quick Start

1. Download `uase.ps1` and place it inside the directory containing your source video files (`.mkv`, `.mp4`, or `.avi`).
2. Open PowerShell in that directory.
3. Run the script with an execution policy bypass:
```powershell
powershell -ExecutionPolicy Bypass -File .\uase.ps1

```


4. Follow the interactive prompts to select your target size, resolution, audio channels, and grain parameters.
5. Review the calculated bitrates in the generated table, press `Y` to confirm, and let the batch encode run. Finished files will appear in `.\encoded\`.

---

## Configuration & Tuning Guide

### Common Storage Targets

| Target Media | Suggested MB Budget | Notes |
| --- | --- | --- |
| **DVD-R (Single Layer)** | `4300` | Safe lead-out limit for 4.7 GB discs (Default) |
| **DVD+R DL (Dual Layer)** | `8100` | Safe limit for 8.5 GB dual-layer discs |
| **BD-R (Single Layer)** | `23000` | Safe limit for 25 GB Blu-ray data discs |
| **CD-R** | `700` | Useful for short films or single anime episodes |

### Film Grain Synthesis Settings

AV1's film grain engine analyzes and strips noise from the source video, encoding only the clean underlying image, and writes parametric instructions for the media player to re-synthesize grain in real time:

* **`10` (Heavy / Gritty):** High-ISO live-action cinema, Super 16mm film stock, or gritty sci-fi (*Battlestar Galactica*, *The Walking Dead*).
* **`4` to `6` (Light / Natural):** Standard 35mm film stock, modern drama, and standard cinematic releases (Default: `5`).
* **`0` (Clean / Disabled):** Modern digital sensors, clean CGI, and 2D animation/anime. Prevents unnecessary synthetic noise over flat artwork.

### Audio Allocation Strategy

Opus delivers transparent quality at significantly lower bitrates than AC3 or AAC:

* **Stereo (2.0):** `64 kbps` provides transparent stereo playback while reserving maximum capacity for the video bitstream.
* **Surround (5.1):** `128 kbps` preserves surround separation and LFE dynamics without heavily eating into video disc space.

### Interlacing & Combing

If you are encoding older broadcast television captures or DVD rips (common with 29.97 fps NTSC sources), select option `1` during the scan prompt. This inserts the `bwdif=mode=0` deinterlacer into the filter chain, preventing interlace combing artifacts from becoming permanently encoded into the progressive AV1 video.

---

## License

This project is dedicated to the public domain under the [Unlicense](https://www.google.com/search?q=LICENSE). You are free to use, modify, distribute, or integrate this software for any purpose.
