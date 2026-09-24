# Custom voice guide

How to give the assistant your own voice (e.g. an actor/character), fully offline and with
**no GPU at runtime** and **no API calls**.

## The idea

```
your PC's TTS (any voice)  ->  raw speech  ->  voice conversion  ->  your target voice
```

You train a small **voice-conversion model** once (that's the GPU-heavy part - do it on free
Google Colab), download it, and from then on it converts every reply locally on your CPU.

## Your three targets

| # | Voice | Source audio to collect | Notes |
|---|-------|------------------------|-------|
| 1 | Scarlett Johansson | Interviews, audiobook, clean movie dialogue (English) | Start here |
| 2 | Wan Peng (Chinese actress) | Interviews / drama dialogue (Chinese) | Timbre converts fine even if she then speaks English |
| 3 | Anya Forger (anime) | Isolated dialogue (no background music) | High/cute pitch - needs the cleanest sample |

## Step 0 - collect audio (per voice)

- **10-30 minutes** of **single-speaker** speech is the sweet spot. 5 minutes can work; 1 hour is overkill.
- **Clean**: no background music, no other speakers, no heavy effects. Remove laugh tracks / BGM.
- Format: any normal audio (mp3/wav/m4a). 44.1 kHz is plenty.
- Tools you already have: **FFmpeg** (you have it), **Audacity**, **CapCut** (installed) - use them to cut out music/other voices.
- Put each voice's clips in its own folder, e.g. `dataset_scarlett/`, `dataset_wanpeng/`.

## Step 1 - train on Google Colab (free GPU)

Use **Applio** (the actively maintained RVC distribution) - it has a ready Colab notebook.

1. Open Google Colab (colab.research.google.com) with a Google account.
2. Find the **Applio** Colab notebook (`Applio` / "Applio RVC" - search their GitHub README for the
   "Open in Colab" badge). The original **Retrieval-based-Voice-Conversion-WebUI** also has a Colab
   notebook if you prefer that.
3. In Colab: **Runtime -> Change runtime type -> T4 GPU**.
4. Run the notebook's install cell (it downloads RVC + models on the Colab machine).
5. Zip your dataset folder and upload it (or mount Google Drive - easier for big files).
6. In the training UI inside the notebook:
   - **Preprocess**: slice into 3-10 second chunks, resample.
   - **Extract features + pitch** (pitch algorithm: **RMVPE** - best quality).
   - **Train**: ~**200-300 epochs** (roughly 30-60 min on a free T4).
7. **Export / get the model files**:
   - `<name>.pth`  - the voice model
   - `<name>.index` - the feature index (optional but improves quality)
8. Download those two files.

## Step 2 - install the voice locally

Put the files here (create the folder):

```
%LOCALAPPDATA%\RealAssistant\voices\scarlett\scarlett.pth
%LOCALAPPDATA%\RealAssistant\voices\scarlett\scarlett.index
```

Then set it in `settings.json`:

```json
{ "custom_voice": "scarlett" }
```

Restart the assistant. `list your custom voices` will show what's installed (the assistant
has this built in via `voice_convert.py`).

## Step 3 - the local conversion runtime (once)

Conversion needs a small local RVC runtime on the CPU:

```powershell
python -m pip install rvc-python
```

(That pulls a CPU build of PyTorch - a few hundred MB. It's a one-time cost.)

`voice_convert.py` already looks for it: if the model **and** the runtime are present, replies
are converted; if either is missing it just plays the normal voice, so nothing breaks.

## Effort / time

| Task | Time |
|---|---|
| Collect + clean audio (per voice) | 30-90 min |
| Colab training (per voice) | 30-60 min (mostly waiting) |
| Download + install locally | 5 min |
| Local CPU conversion per reply | ~0.5-2 s extra |

## If you don't want to train

Community RVC models for many famous voices already exist on model-sharing sites. Downloading
one skips Steps 0-1 - quality varies, so check samples before trusting it.

## Copy-paste brief for an AI helper (chat.ai / GLM / Claude)

> I want to train an RVC v2 voice-conversion model on Google Colab's free T4 GPU using the
> **Applio** Colab notebook. My dataset is a folder of clean single-speaker audio of one target
> voice (10-30 min total) as `.wav`/`.mp3` files. Give me the exact click-by-click steps in the
> notebook: how to upload/mount my dataset, which settings to use for preprocess (slice length,
> sample rate), feature + pitch extraction (RMVPE), training (batch size, epochs for a T4), and
> how to export the `.pth` and `.index` files and download them. Also give me an ffmpeg command
> to strip background music / trim silence before uploading. Keep it beginner-friendly.

## Please keep it personal

Cloning a real person's voice for your **own, offline, personal** assistant is one thing.
**Sharing** that model, or using it to **impersonate** someone publicly or commercially, is where
it stops being okay - and for a public figure like an actor it can be legally exposed. Keep the
models on your own machine and to yourself.
