#!/usr/bin/env python3
"""
UASE — Universal AV1 Size Encoder (v1.4)
Hardware-Accelerated Proxy Entropy Scanning (NVENC -> AMF -> QSV -> CPU)
Proportional Multi-File & Single Video Capacity Budgeting (SVT-AV1 / Opus)
Post-Encode Terminal Visualizer, Text Report, and Vector SVG Generator
"""

import glob
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

# Force UTF-8 output across standard streams
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Enable ANSI escape sequences on Windows console
if os.name == "nt":
    os.system("")

# --- ANSI Terminal Color Palette ---
COLORS = {
    "cyan": "\033[96m",
    "yellow": "\033[93m",
    "green": "\033[92m",
    "gray": "\033[37m",
    "darkgray": "\033[90m",
    "red": "\033[91m",
    "reset": "\033[0m",
}


def cprint(text="", color=None, end="\n"):
    if color and color.lower() in COLORS:
        sys.stdout.write(f"{COLORS[color.lower()]}{text}{COLORS['reset']}{end}")
    else:
        sys.stdout.write(f"{text}{end}")
    sys.stdout.flush()


def ask_option(prompt, default, valid_choices=None):
    if valid_choices is None:
        valid_choices = []
    while True:
        sys.stdout.write(f"{COLORS['yellow']}{prompt} [Default: {default}]: {COLORS['reset']}")
        sys.stdout.flush()
        val = sys.stdin.readline()
        if not val:
            return default
        val = val.strip()
        if not val:
            return default
        if valid_choices:
            if val in valid_choices:
                return val
            cprint(f"Invalid selection. Valid options: {', '.join(valid_choices)}", "red")
        else:
            return val


def test_hardware_encoder(encoder_name, encoder_args):
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=24",
        "-frames:v", "1", "-vf", "format=yuv420p",
        "-c:v", encoder_name, *encoder_args,
        "-f", "null", os.devnull
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0
    except Exception:
        return False


def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


# ==========================================================
# 0. Hardware Acceleration Detection
# ==========================================================
os.system("cls" if os.name == "nt" else "clear")
cprint("==========================================================", "cyan")
cprint("      UASE: UNIVERSAL AV1 SIZE ENCODER (v1.4)             ", "cyan")
cprint("==========================================================", "cyan")

cprint("Probing available acceleration engines for proxy scanning...", "darkgray")
if test_hardware_encoder("h264_nvenc", ["-preset", "p1", "-qp", "16"]):
    hardware_type = "NVIDIA NVENC (Hardware Accelerated)"
    proxy_encoder = "h264_nvenc"
    proxy_enc_args = ["-preset", "p1", "-qp", "16"]
elif test_hardware_encoder("h264_amf", ["-quality", "speed", "-qp_i", "16", "-qp_p", "16"]):
    hardware_type = "AMD AMF (Hardware Accelerated)"
    proxy_encoder = "h264_amf"
    proxy_enc_args = ["-quality", "speed", "-qp_i", "16", "-qp_p", "16"]
elif test_hardware_encoder("h264_qsv", ["-preset", "veryfast", "-global_quality", "16"]):
    hardware_type = "Intel Quick Sync Video (Hardware Accelerated)"
    proxy_encoder = "h264_qsv"
    proxy_enc_args = ["-preset", "veryfast", "-global_quality", "16"]
else:
    hardware_type = "CPU Software Fallback (libx264 ultrafast)"
    proxy_encoder = "libx264"
    proxy_enc_args = ["-preset", "ultrafast", "-crf", "16"]

cprint(f"Proxy Engine Selected: {hardware_type}\n", "green")

# ==========================================================
# 1. Target Capacity & Media Profile Selection
# ==========================================================
cprint("==========================================================", "cyan")
cprint("        TARGET CAPACITY & MEDIA PROFILE SELECTION         ", "cyan")
cprint("==========================================================", "cyan")
cprint("[!] WARNING: Smaller margins maximize picture quality but reduce headroom.", "yellow")
cprint("    Minor 2-pass rate-control variance (+/- 1%) or container muxing overhead could", "yellow")
cprint("    cause 'Max Fill' to slightly overflow physical disc boundaries.", "yellow")
cprint("    Always verify final folder size prior to burning.\n", "yellow")

