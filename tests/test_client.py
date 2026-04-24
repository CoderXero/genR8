from __future__ import annotations

import pytest

from genr8.client import (
    GenerationRequest,
    GenR8Error,
    rewrite_sensual_prompt,
    validate_request,
)


def test_rejects_explicit_nudity_prompt() -> None:
    request = GenerationRequest(
        prompt="make this nude",
        output_format="video",
        duration=5,
    )

    with pytest.raises(GenR8Error, match="Explicit"):
        validate_request(request)


def test_rewrites_spicy_prompt() -> None:
    request = GenerationRequest(
        prompt="make this spicy",
        output_format="image",
    )

    validate_request(request)
    rewritten = rewrite_sensual_prompt(request.prompt)
    assert "sensual editorial" in rewritten
    assert "fully clothed" in rewritten


def test_rejects_video_edit_with_generation_settings() -> None:
    request = GenerationRequest(
        prompt="make the lighting warmer",
        output_format="video",
        video_url="https://example.com/source.mp4",
        duration=5,
    )

    with pytest.raises(GenR8Error, match="inherits"):
        validate_request(request)


def test_rejects_too_many_reference_images() -> None:
    request = GenerationRequest(
        prompt="make a product showcase",
        output_format="video",
        image_inputs=tuple(f"https://example.com/{index}.jpg" for index in range(8)),
        duration=5,
    )

    with pytest.raises(GenR8Error, match="at most 7"):
        validate_request(request)


def test_accepts_text_to_image_variations() -> None:
    request = GenerationRequest(
        prompt="a clean product photo of a ceramic mug",
        output_format="image",
        n=4,
    )

    validate_request(request)
