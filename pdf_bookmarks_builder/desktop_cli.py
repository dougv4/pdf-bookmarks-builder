from __future__ import annotations

import argparse
import json
import sys

from .service import ProcessRequest, dumps_json, process_pdf, validate_preview


def read_stdin_json() -> dict[str, object]:
    raw = sys.stdin.read().strip()
    if not raw:
        raise ValueError("Nenhum JSON recebido via stdin.")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("JSON de entrada deve ser um objeto.")
    return payload


def cmd_validate_preview() -> int:
    payload = read_stdin_json()
    structured_toc = str(payload.get("structured_toc", payload.get("structuredToc", "")))
    response = validate_preview(structured_toc)
    print(dumps_json(response.to_dict()))
    return 0 if response.valid else 1


def cmd_process_pdf() -> int:
    payload = read_stdin_json()
    request = ProcessRequest.from_dict(payload)
    response = process_pdf(request)
    print(dumps_json(response.to_dict()))
    return 0 if response.status == "success" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Desktop backend para PDF Bookmarks Builder.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-preview")
    subparsers.add_parser("process-pdf")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-preview":
            return cmd_validate_preview()
        if args.command == "process-pdf":
            return cmd_process_pdf()
        parser.error("Comando invalido.")
        return 2
    except Exception as exc:
        print(dumps_json({"status": "error", "errors": [str(exc)]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
