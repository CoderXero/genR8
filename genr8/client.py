from __future__ import annotations

import base64
import mimetypes
import os
import re
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import requests

from .config import load_dotenv


OutputFormat = Literal["image", "video"]

IMAGE_MODEL = "grok-imagine-image"
VIDEO_MODEL = "grok-imagine-video"

EXPLICIT_CONTENT_PATTERNS = (
    r"\bporn(?:ographic|ography)?\b",
    r"\bsex(?:ual|ually)?\b",
    r"\bnude|nudity|naked\b",
    r"\bfetish\b",
)

SENSUAL_REWRITE_PATTERNS = (
    r"\bnsfw\b",
    r"\bspicy\b",
    r"\berotic\b",
)


class GenR8Error(ValueError):
    """Raised when a generation request is invalid before hitting the API."""


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    output_format: OutputFormat
    image_inputs: tuple[str, ...] = ()
    video_url: str | None = None
    duration: int | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    n: int = 1


@dataclass(frozen=True)
class GenerationResult:
    url: str | None
    model: str | None = None
    duration: int | None = None
    respect_moderation: bool | None = None
    local_path: Path | None = None


def assert_safe_prompt(prompt: str) -> None:
    pattern = re.compile("|".join(EXPLICIT_CONTENT_PATTERNS), re.IGNORECASE)
    if pattern.search(prompt):
        raise GenR8Error(
            "Explicit sexual or NSFW generation prompts are not supported by this tool."
        )


def rewrite_sensual_prompt(prompt: str) -> str:
    rewritten = prompt.strip()
    pattern = re.compile("|".join(SENSUAL_REWRITE_PATTERNS), re.IGNORECASE)
    if pattern.search(rewritten):
        rewritten = pattern.sub("sensual editorial", rewritten)
        rewritten += (
            " The subject remains fully clothed in a tasteful, non-explicit editorial style."
        )
    return rewritten


def replace_request_prompt(request: GenerationRequest) -> GenerationRequest:
    rewritten = rewrite_sensual_prompt(request.prompt)
    if rewritten == request.prompt:
        return request
    return replace(request, prompt=rewritten)


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https", "data"} and bool(parsed.scheme)


def media_to_image_url(value: str) -> str:
    if is_url(value):
        return value

    path = Path(value).expanduser()
    if not path.exists():
        raise GenR8Error(f"Image input does not exist: {path}")
    if not path.is_file():
        raise GenR8Error(f"Image input is not a file: {path}")

    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type or not mime_type.startswith("image/"):
        raise GenR8Error(f"Image input has unsupported type: {path}")

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def validate_request(request: GenerationRequest) -> None:
    if not request.prompt.strip():
        raise GenR8Error("A non-empty prompt is required.")
    assert_safe_prompt(rewrite_sensual_prompt(request.prompt))

    if request.output_format == "image":
        if request.video_url:
            raise GenR8Error("Image output does not support video input.")
        if len(request.image_inputs) > 5:
            raise GenR8Error("Image editing supports at most 5 input images.")
        if request.n < 1 or request.n > 10:
            raise GenR8Error("Image variation count must be between 1 and 10.")
        return

    if request.output_format == "video":
        if request.n != 1:
            raise GenR8Error("Video generation only supports one output per request.")
        if request.video_url and request.image_inputs:
            raise GenR8Error("Video editing cannot be combined with image inputs.")
        if request.video_url and not request.video_url.lower().endswith(".mp4"):
            raise GenR8Error("Video input must be a public .mp4 URL.")
        if len(request.image_inputs) > 7:
            raise GenR8Error("Reference-to-video supports at most 7 input images.")
        if len(request.image_inputs) > 1 and request.duration and request.duration > 10:
            raise GenR8Error("Reference-to-video duration must be 10 seconds or less.")
        if request.video_url and (
            request.duration or request.aspect_ratio or request.resolution
        ):
            raise GenR8Error(
                "Video editing inherits duration, aspect ratio, and resolution from the input."
            )
        if request.duration is not None and request.duration < 1:
            raise GenR8Error("Duration must be at least 1 second.")
        return

    raise GenR8Error(f"Unsupported output format: {request.output_format}")


class GrokGenerator:
    def __init__(self, api_key: str | None = None) -> None:
        load_dotenv()
        self.api_key = api_key or os.getenv("XAI_API_KEY")
        if not self.api_key:
            raise GenR8Error("Set XAI_API_KEY or pass an API key explicitly.")

        import xai_sdk

        self._client = xai_sdk.Client(api_key=self.api_key)

    def generate(self, request: GenerationRequest) -> list[GenerationResult]:
        request = replace_request_prompt(request)
        validate_request(request)
        if request.output_format == "image":
            return self._generate_image(request)
        return [self._generate_video(request)]

    def _generate_image(self, request: GenerationRequest) -> list[GenerationResult]:
        image_urls = tuple(media_to_image_url(value) for value in request.image_inputs)
        kwargs: dict[str, object] = {
            "prompt": request.prompt,
            "model": IMAGE_MODEL,
        }
        if request.aspect_ratio:
            kwargs["aspect_ratio"] = request.aspect_ratio
        if request.resolution:
            kwargs["resolution"] = request.resolution

        if image_urls:
            if len(image_urls) == 1:
                kwargs["image_url"] = image_urls[0]
            else:
                kwargs["image_urls"] = list(image_urls)
            response = self._client.image.sample(**kwargs)
            return [_image_result(response)]

        if request.n > 1:
            responses = self._client.image.sample_batch(n=request.n, **kwargs)
            return [_image_result(response) for response in responses]

        response = self._client.image.sample(**kwargs)
        return [_image_result(response)]

    def _generate_video(self, request: GenerationRequest) -> GenerationResult:
        image_urls = tuple(media_to_image_url(value) for value in request.image_inputs)
        kwargs: dict[str, object] = {
            "prompt": request.prompt,
            "model": VIDEO_MODEL,
        }
        if request.video_url:
            kwargs["video_url"] = request.video_url
        elif len(image_urls) == 1:
            kwargs["image_url"] = image_urls[0]
        elif image_urls:
            kwargs["reference_image_urls"] = list(image_urls)
        if request.duration:
            kwargs["duration"] = request.duration
        if request.aspect_ratio:
            kwargs["aspect_ratio"] = request.aspect_ratio
        if request.resolution:
            kwargs["resolution"] = request.resolution

        response = self._client.video.generate(**kwargs)
        return GenerationResult(
            url=getattr(response, "url", None),
            model=getattr(response, "model", None),
            duration=getattr(response, "duration", None),
            respect_moderation=getattr(response, "respect_moderation", None),
        )


def download_result(result: GenerationResult, output_dir: Path) -> GenerationResult:
    if not result.url:
        raise GenR8Error("Result did not include a downloadable URL.")

    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = _suffix_from_url(result.url)
    destination = output_dir / f"genr8-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}{suffix}"

    response = requests.get(result.url, timeout=120)
    response.raise_for_status()
    destination.write_bytes(response.content)

    return GenerationResult(
        url=result.url,
        model=result.model,
        duration=result.duration,
        respect_moderation=result.respect_moderation,
        local_path=destination,
    )


def _suffix_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    suffix = Path(path).suffix
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".webm"}:
        return suffix
    if ".mp4" in url.lower():
        return ".mp4"
    return ".jpg"


def _image_result(response: object) -> GenerationResult:
    return GenerationResult(
        url=getattr(response, "url", None),
        model=getattr(response, "model", None),
        respect_moderation=getattr(response, "respect_moderation", None),
    )
