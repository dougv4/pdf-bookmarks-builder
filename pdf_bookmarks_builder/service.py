from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .bookmarks import build_outline_tree, count_nodes, parse_structured_toc, render_tree_text, write_pdfmark
from .pdf_ops import CmdResult, apply_bookmarks, optimize_pdf


@dataclass
class ValidationResponse:
    valid: bool
    errors: list[str]
    bookmark_count: int
    preview_text: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ProcessRequest:
    input_pdf: str
    output_pdf: str
    structured_toc: str
    optimize: bool = True
    color_dpi: int = 150
    gray_dpi: int = 150
    jpeg_quality: int = 80

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ProcessRequest":
        def pick(*keys: str, default: object | None = None) -> object | None:
            for key in keys:
                if key in payload:
                    return payload[key]
            return default

        return cls(
            input_pdf=str(pick("input_pdf", "inputPdf", default="")),
            output_pdf=str(pick("output_pdf", "outputPdf", default="")),
            structured_toc=str(pick("structured_toc", "structuredToc", default="")),
            optimize=bool(pick("optimize", default=True)),
            color_dpi=int(pick("color_dpi", "colorDpi", default=150)),
            gray_dpi=int(pick("gray_dpi", "grayDpi", default=150)),
            jpeg_quality=int(pick("jpeg_quality", "jpegQuality", default=80)),
        )


@dataclass
class ProcessResponse:
    status: str
    errors: list[str]
    logs: list[dict[str, object]]
    input_size_bytes: int
    optimized_size_bytes: int
    output_size_bytes: int
    bookmark_count: int
    output_file_path: str
    preview_file_path: str
    preview_text: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def serialize_logs(results: list[CmdResult]) -> list[dict[str, object]]:
    return [
        {
            "cmd": result.cmd,
            "code": result.code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        for result in results
    ]


def validate_preview(structured_toc: str) -> ValidationResponse:
    try:
        entries = parse_structured_toc(structured_toc)
        tree = build_outline_tree(entries)
    except ValueError as exc:
        return ValidationResponse(
            valid=False,
            errors=[str(exc)],
            bookmark_count=0,
            preview_text="",
        )

    return ValidationResponse(
        valid=True,
        errors=[],
        bookmark_count=count_nodes(tree),
        preview_text=render_tree_text(tree),
    )


def process_pdf(request: ProcessRequest) -> ProcessResponse:
    validation = validate_preview(request.structured_toc)
    if not validation.valid:
        return ProcessResponse(
            status="error",
            errors=validation.errors,
            logs=[],
            input_size_bytes=0,
            optimized_size_bytes=0,
            output_size_bytes=0,
            bookmark_count=0,
            output_file_path=request.output_pdf,
            preview_file_path="",
            preview_text="",
        )

    input_path = Path(request.input_pdf).expanduser().resolve()
    output_path = Path(request.output_pdf).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path = output_path.with_suffix(".bookmarks-preview.txt")

    if not input_path.exists() or not input_path.is_file():
        return ProcessResponse(
            status="error",
            errors=[f"Arquivo de entrada inexistente: {input_path}"],
            logs=[],
            input_size_bytes=0,
            optimized_size_bytes=0,
            output_size_bytes=0,
            bookmark_count=0,
            output_file_path=str(output_path),
            preview_file_path=str(preview_path),
            preview_text="",
        )

    entries = parse_structured_toc(request.structured_toc)
    tree = build_outline_tree(entries)
    preview_text = render_tree_text(tree)

    with tempfile.TemporaryDirectory(prefix="pdf_desktop_backend_") as tmp_dir:
        tmp_root = Path(tmp_dir)
        pdfmark_path = tmp_root / "bookmarks.ps"
        optimized_path = tmp_root / "optimized.pdf"
        working_input = input_path
        write_pdfmark(tree, pdfmark_path)

        results: list[CmdResult] = []
        if request.optimize:
            optimize_results = optimize_pdf(
                input_pdf=input_path,
                output_pdf=optimized_path,
                color_resolution=request.color_dpi,
                gray_resolution=request.gray_dpi,
                jpeg_quality=request.jpeg_quality,
            )
            results.extend(optimize_results)
            if optimize_results and optimize_results[-1].code == 0 and optimized_path.exists():
                working_input = optimized_path

        if not results or results[-1].code == 0:
            results.extend(apply_bookmarks(working_input, pdfmark_path, output_path))

        preview_path.write_text(preview_text, encoding="utf-8")

        failed = next((item for item in results if item.code != 0), None)
        if failed is not None or not output_path.exists():
            errors = []
            if failed is not None:
                errors.append(failed.stderr or failed.stdout or "Falha desconhecida no processamento.")
            if not output_path.exists():
                errors.append("Arquivo final nao foi gerado.")
            return ProcessResponse(
                status="error",
                errors=errors,
                logs=serialize_logs(results),
                input_size_bytes=input_path.stat().st_size,
                optimized_size_bytes=working_input.stat().st_size if working_input.exists() else 0,
                output_size_bytes=output_path.stat().st_size if output_path.exists() else 0,
                bookmark_count=count_nodes(tree),
                output_file_path=str(output_path),
                preview_file_path=str(preview_path),
                preview_text=preview_text,
            )

        return ProcessResponse(
            status="success",
            errors=[],
            logs=serialize_logs(results),
            input_size_bytes=input_path.stat().st_size,
            optimized_size_bytes=working_input.stat().st_size if working_input.exists() else input_path.stat().st_size,
            output_size_bytes=output_path.stat().st_size,
            bookmark_count=count_nodes(tree),
            output_file_path=str(output_path),
            preview_file_path=str(preview_path),
            preview_text=preview_text,
        )


def dumps_json(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False)
