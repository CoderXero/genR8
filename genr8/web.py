from __future__ import annotations

import base64
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default
import html
import mimetypes
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .client import (
    GenerationRequest,
    GenR8Error,
    GrokGenerator,
    download_result,
    validate_request,
)
from .config import env_int, env_path, load_dotenv
from .video_pipeline import extract_last_frame, generate_video_sequence


load_dotenv()

THEMES = ("charcoal", "dracula", "cream")
DEFAULT_VALUES = {
    "prompt": "",
    "output_format": "image",
    "duration": "",
    "image_urls": "",
    "video_url": "",
    "aspect_ratio": "",
    "resolution": "",
    "theme": os.getenv("GENR8_THEME", "charcoal"),
}


@dataclass(frozen=True)
class UploadedFile:
    field_name: str
    filename: str
    content_type: str
    content: bytes


def render_page(
    values: dict[str, str] | None = None,
    result_url: str | None = None,
    source_url: str | None = None,
    error: str | None = None,
    notice: str | None = None,
) -> str:
    values = DEFAULT_VALUES | (values or {})
    theme = values["theme"] if values["theme"] in THEMES else "charcoal"
    is_video = values["output_format"] == "video"
    media = _media_markup(result_url, source_url, is_video)

    return f"""<!doctype html>
<html lang="en" data-theme="{html.escape(theme, quote=True)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>genR8</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #161819;
      --panel: #202426;
      --ink: #f2f4ef;
      --muted: #aab3ad;
      --line: #38403c;
      --field: #111414;
      --accent: #36c58a;
      --accent-dark: #249667;
      --danger: #ff7b7b;
      --shadow: 0 16px 38px rgba(0, 0, 0, 0.28);
    }}
    html[data-theme="dracula"] {{
      color-scheme: dark;
      --bg: #282a36;
      --panel: #343746;
      --ink: #f8f8f2;
      --muted: #c6c2df;
      --line: #565a72;
      --field: #21222c;
      --accent: #bd93f9;
      --accent-dark: #9e72df;
      --danger: #ff6e6e;
      --shadow: 0 16px 38px rgba(0, 0, 0, 0.28);
    }}
    html[data-theme="cream"] {{
      color-scheme: light;
      --bg: #f7f2e8;
      --panel: #fffaf0;
      --ink: #22201c;
      --muted: #6b6457;
      --line: #ddd2bf;
      --field: #ffffff;
      --accent: #28785e;
      --accent-dark: #1d5d48;
      --danger: #a83232;
      --shadow: 0 12px 34px rgba(58, 49, 35, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    main {{
      width: min(1180px, calc(100vw - 32px));
      margin: 24px auto;
      display: grid;
      grid-template-columns: minmax(340px, 460px) minmax(0, 1fr);
      gap: 22px;
      align-items: start;
    }}
    h1 {{
      margin: 0 0 18px;
      font-size: 30px;
      line-height: 1.08;
      font-weight: 720;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 18px;
      line-height: 1.2;
      letter-spacing: 0;
    }}
    form, .preview {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 18px;
    }}
    label {{
      display: block;
      margin: 14px 0 7px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 680;
    }}
    textarea, input, select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--field);
      color: var(--ink);
      font: inherit;
      min-height: 42px;
      padding: 10px 11px;
      outline: none;
    }}
    textarea {{
      min-height: 138px;
      resize: vertical;
      line-height: 1.42;
    }}
    textarea:focus, input:focus, select:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 24%, transparent);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .actions {{
      margin-top: 18px;
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    button, .download {{
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #07110d;
      font: inherit;
      font-weight: 720;
      min-height: 44px;
      padding: 0 16px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      text-decoration: none;
    }}
    button:hover, .download:hover {{ background: var(--accent-dark); }}
    .hint {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.35;
    }}
    .message {{
      margin: 0 0 14px;
      border-radius: 6px;
      padding: 11px 12px;
      line-height: 1.4;
      border: 1px solid var(--line);
      background: color-mix(in srgb, var(--accent) 11%, var(--panel));
    }}
    .message.error {{
      border-color: color-mix(in srgb, var(--danger) 55%, var(--line));
      background: color-mix(in srgb, var(--danger) 12%, var(--panel));
      color: var(--danger);
    }}
    .result {{
      display: grid;
      gap: 14px;
    }}
    .result img, .result video {{
      width: 100%;
      max-height: 70vh;
      object-fit: contain;
      background: #111;
      border-radius: 6px;
    }}
    .url {{
      overflow-wrap: anywhere;
      font-size: 13px;
      color: var(--muted);
    }}
    .empty {{
      min-height: 340px;
      display: grid;
      place-items: center;
      border: 1px dashed var(--line);
      border-radius: 6px;
      color: var(--muted);
      text-align: center;
      padding: 24px;
    }}
    .processing {{
      position: fixed;
      inset: 0;
      display: none;
      place-items: center;
      background: rgba(0, 0, 0, 0.58);
      z-index: 5;
    }}
    .processing.visible {{ display: grid; }}
    .processing-panel {{
      min-width: min(360px, calc(100vw - 32px));
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 22px;
      box-shadow: var(--shadow);
    }}
    .bar {{
      height: 8px;
      overflow: hidden;
      border-radius: 999px;
      background: var(--field);
      margin-top: 12px;
    }}
    .bar::before {{
      content: "";
      display: block;
      width: 38%;
      height: 100%;
      border-radius: inherit;
      background: var(--accent);
      animation: processing 1.1s ease-in-out infinite alternate;
    }}
    @keyframes processing {{
      from {{ transform: translateX(-20%); }}
      to {{ transform: translateX(180%); }}
    }}
    @media (max-width: 860px) {{
      main {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <form method="post" enctype="multipart/form-data" id="generate-form">
      <h1>genR8</h1>
      {_message(error, "error")}
      {_message(notice, "")}

      <label for="theme">Theme</label>
      <select id="theme" name="theme">
        <option value="charcoal" {_selected(values, "theme", "charcoal")}>Charcoal</option>
        <option value="dracula" {_selected(values, "theme", "dracula")}>Dracula</option>
        <option value="cream" {_selected(values, "theme", "cream")}>Cream</option>
      </select>

      <label for="prompt">Prompt</label>
      <textarea id="prompt" name="prompt" required>{_value(values, "prompt")}</textarea>

      <div class="grid">
        <div>
          <label for="output_format">Format</label>
          <select id="output_format" name="output_format">
            <option value="image" {_selected(values, "output_format", "image")}>Image</option>
            <option value="video" {_selected(values, "output_format", "video")}>Video</option>
          </select>
        </div>
        <div>
          <label for="duration">Length</label>
          <input id="duration" name="duration" type="number" min="1" max="{_max_video_length()}" value="{_value(values, "duration")}" placeholder="seconds">
        </div>
      </div>

      <label for="image_files">Image upload</label>
      <input id="image_files" name="image_files" type="file" accept="image/*" multiple>

      <label for="video_file">Video upload</label>
      <input id="video_file" name="video_file" type="file" accept="video/mp4,video/*">
      <div class="hint">Uploaded video is used as a starting reference for generated video. For xAI video edit, use a public .mp4 URL.</div>

      <label for="video_url">Public video URL</label>
      <input id="video_url" name="video_url" value="{_value(values, "video_url")}" placeholder="https://example.com/input.mp4">

      <div class="grid">
        <div>
          <label for="aspect_ratio">Aspect ratio</label>
          <input id="aspect_ratio" name="aspect_ratio" value="{_value(values, "aspect_ratio")}" placeholder="16:9">
        </div>
        <div>
          <label for="resolution">Resolution</label>
          <input id="resolution" name="resolution" value="{_value(values, "resolution")}" placeholder="720p">
        </div>
      </div>

      <div class="actions">
        <button type="submit">Generate</button>
        <span class="hint">Uses .env settings and saves completed media into output/.</span>
      </div>
    </form>

    <section class="preview" aria-live="polite">
      <h2>Output</h2>
      <div class="result">{media}</div>
    </section>
  </main>
  <div class="processing" id="processing">
    <div class="processing-panel">
      <strong>Processing</strong>
      <div class="hint">Waiting for the xAI generation request to complete.</div>
      <div class="bar"></div>
    </div>
  </div>
  <script>
    const theme = document.getElementById("theme");
    const form = document.getElementById("generate-form");
    const processing = document.getElementById("processing");
    theme.addEventListener("change", () => {{
      document.documentElement.dataset.theme = theme.value;
    }});
    form.addEventListener("submit", () => {{
      processing.classList.add("visible");
    }});
  </script>
</body>
</html>"""


