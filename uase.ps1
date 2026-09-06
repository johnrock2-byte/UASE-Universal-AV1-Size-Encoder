<#
.SYNOPSIS
    UASE — Universal AV1 Size Encoder (v1.1)
    Hardware-Accelerated Proxy Entropy Scanning (NVENC -> AMF -> QSV -> CPU)
    Proportional Multi-File & Single Video Capacity Budgeting (SVT-AV1 / Opus)
    Post-Encode Terminal Visualizer, Text Report, and Vector SVG Generator
#>

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# --- Helper Prompt Function ---
function Ask-Option {
    param(
        [string]$Prompt,
        [string]$Default,
        [string[]]$ValidChoices = @()
    )
    while ($true) {
        Write-Host -NoNewline "$Prompt [Default: $Default]: " -ForegroundColor Yellow
        $inputVal = Read-Host
        if ([string]::IsNullOrWhiteSpace($inputVal)) {
            return $Default
        }
        if ($ValidChoices.Count -gt 0) {
            if ($ValidChoices -contains $inputVal) {
                return $inputVal
            } else {
                Write-Host "Invalid selection. Valid options: $($ValidChoices -join ', ')" -ForegroundColor Red
            }
        } else {
            return $inputVal
        }
    }
}

# --- Hardware Acceleration Probe ---
function Test-HardwareEncoder {
    param(
        [string]$EncoderName,
        [string[]]$EncoderArgs
    )
    try {
        & ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc=duration=1:size=320x240:rate=24 -frames:v 1 -vf "format=yuv420p" -c:v $EncoderName @EncoderArgs -f null NUL 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

Clear-Host
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "      UASE: UNIVERSAL AV1 SIZE ENCODER (v1.1)             " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 0. Hardware Acceleration Detection
Write-Host "Probing available acceleration engines for proxy scanning..." -ForegroundColor DarkGray
if (Test-HardwareEncoder -EncoderName "h264_nvenc" -EncoderArgs @("-preset", "p1", "-qp", "16")) {
    $HardwareType = "NVIDIA NVENC (Hardware Accelerated)"
    $ProxyEncoder = "h264_nvenc"
    $ProxyEncArgs = @("-preset", "p1", "-qp", "16")
}
elseif (Test-HardwareEncoder -EncoderName "h264_amf" -EncoderArgs @("-quality", "speed", "-qp_i", "16", "-qp_p", "16")) {
    $HardwareType = "AMD AMF (Hardware Accelerated)"
    $ProxyEncoder = "h264_amf"
    $ProxyEncArgs = @("-quality", "speed", "-qp_i", "16", "-qp_p", "16")
}
elseif (Test-HardwareEncoder -EncoderName "h264_qsv" -EncoderArgs @("-preset", "veryfast", "-global_quality", "16")) {
    $HardwareType = "Intel Quick Sync Video (Hardware Accelerated)"
    $ProxyEncoder = "h264_qsv"
    $ProxyEncArgs = @("-preset", "veryfast", "-global_quality", "16")
}
else {
    $HardwareType = "CPU Software Fallback (libx264 ultrafast)"
    $ProxyEncoder = "libx264"
    $ProxyEncArgs = @("-preset", "ultrafast", "-crf", "16")
}
Write-Host "Proxy Engine Selected: $HardwareType`n" -ForegroundColor Green

# 1. Target Capacity & Media Profile Selection
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "        TARGET CAPACITY & MEDIA PROFILE SELECTION         " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "[!] WARNING: Smaller margins maximize picture quality but reduce headroom." -ForegroundColor Yellow
Write-Host "    Minor 2-pass rate-control variance (+/- 1%) or container muxing overhead could" -ForegroundColor Yellow
Write-Host "    cause 'Max Fill' to slightly overflow physical disc boundaries." -ForegroundColor Yellow
Write-Host "    Always verify final folder size prior to burning.`n" -ForegroundColor Yellow

Write-Host "DVD Single Layer (DVD+R baseline: 4,700 MB):" -ForegroundColor Gray
Write-Host "  1) Safe Fill       (~517 MB margin  |  Target: 4,183 MB)"
Write-Host "  2) Balanced Fill   (~156 MB margin  |  Target: 4,544 MB)  <-- [DEFAULT]"
Write-Host "  3) Max Fill        (~81 MB margin   |  Target: 4,619 MB)"
Write-Host "`nDVD Dual Layer (DVD+R DL baseline: 8,548 MB):" -ForegroundColor Gray
Write-Host "  4) Safe Fill       (~948 MB margin  |  Target: 7,600 MB)"
Write-Host "  5) Balanced Fill   (~298 MB margin  |  Target: 8,250 MB)"
Write-Host "  6) Max Fill        (~148 MB margin  |  Target: 8,400 MB)"
Write-Host "`nBD-R Single Layer (25 GB baseline: 25,025 MB):" -ForegroundColor Gray
Write-Host "  7) Safe Fill       (~2,525 MB margin | Target: 22,500 MB)"
Write-Host "  8) Balanced Fill   (~925 MB margin  |  Target: 24,100 MB)"
Write-Host "  9) Max Fill        (~425 MB margin  |  Target: 24,600 MB)"
Write-Host "`nCD-R (700 MB baseline):" -ForegroundColor Gray
Write-Host "  0) Balanced Fill   (~25 MB margin   |  Target: 675 MB)"
Write-Host "`nManual Entry:" -ForegroundColor Gray
Write-Host "  Type any raw target value in MB directly (e.g., 4300, 15000, etc.)`n"

$rawChoice = Ask-Option -Prompt "Select media preset (0-9) or enter custom MB target" -Default "2"

$TargetDiscMB = switch ($rawChoice) {
    "0" { 675 }
    "1" { 4183 }
    "2" { 4544 }
    "3" { 4619 }
    "4" { 7600 }
    "5" { 8250 }
    "6" { 8400 }
    "7" { 22500 }
    "8" { 24100 }
    "9" { 24600 }
    Default {
        if ($rawChoice -match '^\d+$') {
            [int]$rawChoice
        } else {
            Write-Host "Unrecognized selection. Defaulting to DVD Single Layer Balanced Fill (4,544 MB)." -ForegroundColor Yellow
            4544
        }
    }
}
Write-Host "Target Allocation Budget Set: $TargetDiscMB MB`n" -ForegroundColor DarkCyan

# 2. Output Resolution & Aspect Ratio Selection
Write-Host "Target Output Resolution:" -ForegroundColor Gray
Write-Host "  1) 854x480   (480p 16:9 DVD Single Layer Standard - Default)"
Write-Host "  2) 640x480   (480p 4:3 Vintage / Broadcast)"
Write-Host "  3) 1280x720  (720p HD)"
Write-Host "  4) 1920x1080 (1080p Full HD)"
Write-Host "  5) 3840x2160 (4K UHD)"
Write-Host "  Or enter any custom resolution as WIDTHxHEIGHT (e.g., 1920x800, 960x540)"

while ($true) {
    $resChoice = Ask-Option -Prompt "Select preset (1-5) or enter WIDTHxHEIGHT" -Default "1"
    if ($resChoice -eq "1") { $FinalWidth = 854;  $FinalHeight = 480;  break }
    elseif ($resChoice -eq "2") { $FinalWidth = 640;  $FinalHeight = 480;  break }
    elseif ($resChoice -eq "3") { $FinalWidth = 1280; $FinalHeight = 720;  break }
    elseif ($resChoice -eq "4") { $FinalWidth = 1920; $FinalHeight = 1080; break }
    elseif ($resChoice -eq "5") { $FinalWidth = 3840; $FinalHeight = 2160; break }
    elseif ($resChoice -match '^(\d+)x(\d+)$') {
        $FinalWidth  = [int]$matches[1]
        $FinalHeight = [int]$matches[2]
        if ($FinalWidth % 2 -ne 0)  { $FinalWidth++ }
        if ($FinalHeight % 2 -ne 0) { $FinalHeight++ }
        break
    } else {
        Write-Host "Invalid format. Enter 1-5 or a valid WIDTHxHEIGHT format like 1920x1080." -ForegroundColor Red
    }
}

if ($FinalHeight -le 320) {
    $ProxyWidth  = $FinalWidth
    $ProxyHeight = $FinalHeight
} else {
    $ProxyHeight = 320
    $ProxyWidth  = [math]::Round((($FinalWidth / $FinalHeight) * 320) / 2) * 2
}
Write-Host "Output Geometry: ${FinalWidth}x${FinalHeight} | Proxy Benchmark: ${ProxyWidth}x${ProxyHeight}" -ForegroundColor DarkCyan

# 3. Framerate Configuration
Write-Host "`nFramerate Options:" -ForegroundColor Gray
Write-Host "  0) Match Source (Automatic passthrough - recommended)"
Write-Host "  1) 23.976 fps (Standard Film/Cinema)"
Write-Host "  2) 24.0 fps (True 24p)"
Write-Host "  3) 25.0 fps (PAL Broadcast)"
Write-Host "  4) 29.97 fps (NTSC Broadcast)"
Write-Host "  5) 59.94 fps (High Frame Rate NTSC)"
$fpsChoice = Ask-Option -Prompt "Select Framerate (0-5)" -Default "0" -ValidChoices @("0", "1", "2", "3", "4", "5")

$fpsArgs = switch ($fpsChoice) {
    "1" { @("-r", "24000/1001") }
    "2" { @("-r", "24") }
    "3" { @("-r", "25") }
    "4" { @("-r", "30000/1001") }
    "5" { @("-r", "60000/1001") }
    Default { @() }
}

# 4. Deinterlacing
Write-Host "`nScan Type / Deinterlacing:" -ForegroundColor Gray
Write-Host "  0) Progressive (No filter - standard for modern rips/web)"
Write-Host "  1) Interlaced / Telecined (Apply BWDIF deinterlacer for DVD/broadcast captures)"
$deintChoice = Ask-Option -Prompt "Deinterlacing needed? (0 or 1)" -Default "0" -ValidChoices @("0", "1")
$deintFilter = if ($deintChoice -eq "1") { "bwdif=mode=0," } else { "" }

# 5. Film Grain Synthesis
Write-Host "`nSynthetic Film Grain Strength (AV1 Film Grain Engine):" -ForegroundColor Gray
Write-Host "  10 = Heavy / Gritty (Super 16mm, high ISO cinema, gritty sci-fi)"
Write-Host "  4 to 6 = Light / Natural (Standard 35mm film stock, modern drama)"
Write-Host "  0 = None / Clean (Clean digital sensors, 2D animation, anime)"
$rawGrain = Ask-Option -Prompt "Enter film grain strength (0-50)" -Default "5"
$FilmGrain = [int]$rawGrain

# 6. Audio Configuration
Write-Host "`nAudio Layout:" -ForegroundColor Gray
Write-Host "  1) Mono (1 channel)"
Write-Host "  2) Stereo (2 channels - recommended for low bitrate efficiency)"
Write-Host "  6) 5.1 Surround (6 channels)"
Write-Host "  8) 7.1 Surround (8 channels)"
$audioChanChoice = Ask-Option -Prompt "Select Audio Channels (1, 2, 6, 8)" -Default "2" -ValidChoices @("1", "2", "6", "8")
$AudioChannels = [int]$audioChanChoice

$defaultAudioBitrate = switch ($AudioChannels) {
    1 { "48" }
    2 { "64" }
    6 { "128" }
    8 { "192" }
}
$rawAudioBitrate = Ask-Option -Prompt "Opus audio bitrate in kbps (6-512)" -Default $defaultAudioBitrate
$AudioBitrateK = [int]$rawAudioBitrate

# 7. Subtitle Handling
Write-Host "`nSubtitle Handling:" -ForegroundColor Gray
Write-Host "  1) Copy all subtitle tracks losslessly (SRT, ASS, PGS, VobSub)"
Write-Host "  0) Strip all subtitles"
$subChoice = Ask-Option -Prompt "Preserve subtitles? (0 or 1)" -Default "1" -ValidChoices @("0", "1")
$subArgs = if ($subChoice -eq "1") { @("-map", "0:s?", "-c:s", "copy") } else { @("-sn") }

# 8. SVT-AV1 Speed Preset
Write-Host "`nSVT-AV1 Speed Preset:" -ForegroundColor Gray
Write-Host "  4 = Maximum Compression Efficiency (Highest quality, slowest)"
Write-Host "  5 = Balanced Quality & Encoding Throughput (~30% faster than 4)"
Write-Host "  6 = Fast Turnaround (Reduced CPU time)"
$presetChoice = Ask-Option -Prompt "Select AV1 Preset (4, 5, 6)" -Default "4" -ValidChoices @("4", "5", "6")
$AV1Preset = [int]$presetChoice

# 9. Post-Encode Summary Report Saving
Write-Host "`nPost-Encode Report Files:" -ForegroundColor Gray
Write-Host "  (Terminal bitrate graphs are always shown on screen upon completion)"
Write-Host "  1) Yes - Write summary text file and vector SVG graph to output folder"
Write-Host "  0) No  - Display in console only (Do not save files)"
$saveReportChoice = Ask-Option -Prompt "Save summary report and SVG to disk? (0 or 1)" -Default "0" -ValidChoices @("0", "1")
$SaveReportFiles = ($saveReportChoice -eq "1")

$OutputDir = "encoded"
if (-not (Test-Path -Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$files = Get-ChildItem -File | Where-Object { $_.Extension -match '^\.(mkv|mp4|avi)$' } | 
         Sort-Object { [regex]::Replace($_.Name, '\d+', { $args[0].Value.PadLeft(8, '0') }) }

if ($files.Count -eq 0) {
    Write-Host "`nError: No video files (.mkv, .mp4, .avi) found in current directory." -ForegroundColor Red
    exit 1
}

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "=== Phase 1 & 2: Intermediate + AV1 Complexity Benchmark ===" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$episodes = @()
$totalAV1ComplexityBytes = [int64]0
$index = 1

foreach ($f in $files) {
    Write-Host ("`n[{0}/{1}] Analyzing: {2}" -f $index, $files.Count, $f.Name) -ForegroundColor Yellow

    $durStr = & ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $f.FullName
    $dur = [double]::Parse($durStr, [System.Globalization.CultureInfo]::InvariantCulture)

    $tempProxy = "temp_proxy_$index.mkv"
    $tempAV1Test = "temp_av1_test_$index.mkv"
    Remove-Item -Path $tempProxy, $tempAV1Test -Force -ErrorAction SilentlyContinue

    Write-Host "  -> Rendering ${ProxyWidth}x${ProxyHeight} proxy via $HardwareType..." -ForegroundColor DarkGray
    & ffmpeg -hide_banner -y -i $f.FullName @fpsArgs `
        -vf "${deintFilter}scale=${ProxyWidth}:${ProxyHeight}:flags=lanczos,format=yuv420p" `
        -c:v $ProxyEncoder @ProxyEncArgs `
        -an "$tempProxy" -loglevel error

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Proxy creation failed on $($f.Name)" -ForegroundColor Red
        exit 1
    }

    Write-Host "  -> Running SVT-AV1 complexity benchmark (CRF 32, Preset 11)..." -ForegroundColor DarkGray
    & ffmpeg -hide_banner -y -i $tempProxy `
        -c:v libsvtav1 -crf 32 -preset 11 `
        -an "$tempAV1Test" -loglevel error

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: AV1 benchmark failed on $($f.Name)" -ForegroundColor Red
        exit 1
    }

    $scanBytes = (Get-Item $tempAV1Test).Length
    $totalAV1ComplexityBytes += $scanBytes

    Remove-Item -Path $tempProxy, $tempAV1Test -Force -ErrorAction SilentlyContinue

    $episodes += [PSCustomObject]@{
        File      = $f
        Duration  = $dur
        ScanBytes = $scanBytes
    }
    $index++
}

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "=== Phase 3: Proportional Bitrate Allocation Table     ===" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$totalSeasonDuration = ($episodes | Measure-Object -Property Duration -Sum).Sum
$totalAudioMB = ($AudioBitrateK * 1000 / 8 / 1048576) * $totalSeasonDuration
$availableVideoMB = $TargetDiscMB - $totalAudioMB

if ($availableVideoMB -le 0) {
    Write-Host "Error: Audio allocation exceeds target size! Lower audio bitrate or raise target capacity." -ForegroundColor Red
    exit 1
}

foreach ($ep in $episodes) {
    $epShareRatio = if ($episodes.Count -eq 1) { 1.0 } else { $ep.ScanBytes / $totalAV1ComplexityBytes }
    $allocatedMB  = $availableVideoMB * $epShareRatio
    $videoKbps    = [math]::Floor(($allocatedMB * 8192) / $ep.Duration)
    if ($videoKbps -lt 100) { $videoKbps = 100 }
    
    $ep | Add-Member -NotePropertyName VideoKbps -NotePropertyValue $videoKbps
    $ep | Add-Member -NotePropertyName AllocatedMB -NotePropertyValue ([math]::Round($allocatedMB, 1))

    Write-Host ("{0,-50} | {1,5} kbps | ~{2,6} MB" -f $ep.File.Name, $videoKbps, [math]::Round($allocatedMB, 1)) -ForegroundColor Green
}

$projectedTotal = ($episodes | Measure-Object -Property AllocatedMB -Sum).Sum + $totalAudioMB
Write-Host ("`nTotal Allocated Media: ~{0:N1} MB / Target: {1} MB" -f $projectedTotal, $TargetDiscMB) -ForegroundColor Cyan

Write-Host "`nReview the calculated bitrates above." -ForegroundColor Yellow
$proceed = Ask-Option -Prompt "Proceed with final 2-pass CPU encodes? (Y/N)" -Default "Y" -ValidChoices @("Y", "N", "y", "n")
if ($proceed -match "^[Nn]$") {
    Write-Host "Encoding aborted by user. Exiting." -ForegroundColor Yellow
    exit 0
}

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "=== Phase 4: Final 2-Pass Encodes (${FinalWidth}x${FinalHeight} SVT-AV1) ===" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$grainParams = if ($FilmGrain -gt 0) { "film-grain=${FilmGrain}:film-grain-denoise=1:tune=0" } else { "tune=0" }
$current = 1

foreach ($ep in $episodes) {
    $outPath = Join-Path $OutputDir $ep.File.Name
    $ep | Add-Member -NotePropertyName OutPath -NotePropertyValue $outPath -Force
    Write-Host ("`n[{0}/{1}] Final Render: {2} at {3} kbps..." -f $current, $episodes.Count, $ep.File.Name, $ep.VideoKbps) -ForegroundColor Cyan

    Remove-Item -Path "ffmpeg2pass-0.log*" -Force -ErrorAction SilentlyContinue

    # Pass 1: SVT-AV1 rate-control analysis
    & ffmpeg -hide_banner -y -i $ep.File.FullName @fpsArgs `
        -map 0:v:0 `
        -vf "${deintFilter}scale=${FinalWidth}:${FinalHeight}:flags=lanczos,format=yuv420p10le" `
        -c:v libsvtav1 `
        -b:v "$($ep.VideoKbps)k" `
        -preset $AV1Preset `
        -g 240 `
        -svtav1-params "$grainParams" `
        -pass 1 `
        -an `
        -f null NUL

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Pass 1 analysis failed on $($ep.File.Name)" -ForegroundColor Red
        exit 1
    }

    # Pass 2: Final AV1 video + Opus audio + Subtitle copy + Chapter metadata
    & ffmpeg -hide_banner -y -i $ep.File.FullName @fpsArgs `
        -map 0:v:0 `
        -map 0:a:0? `
        @subArgs `
        -map_chapters 0 `
        -vf "${deintFilter}scale=${FinalWidth}:${FinalHeight}:flags=lanczos,format=yuv420p10le" `
        -c:v libsvtav1 `
        -b:v "$($ep.VideoKbps)k" `
        -preset $AV1Preset `
        -g 240 `
        -svtav1-params "$grainParams" `
        -pass 2 `
        -c:a libopus `
        -b:a "${AudioBitrateK}k" `
        -ac $AudioChannels `
        "$outPath"

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Pass 2 render failed on $($ep.File.Name)" -ForegroundColor Red
        exit 1
    }

    Remove-Item -Path "ffmpeg2pass-0.log*" -Force -ErrorAction SilentlyContinue
    $current++
}

Write-Host "`nAll encodes finished. Analyzing bitstreams for visual reports..." -ForegroundColor Cyan

# ==========================================================
# === Phase 5: Bitstream Inspection & Reporting Engine   ===
# ==========================================================

$numBuckets = 50
$reportLines = [System.Collections.Generic.List[string]]::new()
$svgCards = [System.Collections.Generic.List[string]]::new()

function Add-ReportLine ([string]$line = "") {
    Write-Host $line
    $reportLines.Add($line)
}

Add-ReportLine "=========================================================="
Add-ReportLine "        UASE FINAL ENCODE & BITRATE BUDGET REPORT         "
Add-ReportLine "=========================================================="
Add-ReportLine ("Target Budget: {0} MB | Profile Resolution: {1}x{2}" -f $TargetDiscMB, $FinalWidth, $FinalHeight)
Add-ReportLine ""

$totalActualBytes = [int64]0
$cardIndex = 0

foreach ($ep in $episodes) {
    $outItem = Get-Item $ep.OutPath
    $actualBytes = $outItem.Length
    $totalActualBytes += $actualBytes
    $actualMB = [math]::Round($actualBytes / 1048576, 2)
    $percentOfDisc = [math]::Round(($actualBytes / ($TargetDiscMB * 1048576)) * 100, 2)

    # Harvest packet data via ffprobe
    $probeOutput = & ffprobe -v error -select_streams v:0 -show_entries packet=pts_time,size -of csv=p=0 $ep.OutPath
    
    $bucketDuration = $ep.Duration / $numBuckets
    $bucketBytes = New-Object "double[]" $numBuckets

    foreach ($line in $probeOutput) {
        $parts = $line.Split(',')
        if ($parts.Count -ge 2) {
            $t = 0.0
            $s = 0.0
            if ([double]::TryParse($parts[0], [System.Globalization.NumberStyles]::Any, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$t) -and
                [double]::TryParse($parts[1], [System.Globalization.NumberStyles]::Any, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$s)) {
                $bIdx = [int][math]::Floor($t / $bucketDuration)
                if ($bIdx -ge $numBuckets) { $bIdx = $numBuckets - 1 }
                if ($bIdx -ge 0) { $bucketBytes[$bIdx] += $s }
            }
        }
    }

    $bucketKbps = New-Object "double[]" $numBuckets
    for ($i = 0; $i -lt $numBuckets; $i++) {
        $bucketKbps[$i] = [math]::Round(($bucketBytes[$i] * 8) / ($bucketDuration * 1000), 1)
    }

    $maxKbps = ($bucketKbps | Measure-Object -Maximum).Maximum
    $minKbps = ($bucketKbps | Measure-Object -Minimum).Minimum
    $avgKbps = [math]::Round(($bucketKbps | Measure-Object -Average).Average, 1)
    if ($maxKbps -le 0) { $maxKbps = 1 }

    Add-ReportLine ("FILE: {0}" -f $ep.File.Name)
    Add-ReportLine ("-" * 62)

    # 10-line text histogram (% of Max Bitrate)
    for ($row = 10; $row -ge 1; $row--) {
        $threshold = $row / 10.0
        $label = switch ($row) {
            10 { "100% |" }
            8  { " 80% |" }
            6  { " 60% |" }
            4  { " 40% |" }
            2  { " 20% |" }
            Default { "     |" }
        }
        $chars = New-Object "char[]" $numBuckets
        for ($col = 0; $col -lt $numBuckets; $col++) {
            $ratio = $bucketKbps[$col] / $maxKbps
            $chars[$col] = if ($ratio -ge ($threshold - 0.05)) { [char]0x2588 } else { ' ' }
        }
        Add-ReportLine ($label + (New-Object string ($chars, 0, $numBuckets)))
    }
    Add-ReportLine ("     +" + ("-" * $numBuckets))
    
    $durSpan = [TimeSpan]::FromSeconds($ep.Duration)
    $durStr = "{0:D2}:{1:D2}:{2:D2}" -f $durSpan.Hours, $durSpan.Minutes, $durSpan.Seconds
    $timeAxis = "      00:00:00" + (" " * [math]::Max(0, ($numBuckets - 16))) + $durStr
    Add-ReportLine $timeAxis
    
    Add-ReportLine ("Statistics:")
    Add-ReportLine ("  Peak Bitrate : {0,6} kbps  |  Min Bitrate : {1,6} kbps  |  Avg Bitrate : {2,6} kbps" -f $maxKbps, $minKbps, $avgKbps)
    Add-ReportLine ("  Encoded Size : {0,6} MB    |  Disc Share  : {1,5} % of target capacity" -f $actualMB, $percentOfDisc)
    Add-ReportLine ""

    # Build SVG card for file
    $cardTop = 80 + ($cardIndex * 240)
    $pointsList = New-Object System.Collections.Generic.List[string]
    $areaList = New-Object System.Collections.Generic.List[string]
    
    $areaList.Add("70,$($cardTop + 140)")
    for ($b = 0; $b -lt $numBuckets; $b++) {
        $x = 70 + [math]::Round($b * (700.0 / ($numBuckets - 1)), 1)
        $y = ($cardTop + 140) - [math]::Round(($bucketKbps[$b] / $maxKbps) * 110.0, 1)
        $pointsList.Add("$x,$y")
        $areaList.Add("$x,$y")
    }
    $areaList.Add("770,$($cardTop + 140)")

    $ptsStr = $pointsList -join " "
    $areaStr = $areaList -join " "

    $svgCards.Add(@"
  <g class="card">
    <rect x="30" y="$cardTop" width="760" height="215" rx="8" class="card-bg" />
    <text x="50" y="$($cardTop + 25)" class="card-title">$($ep.File.Name)</text>
    <text x="770" y="$($cardTop + 25)" class="card-meta" text-anchor="end">${durStr} | ${actualMB} MB (${percentOfDisc}% of target)</text>
    
    <!-- Chart Grid -->
    <line x1="70" y1="$($cardTop + 30)" x2="770" y2="$($cardTop + 30)" class="grid-line" />
    <line x1="70" y1="$($cardTop + 85)" x2="770" y2="$($cardTop + 85)" class="grid-line" />
    <line x1="70" y1="$($cardTop + 140)" x2="770" y2="$($cardTop + 140)" class="axis-line" />
    
    <text x="65" y="$($cardTop + 34)" class="axis-text" text-anchor="end">${maxKbps}k</text>
    <text x="65" y="$($cardTop + 89)" class="axis-text" text-anchor="end">$([math]::Round($maxKbps/2))k</text>
    <text x="65" y="$($cardTop + 144)" class="axis-text" text-anchor="end">0k</text>

    <!-- Waveform Area & Line -->
    <polygon points="$areaStr" class="chart-area" />
    <polyline points="$ptsStr" class="chart-line" />

    <!-- Stats Footer -->
    <text x="70" y="$($cardTop + 175)" class="stats-text">Min: ${minKbps} kbps</text>
    <text x="270" y="$($cardTop + 175)" class="stats-text">Avg: ${avgKbps} kbps</text>
    <text x="470" y="$($cardTop + 175)" class="stats-text">Peak: ${maxKbps} kbps</text>
    <text x="670" y="$($cardTop + 175)" class="stats-text">Opus: ${AudioBitrateK} kbps</text>
  </g>
"@)
    $cardIndex++
}

# Grand Total Summary Calculation
$totalActualMB = [math]::Round($totalActualBytes / 1048576, 2)
$totalPercentUsed = [math]::Round(($totalActualBytes / ($TargetDiscMB * 1048576)) * 100, 2)
$freeMarginMB = [math]::Round($TargetDiscMB - $totalActualMB, 2)

Add-ReportLine "=========================================================="
Add-ReportLine "                 SEASON CAPACITY SUMMARY                  "
Add-ReportLine "=========================================================="
Add-ReportLine ("Total Disc Space Budgeted : {0,8} MB" -f $TargetDiscMB)
Add-ReportLine ("Actual Encoded Size Used  : {0,8} MB  ({1}% of capacity)" -f $totalActualMB, $totalPercentUsed)
Add-ReportLine ("Remaining Safety Headroom : {0,8} MB" -f $freeMarginMB)
Add-ReportLine "=========================================================="

# Save reports to disk if requested
if ($SaveReportFiles) {
    $txtReportPath = Join-Path $OutputDir "uase_encode_report.txt"
    $svgReportPath = Join-Path $OutputDir "uase_bitrate_report.svg"

    # Write text report
    $reportLines | Out-File -FilePath $txtReportPath -Encoding utf8

    # Write vector SVG report
    $svgTotalHeight = 120 + ($cardIndex * 240)
    $allCardsSvg = $svgCards -join "`n"
    $svgContent = @"
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 $svgTotalHeight" width="100%" height="100%">
  <style>
    .bg { fill: #11111b; }
    .card-bg { fill: #181825; stroke: #313244; stroke-width: 1; }
    .header-title { fill: #89b4fa; font-family: -apple-system, Segoe UI, Roboto, Helvetica, sans-serif; font-size: 20px; font-weight: bold; }
    .header-sub { fill: #a6adc8; font-family: -apple-system, Segoe UI, Roboto, Helvetica, sans-serif; font-size: 13px; }
    .card-title { fill: #cdd6f4; font-family: -apple-system, Segoe UI, Roboto, Helvetica, sans-serif; font-size: 14px; font-weight: 600; }
    .card-meta { fill: #9399b2; font-family: -apple-system, Segoe UI, Roboto, Helvetica, sans-serif; font-size: 12px; }
    .grid-line { stroke: #313244; stroke-width: 1; stroke-dasharray: 4,4; }
    .axis-line { stroke: #45475a; stroke-width: 1; }
    .axis-text { fill: #6c7086; font-family: monospace; font-size: 10px; }
    .chart-area { fill: rgba(137, 180, 250, 0.15); }
    .chart-line { fill: none; stroke: #89b4fa; stroke-width: 2; stroke-linejoin: round; }
    .stats-text { fill: #bac2de; font-family: monospace; font-size: 11px; }
  </style>
  <rect width="100%" height="100%" class="bg" />
  <text x="30" y="38" class="header-title">UASE Bitrate &amp; Capacity Report</text>
  <text x="30" y="58" class="header-sub">Budget: ${TargetDiscMB} MB | Encoded: ${totalActualMB} MB (${totalPercentUsed}% utilized, ${freeMarginMB} MB margin remaining)</text>
  $allCardsSvg
</svg>
"@
    $svgContent | Out-File -FilePath $svgReportPath -Encoding utf8
    Write-Host "`nReports saved successfully:" -ForegroundColor Green
    Write-Host "  -> Text Report : $txtReportPath" -ForegroundColor DarkGray
    Write-Host "  -> Vector SVG  : $svgReportPath" -ForegroundColor DarkGray
}

Write-Host "`nDone." -ForegroundColor Green