cprint("DVD Single Layer (DVD+R baseline: 4,700 MB):", "gray")
cprint("  1) Safe Fill        (~517 MB margin  |  Target: 4,183 MB)")
cprint("  2) Balanced Fill    (~156 MB margin  |  Target: 4,544 MB)  <-- [DEFAULT]")
cprint("  3) Max Fill         (~81 MB margin   |  Target: 4,619 MB)")
cprint("\nDVD Dual Layer (DVD+R DL baseline: 8,548 MB):", "gray")
cprint("  4) Safe Fill        (~948 MB margin  |  Target: 7,600 MB)")
cprint("  5) Balanced Fill    (~298 MB margin  |  Target: 8,250 MB)")
cprint("  6) Max Fill         (~148 MB margin  |  Target: 8,400 MB)")
cprint("\nBD-R Single Layer (25 GB baseline: 25,025 MB):", "gray")
cprint("  7) Safe Fill        (~2,525 MB margin | Target: 22,500 MB)")
cprint("  8) Balanced Fill    (~925 MB margin  |  Target: 24,100 MB)")
cprint("  9) Max Fill         (~425 MB margin  |  Target: 24,600 MB)")
cprint("\nCD-R (700 MB baseline):", "gray")
cprint("  0) Balanced Fill    (~25 MB margin   |  Target: 675 MB)")
cprint("\nManual Entry:", "gray")
cprint("  Type any raw target value in MB directly (e.g., 4300, 15000, etc.)\n")

raw_choice = ask_option("Select media preset (0-9) or enter custom MB target", "2")
disc_presets = {
    "0": 675,
    "1": 4183,
    "2": 4544,
    "3": 4619,
    "4": 7600,
    "5": 8250,
    "6": 8400,
    "7": 22500,
    "8": 24100,
    "9": 24600,
}

if raw_choice in disc_presets:
    target_disc_mb = disc_presets[raw_choice]
elif raw_choice.isdigit():
    target_disc_mb = int(raw_choice)
else:
    cprint("Unrecognized selection. Defaulting to DVD Single Layer Balanced Fill (4,544 MB).", "yellow")
    target_disc_mb = 4544

cprint(f"Target Allocation Budget Set: {target_disc_mb} MB\n", "cyan")

# ==========================================================
# 2. Output Resolution & Aspect Ratio Selection
# ==========================================================
cprint("Target Output Resolution:", "gray")
cprint("  1) 854x480   (480p 16:9 DVD Single Layer Standard - Default)")
cprint("  2) 640x480   (480p 4:3 Vintage / Broadcast)")
cprint("  3) 1280x720  (720p HD)")
cprint("  4) 1920x1080 (1080p Full HD)")
cprint("  5) 3840x2160 (4K UHD)")
cprint("  Or enter any custom resolution as WIDTHxHEIGHT (e.g., 1920x800, 960x540)")

while True:
    res_choice = ask_option("Select preset (1-5) or enter WIDTHxHEIGHT", "1")
    if res_choice == "1":
        final_width, final_height = 854, 480
        break
    elif res_choice == "2":
        final_width, final_height = 640, 480
        break
    elif res_choice == "3":
        final_width, final_height = 1280, 720
        break
    elif res_choice == "4":
        final_width, final_height = 1920, 1080
        break
    elif res_choice == "5":
        final_width, final_height = 3840, 2160
        break
    else:
        m = re.match(r"^(\d+)x(\d+)$", res_choice)
        if m:
            final_width = int(m.group(1))
            final_height = int(m.group(2))
            if final_width % 2 != 0:
                final_width += 1
            if final_height % 2 != 0:
                final_height += 1
            break
        else:
            cprint("Invalid format. Enter 1-5 or a valid WIDTHxHEIGHT format like 1920x1080.", "red")

if final_height <= 320:
    proxy_width = final_width
    proxy_height = final_height
else:
    proxy_height = 320
    proxy_width = int(round(((final_width / final_height) * 320) / 2) * 2)

