from __future__ import annotations

from pathlib import Path

import pytest

from genr8.client import GenerationRequest, GenerationResult, GenR8Error
from genr8.video_pipeline import generate_video_sequence


class FakeGenerator:
    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> list[GenerationResult]:
        self.requests.append(request)
        return [GenerationResult(url=f"https://example.com/{len(self.requests)}.mp4")]


def test_rejects_duration_above_max(tmp_path: Path) -> None:
    request = GenerationRequest(
        prompt="test",
        output_format="video",
        duration=61,
    )

    with pytest.raises(GenR8Error, match="cannot exceed 60"):
        generate_video_sequence(FakeGenerator(), request, tmp_path, max_video_length=60)  # type: ignore[arg-type]


def test_chunks_video_generation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeGenerator()

    def fake_download(result: GenerationResult, output_dir: Path) -> GenerationResult:
        path = output_dir / f"chunk-{len(fake.requests)}.mp4"
        path.write_bytes(b"video")
        return GenerationResult(url=result.url, local_path=path)

    def fake_extract(video_path: Path, frame_path: Path) -> None:
        frame_path.write_bytes(b"frame")

    def fake_stitch(video_paths: list[Path], output_path: Path) -> None:
        output_path.write_bytes(b"stitched")

    monkeypatch.setattr("genr8.video_pipeline.download_result", fake_download)
    monkeypatch.setattr("genr8.video_pipeline.extract_last_frame", fake_extract)
    monkeypatch.setattr("genr8.video_pipeline.stitch_videos", fake_stitch)

    request = GenerationRequest(
        prompt="test",
        output_format="video",
        duration=12,
    )

    result = generate_video_sequence(fake, request, tmp_path, max_video_length=60)  # type: ignore[arg-type]

    assert [request.duration for request in fake.requests] == [5, 5, 2]
    assert fake.requests[1].image_inputs[0].endswith("-frame-01.jpg")
    assert result.local_path is not None
    assert result.local_path.name.endswith("-stitched.mp4")