def values_from_form(body: bytes) -> dict[str, str]:
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    values = DEFAULT_VALUES.copy()
    for key in values:
        values[key] = parsed.get(key, [values[key]])[0].strip()
    return values


def values_and_uploads_from_body(
    body: bytes, content_type: str
) -> tuple[dict[str, str], tuple[UploadedFile, ...]]:
    if not content_type.startswith("multipart/form-data"):
        return values_from_form(body), ()

    message = BytesParser(policy=default).parsebytes(
        b"Content-Type: "
        + content_type.encode("utf-8")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + body
    )
    values = DEFAULT_VALUES.copy()
    uploads: list[UploadedFile] = []
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename:
            uploads.append(
                UploadedFile(
                    field_name=name,
                    filename=Path(filename).name,
                    content_type=part.get_content_type(),
                    content=payload,
                )
            )
        elif name in values:
            values[name] = payload.decode(part.get_content_charset() or "utf-8").strip()
    return values, tuple(uploads)


def generation_request_from_values(
    values: dict[str, str], uploads: tuple[UploadedFile, ...] = ()
) -> GenerationRequest:
    duration = int(values["duration"]) if values["duration"] else None
    image_inputs = list(_split_urls(values["image_urls"]))
    video_upload = _video_upload(uploads)
    for upload in _image_uploads(uploads):
        image_inputs.append(_image_upload_to_data_uri(upload))

    if video_upload:
        if values["video_url"]:
            raise GenR8Error("Use either a video upload or a public video URL, not both.")
        if values["output_format"] != "video":
            raise GenR8Error("Video uploads are only supported for video generation.")
        image_inputs.append(str(_video_upload_to_reference_frame(video_upload)))

    return GenerationRequest(
        prompt=values["prompt"],
        output_format=values["output_format"],  # type: ignore[arg-type]
        image_inputs=tuple(image_inputs),
        video_url=values["video_url"] or None,
        duration=duration,
        aspect_ratio=values["aspect_ratio"] or None,
        resolution=values["resolution"] or None,
    )


