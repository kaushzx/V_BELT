
## What to expect : Sample Video

Video link: https://youtu.be/4hsVJ74wtOA 


We wanted to **automate repetitive video editing in DaVinci Resolve**, specifically:

- **We should already have:**
    - Audio (voiceover)

- **We would create:**
    - A JSON file containing:
        - `start` / `end` timestamps (in seconds)
        - `emotion` labels (28 emotions)
- **You also have:**
    - One folder per emotion, each containing multiple images

### Goal

> Automatically place images on the Resolve timeline so that:
> 
> - Each image **starts exactly at the JSON timestamp**
> - Images are chosen **randomly from the emotion folder**
> - Images are **perfectly in sync with audio**
> - No gaps, no overlaps ( exists while I was working )
> - Everything lands **directly on the timeline** (no export)

This is a **base-timeline generator** for your workflow.

---

## Processing the audio (in Colab)

Colab link:

https://colab.research.google.com/drive/1xLJ5aa0FtXzEInIGQmBXG-MO_JAtLPgq?usp=sharing

We use Whisper in ASR-only (automatic speech recognition) mode (no translation) to extract reliable segment timestamps and Hindi text. Timestamps must come strictly from audio, and Whisper’s internal translation can distort timing.

Workflow summary:

1. Load Whisper JSON into a DataFrame containing `(id, start, end, text_hindi)`.
2. To avoid Colab dependency and torchvision/pipeline breakage, translate **text only** (not audio) using a text-to-text translation model that works cleanly in your environment (the same `transformers.pipeline('translation')` setup you validated with Tamil → English). Append the result as `text_eng` while keeping the original timestamps unchanged.
    - Reference video: https://www.youtube.com/watch?v=AGgzRE3TlvU
3. Run emotion classification on the English text only, attach the predicted emotion to the same rows, and export a new JSON where each original Hindi timestamp has a stable English meaning and an emotion label.

In short: timestamps from Hindi ASR, meaning from external text translation, emotion from English NLP — strictly separated so nothing corrupts alignment or breaks the environment. Everything flows cleanly through a DataFrame.

Result: clean emotions with timestamps.

---

## JSON → timeline example

```json
{
"segments":"C:/Users/........../sample_em.json",
"audio":"C:/Users/.........../sample.wav",
"images_root":"C:/Users/.........../V_BELT_BASE/Emotions",
"track":4,
"seed":42
}

```

- `segments` → Manually place the `sample_em.json` file in the `V_BELT_BASE` folder.
- `audio` → The original audio `sample.wav` used to produce `sample_em.json`.
- `images_root` → Directory containing all emotion image folders (inside `V_BELT_BASE`).
- `track` → Timeline track layer to place images on.
- `seed` → Random seed for deterministic random selection.

---

## Using scripts with DaVinci Resolve (free vs Studio)

- It's recommended to read the `DR_readme` file and learn how to create a symbolic link in Windows for your script.
- You cannot run external scripts from outside Resolve with the free version. Running external scripts requires DaVinci Resolve **Studio**.
- To use the free version, run the script from inside Resolve: **Fusion > Workspace > Scripts > Folder**.

Some tutorial resources for Python scripting in Resolve (basics):

- https://www.youtube.com/watch?v=Lnn2ehP77zg
- https://www.youtube.com/watch?v=5lyzNKqzYlY

---

## Standard libraries used

This script uses only standard-library modules:

- `json`
- `random`
- `pathlib`
- `datetime` (conditionally)
- `sys` (indirectly via Resolve runtime)

These are part of the Python standard library — no `pip install` needed.

---

## More about DaVinci Resolve scripting

You can give the Davinci Resolve README to an LLM and ask it which functions to use for specific tasks. Also study the Resolve documentation for your DR version — my copy is for **18.6**.
Python: **Python 3.11.9**

---

## Script actions

1. Opens current project
2. Creates timeline if missing
3. Reads timeline FPS + start timecode
4. Pre-imports all emotion images
5. Reads JSON segments
6. For each segment:
    - Picks a random image from the emotion folder
    - Places it at the exact JSON timestamp
    - Cuts overlaps if needed
7. Places audio to match visuals
8. Opens the Edit page at timeline start

---

## Not visible on timeline (important)

**Timeline time ≠ 00:00:00:00**

- Resolve timelines often start at **01:00:00:00**.
- Your JSON timestamps are relative to **audio start**.

Solution:

- Read timeline start timecode.
- Convert it to a **frame offset**.
- Place clips at:

```
timeline_start_frame +seconds_to_frames(json.start)

```

This was a major blocker early on fro me, as clips were visible on Edit Index of DR but nothing was visible on the timeline.

---

## Final note

It's not perfect, but it works.
