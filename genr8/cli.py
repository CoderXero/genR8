from __future__ import annotations

import argparse
from pathlib import Path

from .client import GenerationRequest, GenR8Error, GrokGenerator, download_result
from .config import env_int, env_path, load_dotenv
from .video_pipeline import generate_video_sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="genr8",
        description="Generate safe images or videos with the xAI Grok API.",
    )
    parser.add_argument("-p", "--prompt", required=True)
    parser.add_argument(
        "-f",
        "--format",
        choices=("image", "video"),
        default="image",
        dest="output_format",
    )
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        help="Image path, public URL, or data URI. Repeat for multiple images.",
    )
    parser.add_argument("--video-url", help="Public .mp4 URL for video editing.")
    parser.add_argument("--duration", type=int, help="Video length in seconds.")
    parser.add_argument("--aspect-ratio", help='Aspect ratio such as "16:9" or "1:1".')
    parser.add_argument(
        "--resolution",
        help='Image: "1k" or "2k"; video: "480p" or "720p" where supported.',
    )
    parser.add_argument(
        "-n",
        type=int,
        default=1,
        help="Number of image variations for text-to-image generation.",
    )
    parser.add_argument(
        "--download",
        type=Path,
        help="Download the temporary output URL into this directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    request = GenerationRequest(
        prompt=args.prompt,
        output_format=args.output_format,
        image_inputs=tuple(args.image),
        video_url=args.video_url,
        duration=args.duration,
        aspect_ratio=args.aspect_ratio,
        resolution=args.resolution,
        n=args.n,
    )

    try:
        generator = GrokGenerator()
        if request.output_format == "video":
            output_dir = args.download or env_path("GENR8_OUTPUT_DIR", "output")
            results = [
                generate_video_sequence(
                    generator,
                    request,
                    output_dir,
                    min(env_int("MAX_VIDEO_LENGTH", 60), 60),
                )
            ]
        else:
            results = generator.generate(request)
            if args.download:
                results = [download_result(result, args.download) for result in results]
    except GenR8Error as exc:
        parser.error(str(exc))
    except Exception as exc:
        parser.exit(1, f"genr8: API request failed: {exc}\n")

    for index, result in enumerate(results, start=1):
        prefix = f"{index}: " if len(results) > 1 else ""
        if result.url:
            print(f"{prefix}{result.url}")
        if result.local_path:
            print(f"{prefix}saved {result.local_path}")
        if result.respect_moderation is False:
            print(f"{prefix}moderation rejected this output")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