class GenR8Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/":
            self._send_html(render_page())
            return
        if self.path.startswith("/output/"):
            self._send_output_file()
            return
        self.send_error(404)

    def do_HEAD(self) -> None:
        if self.path != "/":
            self.send_error(404)
            return
        self._send_html(render_page(), include_body=False)

    def do_POST(self) -> None:
        if self.path != "/":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        values, uploads = values_and_uploads_from_body(
            self.rfile.read(length),
            self.headers.get("Content-Type", ""),
        )
        result_url = None
        source_url = None
        error = None
        notice = None

        try:
            generation_request = generation_request_from_values(values, uploads)
            validate_request(generation_request)
            generator = GrokGenerator()
            if generation_request.output_format == "video":
                saved = generate_video_sequence(
                    generator,
                    generation_request,
                    _output_dir(),
                    _max_video_length(),
                )
                result = saved
                source_url = saved.url
                result_url = f"/output/{saved.local_path.name}" if saved.local_path else None
            else:
                results = generator.generate(generation_request)
                result = results[0] if results else None
                source_url = result.url if result else None
                if result:
                    saved = download_result(result, _output_dir())
                    result_url = (
                        f"/output/{saved.local_path.name}" if saved.local_path else None
                    )
            if result and result.respect_moderation is False:
                notice = "The provider moderation response rejected this output."
        except GenR8Error as exc:
            error = str(exc)
        except Exception as exc:
            error = f"API request failed: {exc}"

        self._send_html(render_page(values, result_url, source_url, error, notice))

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _send_html(self, body: str, include_body: bool = True) -> None:
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if include_body:
            self.wfile.write(encoded)

    def _send_output_file(self) -> None:
        name = Path(unquote(urlparse(self.path).path).removeprefix("/output/")).name
        path = _output_dir() / name
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return

        data = path.read_bytes()
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(data)))
        if "download=1" in urlparse(self.path).query:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(data)


