# Minimal Resolve-internal script (run from Resolve Scripts menu).
# Reads config.json, imports audio at timeline start, places images contiguously on timeline.
# Uses timeline start timecode offset so it works when timeline start != 00:00:00:00 (e.g. 01:00:00:00).

import json
import random
from pathlib import Path

# ----------------------------
# EDIT: path to config.json (absolute)


# Uncomment to make it work
# ----------------------------
#CONFIG_PATH = r"....../config.json"


# ----------------------------
# Helper: seconds -> frames
# ----------------------------
def seconds_to_frames(seconds, fps):
    return int(round(seconds * fps))

# ----------------------------
# Helper: convert timecode "HH:MM:SS:FF" to frames
# ----------------------------
def tc_to_frames(tc, fps):
    # expect format "HH:MM:SS:FF" (FF = frames)
    try:
        parts = [int(x) for x in tc.split(':')]
        if len(parts) != 4:
            return 0
        hh, mm, ss, ff = parts
        total_seconds = hh * 3600 + mm * 60 + ss
        return int(total_seconds * fps) + int(ff)
    except Exception:
        return 0

# ----------------------------
# Start (Resolve provides global 'app' when run from GUI)
# ----------------------------
resolve = app.GetResolve()                  # provided by Resolve when running inside GUI
pm = resolve.GetProjectManager()
project = pm.GetCurrentProject()
if project is None:
    raise SystemExit("Open a project in Resolve before running this script.")

media_pool = project.GetMediaPool()

# ensure a timeline exists; create one if none
timeline = project.GetCurrentTimeline()
if timeline is None:
    import datetime
    now = datetime.datetime.now()
    auto_name = f"AutoTimeline_{now.strftime('%Y%m%d_%H%M%S')}"
    media_pool.CreateEmptyTimeline(auto_name)
    timeline = project.GetCurrentTimeline()
    if timeline is None:
        raise SystemExit("Failed to create or get the new timeline.")

# Get timeline fps (project setting)
fps = 30.0
try:
    fps = float(project.GetSetting("timelineFrameRate"))
except Exception:
    try:
        fps = float(timeline.GetSetting("timelineFrameRate"))
    except Exception:
        fps = 30.0

# ----------------------------
# Compute timeline start offset in frames (so recordFrame is adjusted)
# ----------------------------
timeline_start_frame = 0
try:
    start_tc = timeline.GetStartTimecode()  # returns something like "01:00:00:00"
    timeline_start_frame = tc_to_frames(start_tc, fps)
except Exception:
    # if API not available, fall back to 0
    timeline_start_frame = 0

# ----------------------------
# Load config
# ----------------------------
cfg_path = Path(CONFIG_PATH)
if not cfg_path.exists():
    raise SystemExit(f"Config not found: {cfg_path}")

with cfg_path.open("r", encoding="utf-8") as f:
    cfg = json.load(f)

segments_path = Path(cfg["segments"])
audio_path = Path(cfg.get("audio")) if cfg.get("audio") else None
images_root = Path(cfg["images_root"])
track_index = int(cfg.get("track", 2))
seed = cfg.get("seed", None)

if seed is not None:
    random.seed(int(seed))

# Validate inputs
if not segments_path.exists():
    raise SystemExit(f"Segments JSON not found: {segments_path}")
if not images_root.exists():
    raise SystemExit(f"Images root not found: {images_root}")
if audio_path and not audio_path.exists():
    raise SystemExit(f"Audio file not found: {audio_path}")

# ----------------------------
# Read segments and validate no-overlap (we still validate segments themselves don't overlap)
# ----------------------------
with segments_path.open("r", encoding="utf-8") as f:
    segments = json.load(f)

segments_sorted = sorted(segments, key=lambda s: float(s["start"]))

for i in range(len(segments_sorted) - 1):
    cur_end = float(segments_sorted[i]["end"])
    nxt_start = float(segments_sorted[i + 1]["start"])
    if nxt_start < cur_end:
        raise SystemExit(f"Overlap detected between segment {segments_sorted[i].get('id')} and {segments_sorted[i+1].get('id')}. Aborting.")

