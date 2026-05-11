from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import parse

from app.utils.file_utils import atomic_write_json, ensure_dir

DEFAULT_STATE_DIR_NAME = "pi_gateway"


@dataclass(frozen=True)
class DutResultReceiverSettings:
    host: str
    port: int
    result_file: Path


def now_utc_iso8601() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_args(argv: list[str] | None = None) -> DutResultReceiverSettings:
    parser = argparse.ArgumentParser(description="DuckPark Pi DUT result receiver")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--result-file", default=None)
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[2]
    default_state_dir = project_root / "run_data" / DEFAULT_STATE_DIR_NAME
    state_dir = Path(args.state_dir or default_state_dir)
    result_file = Path(args.result_file or state_dir / "dut_result.json")
    ensure_dir(result_file.parent)

    return DutResultReceiverSettings(
        host=str(args.host).strip() or "0.0.0.0",
        port=max(int(args.port), 1),
        result_file=result_file,
    )


def normalize_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    received_at_utc = str(normalized.get("received_at_utc") or "").strip()
    if not received_at_utc:
        normalized["received_at_utc"] = now_utc_iso8601()
    return normalized


def write_result_payload(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_result_payload(payload)
    atomic_write_json(path, normalized)
    return normalized


def _send_json_response(
    handler: BaseHTTPRequestHandler,
    status: HTTPStatus,
    payload: dict[str, Any],
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status.value)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def build_handler(result_file: Path):
    class DutResultHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            sys.stdout.write(
                f"{now_utc_iso8601()} dut-result-receiver "
                f"{self.address_string()} {format % args}\n"
            )
            sys.stdout.flush()

        def do_GET(self) -> None:
            parsed_path = parse.urlparse(self.path)
            if parsed_path.path != "/healthz":
                _send_json_response(
                    self,
                    HTTPStatus.NOT_FOUND,
                    {"success": False, "error": "not_found"},
                )
                return

            _send_json_response(
                self,
                HTTPStatus.OK,
                {"success": True, "data": {"status": "ok", "result_file": str(result_file)}},
            )

        def do_POST(self) -> None:
            parsed_path = parse.urlparse(self.path)
            if parsed_path.path not in {"/dut-results", "/results"}:
                _send_json_response(
                    self,
                    HTTPStatus.NOT_FOUND,
                    {"success": False, "error": "not_found"},
                )
                return

            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0:
                _send_json_response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"success": False, "error": "empty_body"},
                )
                return

            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                _send_json_response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"success": False, "error": "invalid_json"},
                )
                return

            if not isinstance(payload, dict):
                _send_json_response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"success": False, "error": "payload_must_be_object"},
                )
                return

            normalized = write_result_payload(result_file, payload)
            _send_json_response(
                self,
                HTTPStatus.OK,
                {"success": True, "data": normalized},
            )

    return DutResultHandler


def run_server(settings: DutResultReceiverSettings) -> int:
    server = ThreadingHTTPServer(
        (settings.host, settings.port), build_handler(settings.result_file)
    )
    sys.stdout.write(
        f"{now_utc_iso8601()} dut-result-receiver start "
        f"host={settings.host} port={settings.port} result_file={settings.result_file}\n"
    )
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    settings = parse_args(argv)
    return run_server(settings)


if __name__ == "__main__":
    raise SystemExit(main())
