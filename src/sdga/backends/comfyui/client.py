"""HTTP client for a remote ComfyUI (docs/04-pipeline-stages.md §3).

Only the endpoints the pipeline actually needs, mapped onto the closed error taxonomy:

    POST /prompt            submit a bound graph
    GET  /history/{id}      the source of truth for completion
    GET  /view              fetch an output artifact
    POST /upload/image      upload a reference (phase P2, implemented here already)
    GET  /object_info       capability probe
    GET  /system_stats      identity and VRAM

`prompt_id` is supplied by us, derived from the request hash. ComfyUI honours a
caller-supplied id, which is what makes submission idempotent across process restarts.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...errors import BackendError


def _safe_json(payload: bytes) -> Any:
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


class ComfyUIClient:
    def __init__(self, base_url: str, *, timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    # ------------------------------------------------------------------ transport

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, bytes]:
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            # A 400 is a graph problem, not a transport problem: callers need the body.
            return exc.code, exc.read()
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            raise BackendError(
                "unreachable",
                f"{self.base_url}{path}: {exc}",
                remedy="is ComfyUI running, and is [backend] url correct?",
            ) from None

    def _json(self, method: str, path: str, *, data: bytes | None = None) -> Any:
        status, payload = self._request(
            method, path, data=data, headers={"Content-Type": "application/json"}
        )
        if status != 200:
            raise BackendError(
                "unreachable",
                f"{method} {path} returned HTTP {status}",
                payload={"body": payload.decode("utf-8", errors="replace")[:2000]},
            )
        parsed = _safe_json(payload)
        if parsed is None:
            raise BackendError("bad_output", f"{method} {path} did not return JSON")
        return parsed

    # ------------------------------------------------------------------ endpoints

    def submit(self, graph: Mapping[str, Any], *, prompt_id: str, client_id: str) -> dict[str, Any]:
        body = json.dumps({"prompt": graph, "client_id": client_id, "prompt_id": prompt_id}).encode(
            "utf-8"
        )
        status, payload = self._request(
            "POST", "/prompt", data=body, headers={"Content-Type": "application/json"}
        )
        parsed = _safe_json(payload)

        if status == 400:
            detail = parsed if isinstance(parsed, dict) else {}
            message = "invalid prompt"
            error = detail.get("error")
            if isinstance(error, dict) and error.get("message"):
                message = str(error["message"])
            elif isinstance(error, str):
                message = error
            raise BackendError(
                "rejected_graph",
                f"ComfyUI rejected {prompt_id}: {message}",
                payload=detail or {"body": payload.decode("utf-8", errors="replace")},
                remedy="a recipe or slot is wrong; the 400 body is recorded verbatim",
            )

        if status != 200:
            raise BackendError(
                "unreachable",
                f"POST /prompt returned HTTP {status}",
                payload={"body": payload.decode("utf-8", errors="replace")[:2000]},
            )
        if not isinstance(parsed, dict):
            raise BackendError("bad_output", "POST /prompt did not return a JSON object")
        return parsed

    def history(self, prompt_id: str) -> dict[str, Any]:
        parsed = self._json("GET", f"/history/{urllib.parse.quote(prompt_id)}")
        if not isinstance(parsed, dict):
            return {}
        return parsed

    def view(self, filename: str, subfolder: str = "", type: str = "output") -> bytes:
        query = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": type})
        status, payload = self._request("GET", f"/view?{query}")
        if status == 404:
            raise BackendError(
                "bad_output", f"/view has no file {filename!r} (subfolder={subfolder!r})"
            )
        if status != 200:
            raise BackendError("unreachable", f"GET /view returned HTTP {status}")
        return payload

    def upload_image(self, path: Path, name: str | None = None) -> dict[str, Any]:
        boundary = f"----sdga{uuid4().hex}"
        filename = name or Path(path).name
        content = Path(path).read_bytes()
        body = bytearray()
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode()
        )
        body.extend(b"Content-Type: image/png\r\n\r\n")
        body.extend(content)
        body.extend(f"\r\n--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n')
        body.extend(f"--{boundary}--\r\n".encode())

        status, payload = self._request(
            "POST",
            "/upload/image",
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        parsed = _safe_json(payload)
        if status != 200 or not isinstance(parsed, dict):
            raise BackendError(
                "unreachable",
                f"POST /upload/image returned HTTP {status}",
                payload={"body": payload.decode("utf-8", errors="replace")[:2000]},
            )
        return parsed

    def object_info(self) -> dict[str, Any]:
        parsed = self._json("GET", "/object_info")
        if not isinstance(parsed, dict):
            raise BackendError("bad_output", "/object_info did not return a JSON object")
        return parsed

    def system_stats(self) -> dict[str, Any]:
        parsed = self._json("GET", "/system_stats")
        if not isinstance(parsed, dict):
            raise BackendError("bad_output", "/system_stats did not return a JSON object")
        return parsed

    def interrupt(self) -> None:
        try:
            self._request("POST", "/interrupt")
        except BackendError:
            # Cancel is best-effort: the job's own timeout is the real backstop.
            pass


__all__ = ["ComfyUIClient"]