cprint(f"Output Geometry: {final_width}x{final_height} | Proxy Benchmark: {proxy_width}x{proxy_height}", "cyan")

# ==========================================================
# 3. Framerate Configuration
# ==========================================================
cprint("\nFramerate Options:", "gray")
cprint("  0) Match Source (Automatic passthrough - recommended)")
cprint("  1) 23.976 fps (Standard Film/Cinema)")
cprint("  2) 24.0 fps (True 24p)")
cprint("  3) 25.0 fps (PAL Broadcast)")
cprint("  4) 29.97 fps (NTSC Broadcast)")
cprint("  5) 59.94 fps (High Frame Rate NTSC)")
fps_choice = ask_option("Select Framerate (0-5)", "0", ["0", "1", "2", "3", "4", "5"])

fps_map = {
    "1": (["-r", "24000/1001"], "23.976 fps (Film)"),
    "2": (["-r", "24"], "24.0 fps (True 24p)"),
    "3": (["-r", "25"], "25.0 fps (PAL)"),
    "4": (["-r", "30000/1001"], "29.97 fps (NTSC)"),
    "5": (["-r", "60000/1001"], "59.94 fps (HFR)"),
}
fps_args, fps_desc = fps_map.get(fps_choice, ([], "Match Source (Passthrough)"))

# ==========================================================
# 4. Deinterlacing
# ==========================================================
cprint("\nScan Type / Deinterlacing:", "gray")
cprint("  0) Progressive (No filter - standard for modern rips/web)")
cprint("  1) Interlaced / Telecined (Apply BWDIF deinterlacer for DVD/broadcast captures)")
deint_choice = ask_option("Deinterlacing needed? (0 or 1)", "0", ["0", "1"])
deint_filter = "bwdif=mode=0," if deint_choice == "1" else ""

# ==========================================================
# 5. Film Grain Synthesis
# ==========================================================
cprint("\nSynthetic Film Grain Strength (AV1 Film Grain Engine):", "gray")
cprint("  10 = Heavy / Gritty (Super 16mm, high ISO cinema, gritty sci-fi)")
cprint("  4 to 6 = Light / Natural (Standard 35mm film stock, modern drama)")
cprint("  0 = None / Clean (Clean digital sensors, 2D animation, anime)")
raw_grain = ask_option("Enter film grain strength (0-50)", "5")
try:
    film_grain = int(raw_grain)
except ValueError:
    film_grain = 5

# ==========================================================
# 6. Audio Configuration
# ==========================================================
cprint("\nAudio Layout:", "gray")
cprint("  1) Mono (1 channel)")
cprint("  2) Stereo (2 channels - recommended for low bitrate efficiency)")
cprint("  6) 5.1 Surround (6 channels)")
cprint("  8) 7.1 Surround (8 channels)")
audio_chan_choice = ask_option("Select Audio Channels (1, 2, 6, 8)", "2", ["1", "2", "6", "8"])
audio_channels = int(audio_chan_choice)

audio_defaults = {1: "48", 2: "64", 6: "128", 8: "192"}
default_audio_bitrate = audio_defaults.get(audio_channels, "64")
raw_audio_bitrate = ask_option("Opus audio bitrate in kbps (6-512)", default_audio_bitrate)
try:
    audio_bitrate_k = int(raw_audio_bitrate)
except ValueError:
    audio_bitrate_k = int(default_audio_bitrate)

# ==========================================================
# 7. Subtitle Handling
# ==========================================================
cprint("\nSubtitle Handling:", "gray")
cprint("  1) Copy all subtitle tracks losslessly (SRT, ASS, PGS, VobSub)")
cprint("  0) Strip all subtitles")
sub_choice = ask_option("Preserve subtitles? (0 or 1)", "1", ["0", "1"])
sub_args = ["-map", "0:s?", "-c:s", "copy"] if sub_choice == "1" else ["-sn"]

# ==========================================================
# 8. SVT-AV1 Speed Preset
# ==========================================================
cprint("\nSVT-AV1 Speed Preset:", "gray")
cprint("  4 = Maximum Compression Efficiency (Highest quality, slowest)")
cprint("  5 = Balanced Quality & Encoding Throughput (~30% faster than 4)")
cprint("  6 = Fast Turnaround (Reduced CPU time)")
preset_choice = ask_option("Select AV1 Preset (4, 5, 6)", "4", ["4", "5", "6"])
av1_preset = int(preset_choice)