def _media_markup(
    result_url: str | None, source_url: str | None, is_video: bool
) -> str:
    if not result_url:
        return '<div class="empty">Generated media appears here after the xAI request completes.</div>'

    safe_url = html.escape(result_url, quote=True)
    source_link = ""
    if source_url:
        safe_source = html.escape(source_url, quote=True)
        source_link = (
            f'<a class="url" href="{safe_source}" target="_blank" rel="noreferrer">'
            f"Source URL: {safe_source}</a>"
        )

    if is_video:
        media = f'<video src="{safe_url}" controls playsinline></video>'
    else:
        media = f'<img src="{safe_url}" alt="Generated output">'
    return (
        media
        + f'<a class="download" href="{safe_url}?download=1" download>Download</a>'
        + f'<a class="url" href="{safe_url}" target="_blank" rel="noreferrer">{safe_url}</a>'
        + source_link
    )


def _split_urls(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    parts = value.replace(",", "\n").splitlines()
    return tuple(part.strip() for part in parts if part.strip())


def _image_uploads(uploads: tuple[UploadedFile, ...]) -> tuple[UploadedFile, ...]:
    return tuple(
        upload
        for upload in uploads
        if upload.field_name == "image_files" and upload.content
    )


def _video_upload(uploads: tuple[UploadedFile, ...]) -> UploadedFile | None:
    for upload in uploads:
        if upload.field_name == "video_file" and upload.content:
            return upload
    return None


def _image_upload_to_data_uri(upload: UploadedFile) -> str:
    if not upload.content_type.startswith("image/"):
        raise GenR8Error(f"Unsupported image upload type: {upload.filename}")
    encoded = base64.b64encode(upload.content).decode("ascii")
    return f"data:{upload.content_type};base64,{encoded}"


def _video_upload_to_reference_frame(upload: UploadedFile) -> Path:
    if upload.content_type not in {"video/mp4", "application/mp4"} and not upload.filename.lower().endswith(".mp4"):
        raise GenR8Error("Video upload must be an .mp4 file.")

    upload_dir = _output_dir() / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stem = f"upload-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    video_path = upload_dir / f"{stem}.mp4"
    frame_path = upload_dir / f"{stem}-last-frame.jpg"
    video_path.write_bytes(upload.content)
    extract_last_frame(video_path, frame_path)
    return frame_path


def _output_dir() -> Path:
    return env_path("GENR8_OUTPUT_DIR", "output")


def _max_video_length() -> int:
    return min(env_int("MAX_VIDEO_LENGTH", 60), 60)


def _value(values: dict[str, str], key: str) -> str:
    return html.escape(values[key], quote=True)


def _selected(values: dict[str, str], key: str, option: str) -> str:
    return "selected" if values[key] == option else ""


def _message(message: str | None, kind: str) -> str:
    if not message:
        return ""
    classes = "message"
    if kind:
        classes += f" {kind}"
    return f'<p class="{classes}">{html.escape(message)}</p>'


def main() -> None:
    load_dotenv()
    host = os.getenv("GENR8_HOST", "127.0.0.1")
    port = env_int("GENR8_PORT", 8000)
    _output_dir().mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), GenR8Handler)
    print(f"genR8 web UI running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
