from __future__ import annotations

import shutil
import subprocess
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CmdResult:
    code: int
    stdout: str
    stderr: str
    cmd: str


def resolve_binary(name: str) -> str:
    env_key = f"PDF_BUILDER_{name.upper()}_PATH"
    env_value = os.environ.get(env_key, "").strip()
    if env_value:
        return env_value
    found = shutil.which(name)
    if found:
        return found
    raise RuntimeError(f"Dependencia ausente: `{name}`")


def run_cmd(cmd: list[str]) -> CmdResult:
    proc = subprocess.run(cmd, text=True, capture_output=True, env=build_runtime_env())
    return CmdResult(
        code=proc.returncode,
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
        cmd=" ".join(cmd),
    )


def require_binary(name: str) -> str:
    return resolve_binary(name)


def build_runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    gs_resource_root = env.get("PDF_BUILDER_GS_RESOURCE_PATH", "").strip()
    if gs_resource_root:
        base = Path(gs_resource_root)
        gs_lib_parts: list[str] = []
        for candidate in (
            base / "lib",
            base / "fonts",
            base / "Resource" / "Init",
            base / "Resource" / "Font",
        ):
            if candidate.exists():
                gs_lib_parts.append(str(candidate))
        if gs_lib_parts:
            separator = ";" if os.name == "nt" else ":"
            env["GS_LIB"] = separator.join(gs_lib_parts)
            env["PDF_BUILDER_EFFECTIVE_GS_LIB"] = env["GS_LIB"]
    return env


def file_size_text(path: Path) -> str:
    size = path.stat().st_size
    return f"{size:,} bytes ({size / 1024 / 1024:.2f} MB)"


def optimize_pdf(
    input_pdf: Path,
    output_pdf: Path,
    color_resolution: int,
    gray_resolution: int,
    jpeg_quality: int,
) -> list[CmdResult]:
    tmp_unlinearized = output_pdf.with_suffix(".tmp.unlinearized.pdf")
    gs_bin = resolve_binary("gs")
    qpdf_bin = resolve_binary("qpdf")
    gs_cmd = [
        gs_bin,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.7",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        "-dDetectDuplicateImages=true",
        "-sColorConversionStrategy=RGB",
        "-dProcessColorModel=/DeviceRGB",
        "-dDownsampleColorImages=true",
        "-dColorImageDownsampleType=/Bicubic",
        f"-dColorImageResolution={color_resolution}",
        "-dDownsampleGrayImages=true",
        "-dGrayImageDownsampleType=/Bicubic",
        f"-dGrayImageResolution={gray_resolution}",
        "-dAutoFilterColorImages=false",
        "-dColorImageFilter=/DCTEncode",
        f"-dJPEGQ={jpeg_quality}",
        f"-sOutputFile={tmp_unlinearized}",
        str(input_pdf),
    ]
    qpdf_linearize_cmd = [qpdf_bin, "--linearize", str(tmp_unlinearized), str(output_pdf)]
    qpdf_check_cmd = [qpdf_bin, "--check", str(output_pdf)]

    results = [run_cmd(gs_cmd)]
    if results[-1].code != 0:
        return results

    results.append(run_cmd(qpdf_linearize_cmd))
    if results[-1].code != 0:
        return results

    if tmp_unlinearized.exists():
        tmp_unlinearized.unlink()

    results.append(run_cmd(qpdf_check_cmd))
    return results


def apply_bookmarks(input_pdf: Path, pdfmark_path: Path, output_pdf: Path) -> list[CmdResult]:
    tmp_pdf = output_pdf.with_suffix(".tmp.with-bookmarks.pdf")
    gs_bin = resolve_binary("gs")
    qpdf_bin = resolve_binary("qpdf")
    gs_cmd = [
        gs_bin,
        "-dBATCH",
        "-dNOPAUSE",
        "-dQUIET",
        "-sDEVICE=pdfwrite",
        f"-sOutputFile={tmp_pdf}",
        str(input_pdf),
        str(pdfmark_path),
    ]
    qpdf_linearize_cmd = [qpdf_bin, "--linearize", str(tmp_pdf), str(output_pdf)]
    qpdf_check_cmd = [qpdf_bin, "--check", str(output_pdf)]

    results = [run_cmd(gs_cmd)]
    if results[-1].code != 0:
        return results

    results.append(run_cmd(qpdf_linearize_cmd))
    if results[-1].code != 0:
        return results

    if tmp_pdf.exists():
        tmp_pdf.unlink()

    results.append(run_cmd(qpdf_check_cmd))
    return results