# ==========================================================
# 9. Post-Encode Summary Report Saving
# ==========================================================
cprint("\nPost-Encode Report Files:", "gray")
cprint("  (Terminal bitrate graphs are always shown on screen upon completion)")
cprint("  1) Yes - Write summary text file and vector SVG graph to output folder")
cprint("  0) No  - Display in console only (Do not save files)")
save_report_choice = ask_option("Save summary report and SVG to disk? (0 or 1)", "0", ["0", "1"])
save_report_files = (save_report_choice == "1")

output_dir = "encoded"
os.makedirs(output_dir, exist_ok=True)

# File collection with natural alphanumeric sorting
source_files = [
    f for f in os.listdir(".")
    if os.path.isfile(f) and Path(f).suffix.lower() in [".mkv", ".mp4", ".avi"]
]
source_files.sort(key=natural_sort_key)

if not source_files:
    cprint("\nError: No video files (.mkv, .mp4, .avi) found in current directory.", "red")
    sys.exit(1)

# ==========================================================
# Phase 1 & 2: Intermediate + AV1 Complexity Benchmark
# ==========================================================
cprint("\n==========================================================", "cyan")
cprint("=== Phase 1 & 2: Intermediate + AV1 Complexity Benchmark ===", "cyan")
cprint("==========================================================", "cyan")

episodes = []
total_av1_complexity_bytes = 0

for index, f in enumerate(source_files, 1):
    cprint(f"\n[{index}/{len(source_files)}] Analyzing: {f}", "yellow")

    # Probe duration
    dur_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", f
    ]
    try:
        dur_str = subprocess.check_output(dur_cmd, text=True).strip()
        dur = float(dur_str)
    except Exception as e:
        cprint(f"Error reading duration for {f}: {e}", "red")
        sys.exit(1)

    temp_proxy = f"temp_proxy_{index}.mkv"
    temp_av1_test = f"temp_av1_test_{index}.mkv"

    for temp_f in [temp_proxy, temp_av1_test]:
        if os.path.exists(temp_f):
            try:
                os.remove(temp_f)
            except OSError:
                pass

    cprint(f"  -> Rendering {proxy_width}x{proxy_height} proxy via {hardware_type}...", "darkgray")
    proxy_cmd = [
        "ffmpeg", "-hide_banner", "-y", "-i", f, *fps_args,
        "-vf", f"{deint_filter}scale={proxy_width}:{proxy_height}:flags=lanczos,format=yuv420p",
        "-c:v", proxy_encoder, *proxy_enc_args,
        "-an", temp_proxy, "-loglevel", "error"
    ]
    res_proxy = subprocess.run(proxy_cmd)
    if res_proxy.returncode != 0:
        cprint(f"Error: Proxy creation failed on {f}", "red")
        sys.exit(1)

    cprint("  -> Running SVT-AV1 complexity benchmark (CRF 32, Preset 11)...", "darkgray")
    test_cmd = [
        "ffmpeg", "-hide_banner", "-y", "-i", temp_proxy,
        "-c:v", "libsvtav1", "-crf", "32", "-preset", "11",
        "-an", temp_av1_test, "-loglevel", "error"
    ]
    res_test = subprocess.run(test_cmd)
    if res_test.returncode != 0:
        cprint(f"Error: AV1 benchmark failed on {f}", "red")
        sys.exit(1)

    scan_bytes = os.path.getsize(temp_av1_test)
    total_av1_complexity_bytes += scan_bytes

    for temp_f in [temp_proxy, temp_av1_test]:
        if os.path.exists(temp_f):
            try:
                os.remove(temp_f)
            except OSError:
                pass

    episodes.append({
        "file": f,
        "duration": dur,
        "scan_bytes": scan_bytes
    })

# ==========================================================
# Phase 3: Proportional Bitrate Allocation Table
# ==========================================================
cprint("\n==========================================================", "cyan")
cprint("=== Phase 3: Proportional Bitrate Allocation Table     ===", "cyan")
cprint("==========================================================", "cyan")

