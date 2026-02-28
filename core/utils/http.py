from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class FetchResponse:
    ok: bool
    status: int
    text: str
    headers: dict[str, str]


class HttpError(RuntimeError):
    def __init__(self, message: str, *, status: int = 0, body_preview: str = "", headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.body_preview = body_preview
        self.headers = dict(headers or {})


def fetch_with_retries(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | bytes | None = None,
    timeout_ms: int = 20_000,
    retries: int = 3,
    accept: str = "*/*",
) -> FetchResponse:
    hdrs = dict(headers or {})
    hdrs.setdefault("User-Agent", "langskills/0.1 (+local)")
    hdrs.setdefault("Accept", accept)

    if isinstance(body, str):
        data = body.encode("utf-8")
    else:
        data = body

    last_err: Exception | None = None
    for attempt in range(0, max(0, int(retries or 0)) + 1):
        try:
            req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
            with urllib.request.urlopen(req, timeout=max(0.001, (timeout_ms or 20_000) / 1000)) as resp:
                status = int(getattr(resp, "status", 200))
                resp_headers = {str(k): str(v) for k, v in getattr(resp, "headers", {}).items()}
                raw = resp.read()
                text = raw.decode("utf-8", errors="replace")
                if not (200 <= status <= 299):
                    raise HttpError(f"HTTP {status}: {url}", status=status, body_preview=text[:2000], headers=resp_headers)
                return FetchResponse(ok=True, status=status, text=text, headers=resp_headers)
        except urllib.error.HTTPError as e:
            status = int(getattr(e, "code", 0) or 0)
            body_text = ""
            try:
                body_text = e.read().decode("utf-8", errors="replace")
            except Exception:
                body_text = ""
            hdrs = {str(k): str(v) for k, v in getattr(getattr(e, "headers", None), "items", lambda: [])()}
            last_err = HttpError(f"HTTP {status}: {url}", status=status, body_preview=body_text[:2000], headers=hdrs)
            retryable = status in {429, 500, 502, 503, 504}
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            retryable = True
        except Exception as e:  # pragma: no cover - unexpected path
            last_err = e
            retryable = False

        if not retryable or attempt >= retries:
            break
        time.sleep(0.5 * (2**attempt))

    if isinstance(last_err, HttpError):
        raise last_err
    raise RuntimeError(f"Fetch failed: {url}") from last_err


def try_parse_json_object(raw: str) -> dict | list | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            sliced = text[start : end + 1]
            try:
                return json.loads(sliced)
            except Exception:
                return None
        return None
