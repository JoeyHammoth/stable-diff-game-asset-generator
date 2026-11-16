#!/usr/bin/env python3
"""Reference MusicGen service for sdga's `[audio] bed = "musicgen"` contract (docs/04 §10).

Why this is a separate process rather than a backend class: the pipeline never imports torch,
and torch+the weights are a multi-gigabyte, GPU-shaped dependency. This script is the other side
of the HTTP contract, isolated so `sdga` stays installable with the standard library alone.

    GET  /health   -> {"model": "facebook/musicgen-small", "sample_rate": 32000}
    POST /generate -> audio/wav bytes, given
         {"prompt", "negative_prompt", "duration_s", "sample_rate", "seed"}

Requirements (not installed with sdga):

    python -m venv .venv-musicgen
    .venv-musicgen/Scripts/activate          # or: source .venv-musicgen/bin/activate
    pip install torch --index-url https://download.pytorch.org/whl/cu126   # CPU: plain torch
    pip install transformers numpy
    python tools/musicgen_server.py --model facebook/musicgen-small --port 8765

Two contract details worth knowing:

* MusicGen is token-conditioned: it emits 50 audio tokens per second, so the server asks for
  `ceil(duration_s * 50) + 2` tokens and lets sdga cut the excess. It never pads a short render
  with silence at the end, which would become an audible gap at the loop seam.
* Stock MusicGen has no negative conditioning. The negative prompt is folded into the text as
  "Avoid: ...", which is weaker than a real CFG negative but keeps a lead melody out of the
  prompt. The melody is mixed in afterwards regardless, so the leitmotif is not at risk.
"""

from __future__ import annotations

import argparse
import array
import io
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

TOKENS_PER_SECOND = 50


def _wav_bytes(samples: Any, sample_rate: int) -> bytes:
    """Mono 16-bit WAV from a float waveform in [-1, 1]."""
    clipped = samples.clip(-1.0, 1.0) if hasattr(samples, "clip") else samples
    pcm = array.array("h", (int(round(float(value) * 32767)) for value in clipped))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


class MusicGen:
    """Loads once, generates under a lock, and reports its own sample rate."""

    def __init__(self, model_name: str, device: str) -> None:
        import torch
        from transformers import AutoProcessor, MusicgenForConditionalGeneration

        self._torch = torch
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.name = model_name
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = MusicgenForConditionalGeneration.from_pretrained(model_name).to(device).eval()
        self.sample_rate = int(self.model.config.audio_encoder.sampling_rate)
        self._lock = threading.Lock()
        print(f"loaded {model_name} on {device} at {self.sample_rate} Hz", flush=True)

    def render(self, prompt: str, negative: str, duration_s: float, seed: int) -> Any:
        text = prompt if not negative.strip() else f"{prompt}. Avoid: {negative.strip()}"
        tokens = max(8, int(round(duration_s * TOKENS_PER_SECOND)) + 2)
        inputs = self.processor(text=[text], padding=True, return_tensors="pt").to(self.device)
        with self._lock, self._torch.inference_mode():
            self._torch.manual_seed(seed)
            audio = self.model.generate(
                **inputs,
                do_sample=True,
                guidance_scale=3.0,
                max_new_tokens=tokens,
            )
        return audio[0, 0].detach().float().cpu().numpy()


class Handler(BaseHTTPRequestHandler):
    service: MusicGen

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server names the verb this way
        if self.path != "/health":
            self.send_error(404)
            return
        body = json.dumps(
            {"model": self.service.name, "sample_rate": self.service.sample_rate}
        ).encode()
        self._send(200, "application/json", body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/generate":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            duration_s = float(payload["duration_s"])
            seed = int(payload.get("seed") or 0)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self._send(400, "application/json", json.dumps({"error": str(exc)}).encode())
            return
        if duration_s <= 0 or duration_s > 60:
            self._send(400, "application/json", b'{"error": "duration_s outside 0..60"}')
            return
        requested_rate = payload.get("sample_rate")
        if requested_rate is not None and int(requested_rate) != self.service.sample_rate:
            self._send(
                409,
                "application/json",
                json.dumps(
                    {
                        "error": (
                            f"model runs at {self.service.sample_rate} Hz, request asked for "
                            f"{requested_rate} Hz"
                        )
                    }
                ).encode(),
            )
            return

        samples = self.service.render(
            prompt=str(payload.get("prompt") or "instrumental ambient game bed, no lead melody"),
            negative=str(payload.get("negative_prompt") or "lead melody, vocals"),
            duration_s=duration_s,
            seed=seed,
        )
        self._send(200, "audio/wav", _wav_bytes(samples, self.service.sample_rate))

    def log_message(self, *args: object) -> None:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="facebook/musicgen-small")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    Handler.service = MusicGen(args.model, args.device)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