total_season_duration = sum(ep["duration"] for ep in episodes)
total_audio_mb = (audio_bitrate_k * 1000 / 8 / 1048576) * total_season_duration
available_video_mb = target_disc_mb - total_audio_mb

if available_video_mb <= 0:
    cprint("Error: Audio allocation exceeds target size! Lower audio bitrate or raise target capacity.", "red")
    sys.exit(1)

for ep in episodes:
    ep_share_ratio = 1.0 if len(episodes) == 1 else (ep["scan_bytes"] / total_av1_complexity_bytes)
    allocated_mb = available_video_mb * ep_share_ratio
    video_kbps = math.floor((allocated_mb * 8192) / ep["duration"])
    if video_kbps < 100:
        video_kbps = 100

    ep["video_kbps"] = video_kbps
    ep["allocated_mb"] = round(allocated_mb, 1)

    cprint(f"{ep['file']:<50} | {video_kbps:>5} kbps | ~{round(allocated_mb, 1):>6} MB", "green")

projected_total = sum(ep["allocated_mb"] for ep in episodes) + total_audio_mb
cprint(f"\nTotal Allocated Media: ~{projected_total:,.1f} MB / Target: {target_disc_mb} MB", "cyan")

# --- 10-Second Auto-Proceed Countdown ---
cprint("\nReview the calculated bitrates above.", "yellow")
cprint("Auto-proceeding with final 2-pass CPU encodes in 10 seconds...", "cyan")
cprint("Press [N] to abort, or press any other key / Enter to proceed immediately.\n", "darkgray")

timeout_seconds = 10
proceed = True

# Platform-agnostic keyboard detection
try:
    import msvcrt

    for sec in range(timeout_seconds, 0, -1):
        sys.stdout.write(f"\rStarting encodes in {sec:2d}s... (Press 'N' to abort) ")
        sys.stdout.flush()
        loop_start = time.time()
        while time.time() - loop_start < 1.0:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key in [b"n", b"N"]:
                    proceed = False
                    break
                else:
                    sec = 0
                    break
            time.sleep(0.05)
        if not proceed or sec == 0:
            break
    sys.stdout.write("\r" + " " * 65 + "\r")
    sys.stdout.flush()
except ImportError:
    import select

    for sec in range(timeout_seconds, 0, -1):
        sys.stdout.write(f"\rStarting encodes in {sec:2d}s... (Press 'N' to abort) ")
        sys.stdout.flush()
        rlist, _, _ = select.select([sys.stdin], [], [], 1.0)
        if rlist:
            user_input = sys.stdin.readline().strip()
            if user_input.lower() == "n":
                proceed = False
            break
    sys.stdout.write("\r" + " " * 65 + "\r")
    sys.stdout.flush()

if not proceed:
    cprint("\nEncoding aborted by user. Exiting.", "yellow")
    sys.exit(0)

# ==========================================================
# Phase 4: Final 2-Pass Encodes (SVT-AV1)
# ==========================================================
cprint("\n==========================================================", "cyan")
cprint(f"=== Phase 4: Final 2-Pass Encodes ({final_width}x{final_height} SVT-AV1) ===", "cyan")
cprint("==========================================================", "cyan")

grain_params = f"film-grain={film_grain}:film-grain-denoise=1:tune=0" if film_grain > 0 else "tune=0"

