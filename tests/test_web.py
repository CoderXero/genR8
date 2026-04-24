from __future__ import annotations

from genr8.client import rewrite_sensual_prompt, validate_request
from genr8.web import UploadedFile, generation_request_from_values, render_page


def test_web_rewrites_nsfw_prompt_without_api_key() -> None:
    generation_request = generation_request_from_values(
        {
            "prompt": "make this nsfw",
            "output_format": "image",
            "duration": "",
            "image_urls": "",
            "video_url": "",
            "aspect_ratio": "",
            "resolution": "",
        }
    )

    validate_request(generation_request)
    rewritten = rewrite_sensual_prompt(generation_request.prompt)
    assert "sensual editorial" in rewritten
    assert "fully clothed" in rewritten


def test_web_renders_result_preview() -> None:
    page = render_page(
        {
            "prompt": "test",
            "output_format": "image",
            "duration": "",
            "image_urls": "",
            "video_url": "",
            "aspect_ratio": "",
            "resolution": "",
        },
        result_url="https://example.com/output.jpg",
    )

    assert '<img src="https://example.com/output.jpg"' in page


def test_theme_selector_renders_before_prompt() -> None:
    page = render_page({"theme": "dracula"})

    assert page.index('id="theme"') < page.index('id="prompt"')
    assert 'data-theme="dracula"' in page


def test_upload_controls_render() -> None:
    page = render_page()

    assert 'enctype="multipart/form-data"' in page
    assert 'id="image_files"' in page
    assert 'id="video_file"' in page


def test_image_upload_becomes_generation_input() -> None:
    request = generation_request_from_values(
        {
            "prompt": "test",
            "output_format": "image",
            "duration": "",
            "image_urls": "",
            "video_url": "",
            "aspect_ratio": "",
            "resolution": "",
            "theme": "charcoal",
        },
        (
            UploadedFile(
                field_name="image_files",
                filename="source.png",
                content_type="image/png",
                content=b"fake-image",
            ),
        ),
    )

    assert request.image_inputs == ("data:image/png;base64,ZmFrZS1pbWFnZQ==",)
