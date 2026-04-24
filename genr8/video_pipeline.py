from __future__ import annotations

import subprocess
import time
import uuid
from dataclasses import replace
from pathlib import Path

from .client import (
    GenerationRequest,
    GenerationResult,
    GenR8Error,
    GrokGenerator,
    download_result,
    validate_request,
)


CHUNK_SECONDS = 5
MAX_ALLOWED_VIDEO_LENGTH = 60


def generate_video_sequence(
    generator: GrokGenerator,
    request: GenerationRequest,
    output_dir: Path,
    max_video_length: int,
) -> GenerationResult:
    if request.output_format != "video":
        raise GenR8Error("Video sequence generation requires video output.")
    if request.video_url:
        result = generator.generate(request)[0]
        return download_result(result, output_dir)

    duration = request.duration or CHUNK_SECONDS
    if max_video_length > MAX_ALLOWED_VIDEO_LENGTH:
        raise GenR8Error("MAX_VIDEO_LENGTH cannot exceed 60 seconds.")
    if duration > max_video_length:
        raise GenR8Error(f"Video length cannot exceed {max_video_length} seconds.")
    if duration < 1:
        raise GenR8Error("Duration must be at least 1 second.")

    output_dir.mkdir(parents=True, exist_ok=True)
    if duration <= CHUNK_SECONDS:
        result = generator.generate(request)[0]
        return download_result(result, output_dir)

    chunk_paths: list[Path] = []
    source_urls: list[str] = []
    current_inputs = request.image_inputs
    remaining = duration
    sequence_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    chunk_index = 1

    while remaining > 0:
        chunk_duration = min(CHUNK_SECONDS, remaining)
        chunk_request = replace(
            request,
            duration=chunk_duration,
            image_inputs=current_inputs,
            video_url=None,
        )
        validate_request(chunk_request)

        chunk_result = generator.generate(chunk_request)[0]
        if chunk_result.url:
            source_urls.append(chunk_result.url)
        saved = download_result(chunk_result, output_dir)
        if not saved.local_path:
            raise GenR8Error("Chunk download did not produce a local file.")
        chunk_paths.append(saved.local_path)

        remaining -= chunk_duration
        if remaining > 0:
            frame_path = output_dir / f"genr8-{sequence_id}-frame-{chunk_index:02d}.jpg"
            extract_last_frame(saved.local_path, frame_path)
            current_inputs = (str(frame_path),)
        chunk_index += 1

    stitched_path = output_dir / f"genr8-{sequence_id}-stitched.mp4"
    stitch_videos(chunk_paths, stitched_path)
    return GenerationResult(
        url=";".join(source_urls) if source_urls else None,
        duration=duration,
        local_path=stitched_path,
    )


def extract_last_frame(video_path: Path, frame_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-sseof",
        "-0.1",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(frame_path),
    ]
    _run_ffmpeg(command, "extract the final frame")


def stitch_videos(video_paths: list[Path], output_path: Path) -> None:
    if not video_paths:
        raise GenR8Error("No video chunks were generated.")

    concat_file = output_path.with_suffix(".concat.txt")
    concat_file.write_text(
        "".join(f"file '{path.resolve()}'\n" for path in video_paths),
        encoding="utf-8",
    )
    try:
        command = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output_path),
        ]
        try:
            _run_ffmpeg(command, "stitch video chunks")
        except GenR8Error:
            transcode_command = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
            _run_ffmpeg(transcode_command, "stitch video chunks")
    finally:
        concat_file.unlink(missing_ok=True)


def _run_ffmpeg(command: list[str], action: str) -> None:
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise GenR8Error("ffmpeg is required for multi-chunk video generation.") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip()
        raise GenR8Error(f"Could not {action}: {detail}") from exc
    if completed.returncode != 0:
        raise GenR8Error(f"Could not {action}.")