for current, ep in enumerate(episodes, 1):
    # Enforce .mkv container
    base_name = Path(ep["file"]).stem
    out_name = f"{base_name}.mkv"
    out_path = os.path.join(output_dir, out_name)
    ep["out_path"] = out_path
    ep["out_name"] = out_name

    cprint(f"\n[{current}/{len(episodes)}] Final Render: {out_name} at {ep['video_kbps']} kbps...", "cyan")

    for f_log in glob.glob("ffmpeg2pass-0.log*"):
        try:
            os.remove(f_log)
        except OSError:
            pass

    # Pass 1: SVT-AV1 analysis
    pass1_cmd = [
        "ffmpeg", "-hide_banner", "-y", "-i", ep["file"], *fps_args,
        "-map", "0:v:0",
        "-vf", f"{deint_filter}scale={final_width}:{final_height}:flags=lanczos,format=yuv420p10le",
        "-c:v", "libsvtav1",
        "-b:v", f"{ep['video_kbps']}k",
        "-preset", str(av1_preset),
        "-g", "240",
        "-svtav1-params", grain_params,
        "-pass", "1",
        "-an",
        "-f", "null", os.devnull
    ]
    res_pass1 = subprocess.run(pass1_cmd)
    if res_pass1.returncode != 0:
        cprint(f"Error: Pass 1 analysis failed on {ep['file']}", "red")
        sys.exit(1)

    # Pass 2: Final video + Opus audio + Subtitles + Metadata
    pass2_cmd = [
        "ffmpeg", "-hide_banner", "-y", "-i", ep["file"], *fps_args,
        "-map", "0:v:0",
        "-map", "0:a:0?",
        *sub_args,
        "-map_chapters", "0",
        "-vf", f"{deint_filter}scale={final_width}:{final_height}:flags=lanczos,format=yuv420p10le",
        "-c:v", "libsvtav1",
        "-b:v", f"{ep['video_kbps']}k",
        "-preset", str(av1_preset),
        "-g", "240",
        "-svtav1-params", grain_params,
        "-pass", "2",
        "-c:a", "libopus",
        "-b:a", f"{audio_bitrate_k}k",
        "-ac", str(audio_channels),
        out_path
    ]
    res_pass2 = subprocess.run(pass2_cmd)
    if res_pass2.returncode != 0:
        cprint(f"Error: Pass 2 render failed on {ep['file']}", "red")
        sys.exit(1)

    for f_log in glob.glob("ffmpeg2pass-0.log*"):
        try:
            os.remove(f_log)
        except OSError:
            pass

cprint("\nAll encodes finished. Analyzing bitstreams for visual reports...", "cyan")

# ==========================================================
# Phase 5: Bitstream Inspection & Reporting Engine
# ==========================================================
num_buckets = 50
report_lines = []
svg_cards = []


def add_report_line(line=""):
    print(line)
    report_lines.append(line)


add_report_line("==========================================================")
add_report_line("        UASE FINAL ENCODE & BITRATE BUDGET REPORT         ")
add_report_line("==========================================================")
add_report_line(f"Target Budget     : {target_disc_mb} MB")
add_report_line(f"Profile Resolution: {final_width}x{final_height}")
add_report_line(f"Framerate Mode    : {fps_desc}")
add_report_line(f"Scan / Deint Mode : {'BWDIF Deinterlacing Enabled' if deint_choice == '1' else 'Progressive (Passthrough)'}")
add_report_line(f"SVT-AV1 Preset    : {av1_preset}")
add_report_line(f"Film Grain Engine : {f'Strength {film_grain} (film-grain-denoise=1)' if film_grain > 0 else '0 (Disabled)'}")
add_report_line(f"Audio Profile     : Opus | {audio_channels} ch | {audio_bitrate_k} kbps")
add_report_line(f"Subtitle Policy   : {'Copy All Losslessly' if sub_choice == '1' else 'Strip All (-sn)'}")
add_report_line(f"Proxy Engine Used : {hardware_type}")
add_report_line("==========================================================")
add_report_line("")

total_actual_bytes = 0

