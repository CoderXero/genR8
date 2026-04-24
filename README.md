# genR8

Safe image and video generation CLI for the xAI Grok API.

## Requirements

- Python 3.10 or newer.
- `ffmpeg` on `PATH` for uploaded video reference frames and multi-chunk video stitching.
- An xAI API key.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` and set `XAI_API_KEY`. Keep `.env` local; it is ignored by git.

Optional `.env` settings:

```bash
GENR8_HOST=127.0.0.1
GENR8_PORT=8000
GENR8_OUTPUT_DIR=output
GENR8_THEME=charcoal
MAX_VIDEO_LENGTH=60
```

`MAX_VIDEO_LENGTH` is capped at 60 seconds even if a larger value is configured.

## Usage

Text to image:

```bash
genr8 --format image --prompt "A clean product photo of a ceramic mug" --aspect-ratio 1:1
```

Image edit:

```bash
genr8 --format image --image ./source.png --prompt "Render this as a pencil sketch"
```

Text to video:

```bash
genr8 --format video --prompt "A flower opening in morning light" --duration 8 --resolution 720p
```

Video generation supports up to `MAX_VIDEO_LENGTH`, capped at 60 seconds. Videos longer than 5 seconds are generated in 5-second chunks, each next chunk starts from the previous chunk's final frame, and the saved chunks are stitched into a single MP4 in `GENR8_OUTPUT_DIR`.

Image to video:

```bash
genr8 --format video --image ./still.png --prompt "Slow cinematic camera push-in" --duration 8
```

Video edit:

```bash
genr8 --format video --video-url "https://example.com/input.mp4" --prompt "Make the lighting warmer"
```

Generated xAI URLs are temporary. Add `--download ./outputs` to save the returned media locally.

Video output is always saved locally. If `--download` is omitted, video files are written to `GENR8_OUTPUT_DIR`.

## Web UI

Start the local Python web UI:

```bash
genr8-web
```

Then open http://127.0.0.1:8000.

The web UI reads `.env`, shows a processing indicator while generation is running, saves completed media into `output/`, and renders a Download button for the saved file. Available themes are Charcoal, Dracula, and Cream, and the selector appears above the prompt.

The web UI uses file upload controls for images and videos. Image uploads are sent as generation references. Video uploads are saved locally, their last frame is extracted with `ffmpeg`, and that frame is used as the starting reference for generated video chunks. For xAI video edit, use the public `.mp4` URL field because the provider requires a reachable URL.

You can also use:

```bash
./run.sh
```

`run.sh` creates or reuses `.venv`, installs the project in editable mode, creates `.env` from `.env.example` when needed, sources `.env`, and starts `genr8-web`.

## Safety

This project does not pass explicit sexual generation modes to the API. Requests containing NSFW, spicy, or erotic wording are rewritten into a fully clothed sensual editorial style; nudity, pornographic, sexual, or fetish prompts are rejected locally before calling the xAI SDK.
