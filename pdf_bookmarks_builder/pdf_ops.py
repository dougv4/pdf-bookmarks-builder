from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CmdResult:
    code: int
    stdout: str
    stderr: str
    cmd: str


def run_cmd(cmd: list[str]) -> CmdResult:
    proc = subprocess.run(cmd, text=True, capture_output=True)
    return CmdResult(
        code=proc.returncode,
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
        cmd=" ".join(cmd),
    )


def require_binary(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"Dependencia ausente: `{name}`")
    return found


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
    gs_cmd = [
        "gs",
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
    qpdf_linearize_cmd = ["qpdf", "--linearize", str(tmp_unlinearized), str(output_pdf)]
    qpdf_check_cmd = ["qpdf", "--check", str(output_pdf)]

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
    gs_cmd = [
        "gs",
        "-dBATCH",
        "-dNOPAUSE",
        "-dQUIET",
        "-sDEVICE=pdfwrite",
        f"-sOutputFile={tmp_pdf}",
        str(input_pdf),
        str(pdfmark_path),
    ]
    qpdf_linearize_cmd = ["qpdf", "--linearize", str(tmp_pdf), str(output_pdf)]
    qpdf_check_cmd = ["qpdf", "--check", str(output_pdf)]

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