for card_index, ep in enumerate(episodes):
    out_item_path = ep["out_path"]
    out_item_name = ep["out_name"]
    actual_bytes = os.path.getsize(out_item_path)
    total_actual_bytes += actual_bytes
    actual_mb = round(actual_bytes / 1048576, 2)
    percent_of_disc = round((actual_bytes / (target_disc_mb * 1048576)) * 100, 2)

    # Harvest packet data via ffprobe
    probe_cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "packet=pts_time,size", "-of", "csv=p=0", out_item_path
    ]
    try:
        probe_output = subprocess.check_output(probe_cmd, text=True)
    except Exception:
        probe_output = ""

    bucket_duration = ep["duration"] / num_buckets
    bucket_bytes = [0.0] * num_buckets

    for line in probe_output.splitlines():
        parts = line.strip().split(",")
        if len(parts) >= 2:
            try:
                t = float(parts[0])
                s = float(parts[1])
                b_idx = int(math.floor(t / bucket_duration))
                if b_idx >= num_buckets:
                    b_idx = num_buckets - 1
                if b_idx >= 0:
                    bucket_bytes[b_idx] += s
            except ValueError:
                continue

    bucket_kbps = [round((b * 8) / (bucket_duration * 1000), 1) for b in bucket_bytes]
    max_kbps = max(bucket_kbps) if bucket_kbps else 1.0
    min_kbps = min(bucket_kbps) if bucket_kbps else 0.0
    avg_kbps = round(sum(bucket_kbps) / len(bucket_kbps), 1) if bucket_kbps else 0.0
    if max_kbps <= 0:
        max_kbps = 1.0

    add_report_line(f"FILE: {out_item_name}")
    add_report_line("-" * 62)

    # 10-line text histogram (% of Max Bitrate)
    histogram_labels = {
        10: "100% |",
        8: " 80% |",
        6: " 60% |",
        4: " 40% |",
        2: " 20% |",
    }
    for row in range(10, 0, -1):
        threshold = row / 10.0
        label = histogram_labels.get(row, "     |")
        chars = []
        for col in range(num_buckets):
            ratio = bucket_kbps[col] / max_kbps
            chars.append("█" if ratio >= (threshold - 0.05) else " ")
        add_report_line(label + "".join(chars))

    add_report_line("     +" + ("-" * num_buckets))

    hrs = int(ep["duration"] // 3600)
    mins = int((ep["duration"] % 3600) // 60)
    secs = int(ep["duration"] % 60)
    dur_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
    spacer = " " * max(0, num_buckets - 16)
    add_report_line(f"      00:00:00{spacer}{dur_str}")

    add_report_line("Statistics:")
    add_report_line(f"  Peak Bitrate : {max_kbps:>6.1f} kbps  |  Min Bitrate : {min_kbps:>6.1f} kbps  |  Avg Bitrate : {avg_kbps:>6.1f} kbps")
    add_report_line(f"  Encoded Size : {actual_mb:>6.2f} MB    |  Disc Share  : {percent_of_disc:>5.2f} % of target capacity")
    add_report_line("")

    # Build SVG card
    card_top = 80 + (card_index * 240)
    points_list = []
    area_list = [f"70,{card_top + 140}"]

    for b in range(num_buckets):
        x = round(70 + b * (700.0 / (num_buckets - 1)), 1)
        y = round((card_top + 140) - (bucket_kbps[b] / max_kbps) * 110.0, 1)
        points_list.append(f"{x},{y}")
        area_list.append(f"{x},{y}")

    area_list.append(f"770,{card_top + 140}")
    pts_str = " ".join(points_list)
    area_str = " ".join(area_list)

    escaped_title = xml_escape(out_item_name)
    svg_cards.append(f"""  <g class="card">
    <rect x="30" y="{card_top}" width="760" height="215" rx="8" class="card-bg" />
    <text x="50" y="{card_top + 25}" class="card-title">{escaped_title}</text>
    <text x="770" y="{card_top + 25}" class="card-meta" text-anchor="end">{dur_str} | {actual_mb} MB ({percent_of_disc}% of target)</text>
    
    <!-- Chart Grid -->
    <line x1="70" y1="{card_top + 30}" x2="770" y2="{card_top + 30}" class="grid-line" />
    <line x1="70" y1="{card_top + 85}" x2="770" y2="{card_top + 85}" class="grid-line" />
    <line x1="70" y1="{card_top + 140}" x2="770" y2="{card_top + 140}" class="axis-line" />
    
    <text x="65" y="{card_top + 34}" class="axis-text" text-anchor="end">{max_kbps}k</text>
    <text x="65" y="{card_top + 89}" class="axis-text" text-anchor="end">{round(max_kbps / 2)}k</text>
    <text x="65" y="{card_top + 144}" class="axis-text" text-anchor="end">0k</text>

    <!-- Waveform Area & Line -->
    <polygon points="{area_str}" class="chart-area" />
    <polyline points="{pts_str}" class="chart-line" />

    <!-- Stats Footer -->
    <text x="70" y="{card_top + 175}" class="stats-text">Min: {min_kbps} kbps</text>
    <text x="270" y="{card_top + 175}" class="stats-text">Avg: {avg_kbps} kbps</text>
    <text x="470" y="{card_top + 175}" class="stats-text">Peak: {max_kbps} kbps</text>
    <text x="670" y="{card_top + 175}" class="stats-text">Opus: {audio_bitrate_k} kbps</text>
  </g>""")

# Grand Total Summary Calculation
total_actual_mb = round(total_actual_bytes / 1048576, 2)
total_percent_used = round((total_actual_bytes / (target_disc_mb * 1048576)) * 100, 2)
free_margin_mb = round(target_disc_mb - total_actual_mb, 2)

add_report_line("==========================================================")
add_report_line("                  SEASON CAPACITY SUMMARY                 ")
add_report_line("==========================================================")
add_report_line(f"Total Disc Space Budgeted : {target_disc_mb:>8} MB")
add_report_line(f"Actual Encoded Size Used  : {total_actual_mb:>8.2f} MB  ({total_percent_used}% of capacity)")
add_report_line(f"Remaining Safety Headroom : {free_margin_mb:>8.2f} MB")
add_report_line("==========================================================")

# Save reports to disk if requested
if save_report_files:
    txt_report_path = os.path.join(output_dir, "uase_encode_report.txt")
    svg_report_path = os.path.join(output_dir, "uase_bitrate_report.svg")

    # Write text report
    with open(txt_report_path, "w", encoding="utf-8") as f_txt:
        f_txt.write("\n".join(report_lines) + "\n")

    # Write vector SVG report
    svg_total_height = 120 + (len(episodes) * 240)
    all_cards_svg = "\n".join(svg_cards)
    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 {svg_total_height}" width="100%" height="100%">
  <style>
    .bg {{ fill: #11111b; }}
    .card-bg {{ fill: #181825; stroke: #313244; stroke-width: 1; }}
    .header-title {{ fill: #89b4fa; font-family: -apple-system, Segoe UI, Roboto, Helvetica, sans-serif; font-size: 20px; font-weight: bold; }}
    .header-sub {{ fill: #a6adc8; font-family: -apple-system, Segoe UI, Roboto, Helvetica, sans-serif; font-size: 13px; }}
    .card-title {{ fill: #cdd6f4; font-family: -apple-system, Segoe UI, Roboto, Helvetica, sans-serif; font-size: 14px; font-weight: 600; }}
    .card-meta {{ fill: #9399b2; font-family: -apple-system, Segoe UI, Roboto, Helvetica, sans-serif; font-size: 12px; }}
    .grid-line {{ stroke: #313244; stroke-width: 1; stroke-dasharray: 4,4; }}
    .axis-line {{ stroke: #45475a; stroke-width: 1; }}
    .axis-text {{ fill: #6c7086; font-family: monospace; font-size: 10px; }}
    .chart-area {{ fill: rgba(137, 180, 250, 0.15); }}
    .chart-line {{ fill: none; stroke: #89b4fa; stroke-width: 2; stroke-linejoin: round; }}
    .stats-text {{ fill: #bac2de; font-family: monospace; font-size: 11px; }}
  </style>
  <rect width="100%" height="100%" class="bg" />
  <text x="30" y="38" class="header-title">UASE Bitrate &amp; Capacity Report</text>
  <text x="30" y="58" class="header-sub">Budget: {target_disc_mb} MB | Encoded: {total_actual_mb} MB ({total_percent_used}% utilized, {free_margin_mb} MB margin remaining)</text>
{all_cards_svg}
</svg>"""

    with open(svg_report_path, "w", encoding="utf-8") as f_svg:
        f_svg.write(svg_content)

    cprint("\nReports saved successfully:", "green")
    cprint(f"  -> Text Report : {txt_report_path}", "darkgray")
    cprint(f"  -> Vector SVG  : {svg_report_path}", "darkgray")

cprint("\nDone.", "green")