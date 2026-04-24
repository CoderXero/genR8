# genR8 System Spec

Build a Python CLI and Python 3 web UI for safe image and video generation using the xAI Grok SDK.

## Inputs

The request accepts:

- Text prompt, required.
- Output format: `image` or `video`.
- Zero or more image inputs as local paths, public URLs, data URIs, or web UI file uploads.
- Optional web UI video file upload, used as a starting reference by extracting its final frame.
- Optional public `.mp4` video URL for video editing.
- Optional generation parameters:
  - `duration` in seconds for video generation.
  - `aspect_ratio` for image generation/editing and supported video generation modes.
  - `resolution` for supported image/video generation modes.
  - `n` for text-to-image variations.
- Runtime configuration from `.env`:
  - `XAI_API_KEY`
  - `GENR8_HOST`
  - `GENR8_PORT`
  - `GENR8_OUTPUT_DIR`
  - `GENR8_THEME`
  - `MAX_VIDEO_LENGTH`, capped at 60 seconds.

## Outputs

The response prints xAI-hosted temporary media URLs. The CLI can also download the returned media URL into a local output directory.

The web UI renders the returned image or video URL in the browser after generation completes.

Generated web UI media is downloaded from the temporary xAI URL, saved to the configured output directory, and served back through the local app with a Download button.

Video generation longer than 5 seconds must be generated in 5-second chunks until the requested duration is reached, without exceeding `MAX_VIDEO_LENGTH` or 60 seconds. After each chunk, extract the final frame and use it as the image input for the next chunk. Save all chunks to the configured output directory, then stitch them into one MP4.

## xAI API Integration

Use the xAI SDK:

- Image generation/editing: `client.image.sample()` and `client.image.sample_batch()`.
- Video generation/editing: `client.video.generate()`.

Use `XAI_API_KEY` from the environment.

The runtime must load `.env` before reading environment configuration. `.env.example` documents supported parameters, while `.env` remains untracked.

## Interfaces

- CLI entry point: `genr8`.
- Web UI entry point: `genr8-web`.
- Local web server: `http://127.0.0.1:8000`.
- Launcher script: `./run.sh`, which prepares the virtualenv, loads `.env`, and starts the web UI.
- Web UI themes: Charcoal, Dracula, and Cream.
- Web UI processing state: show a blocking "Processing" indicator after submit until the server returns a completed result or error.
- Web UI media inputs must use file upload controls for image and video files. Uploaded image files become API image references. Uploaded video files are saved locally and converted to a final-frame image reference for video generation; true xAI video editing still requires a public `.mp4` URL.

## Dependencies

- Python 3.10 or newer.
- xAI SDK for generation requests.
- `requests` for downloading temporary provider URLs.
- `ffmpeg` for final-frame extraction and stitching generated video chunks.

## Mode Selection

For image output:

- No image input: text-to-image.
- One image input: image edit.
- Two to five image inputs: multi-image edit.
- `n` is supported only for text-to-image generation.

For video output:

- No image or video input: text-to-video.
- One image input: image-to-video.
- Two to seven image inputs: reference-to-video.
- One video URL: video edit.
- Video edit cannot combine with duration, aspect ratio, or resolution because those are inherited from the input video.

## Safety

The project must not pass explicit sexual generation workflows to the xAI API. It may rewrite NSFW, spicy, or erotic wording into a fully clothed sensual editorial request. It must reject nudity, pornographic, sexual, or fetish prompts locally before calling the xAI API and still rely on xAI API moderation for provider-side enforcement.