# ----------------------------
# Import audio at timeline start (if provided) — compute explicit audio duration in frames
# ----------------------------
audio_duration_frames = None
if audio_path:
    imported = media_pool.ImportMedia([str(audio_path)])
    if not imported:
        raise SystemExit(f"Failed to import audio: {audio_path}")
    audio_item = imported[0]

    # Try to read the imported media's duration from Resolve via clip properties
    try:
        clip_props = audio_item.GetClipProperty()
        # clip_props often contains keys like 'Duration' or 'SourceDuration' formatted "HH:MM:SS:FF"
        dur_tc = clip_props.get('Duration') or clip_props.get('SourceDuration') or clip_props.get('sourceDuration') or clip_props.get('duration')
        if dur_tc:
            # If duration is numeric frames, handle; else treat as TC string
            if isinstance(dur_tc, (int, float)):
                audio_duration_frames = int(dur_tc)
            else:
                audio_duration_frames = tc_to_frames(str(dur_tc), fps)
    except Exception:
        audio_duration_frames = None

    # Fallback: use the last segment end (so audio covers all segments)
    if audio_duration_frames is None:
        if segments_sorted:
            last_end_s = float(segments_sorted[-1]["end"])
            audio_duration_frames = seconds_to_frames(last_end_s, fps)
        else:
            audio_duration_frames = seconds_to_frames(30.0, fps)  # default 30s

    audio_clip = {
        "mediaPoolItem": audio_item,
        "startFrame": 0,
        "endFrame": audio_duration_frames,
        "recordFrame": timeline_start_frame,  # place audio at visible timeline start
        "trackIndex": 1
    }
    media_pool.AppendToTimeline([audio_clip])

# ----------------------------
# Prepare clipInfos for all segments (images) — contiguous placement (no gaps)
# ----------------------------
clip_infos = []
import_cache = {}

# start contiguous placement from timeline_start_frame
last_record_end = timeline_start_frame

for seg in segments_sorted:
    start_s = float(seg["start"])
    end_s = float(seg["end"])
    emotion = seg["emotion"]

    if end_s <= start_s:
        continue

    emo_folder = images_root / emotion
    if not emo_folder.exists():
        raise SystemExit(f"Missing emotion folder: {emo_folder}")

    imgs = [p for p in emo_folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".tiff")]
    if not imgs:
        raise SystemExit(f"No images in folder: {emo_folder}")

    chosen = str(random.choice(imgs))

    if chosen in import_cache:
        media_item = import_cache[chosen]
    else:
        imported = media_pool.ImportMedia([chosen])
        if not imported:
            raise SystemExit(f"Failed to import image: {chosen}")
        media_item = imported[0]
        import_cache[chosen] = media_item

    duration_frames = max(1, seconds_to_frames(end_s - start_s, fps))

    # place immediately after the previous clip to avoid gaps
    record_frame = last_record_end

    clip_info = {
        "mediaPoolItem": media_item,
        "startFrame": 0,
        "endFrame": duration_frames,
        "recordFrame": record_frame,
        "trackIndex": track_index
    }
    clip_infos.append(clip_info)

    # advance last_record_end so next clip starts right after this one
    last_record_end = record_frame + duration_frames

# ----------------------------
# Place all clips on timeline
# ----------------------------
# Place all clips on timeline
if clip_infos:
    result_items = media_pool.AppendToTimeline(clip_infos)

    # result_items is expected to be a list of TimelineItem objects in the same order.
    # Some Resolve versions return None or an object; guard carefully.
    if result_items:
        try:
            # Attempt to set each placed item's start/end to requested frames
            for idx, item in enumerate(result_items):
                planned = clip_infos[idx]
                planned_start = planned.get('recordFrame', 0)
                planned_end = planned_start + int(planned.get('endFrame', 1))
                # Use SetStart / SetEnd if available
                if hasattr(item, 'SetStart') and hasattr(item, 'SetEnd'):
                    item.SetStart(planned_start)
                    item.SetEnd(planned_end)
                else:
                    # fallback: try SetStartFrame / SetEndFrame names
                    if hasattr(item, 'SetStartFrame') and hasattr(item, 'SetEndFrame'):
                        item.SetStartFrame(planned_start)
                        item.SetEndFrame(planned_end)
            # after adjusting, refresh UI to start
            try:
                resolve.OpenPage("edit")
                resolve.SetCurrentTimecode(timeline.GetStartTimecode())
            except Exception:
                pass
        except Exception as e:
            print("Warning: could not set item start/end frames:", e)
    else:
        print("Warning: AppendToTimeline returned no items or unsupported type; timeline may not reflect requested durations.")

print("Placement finished. Check timeline in Resolve.")
