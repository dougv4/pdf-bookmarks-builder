#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pdf_bookmarks_builder.service import ProcessRequest, process_pdf, validate_preview  # noqa: E402


MINIMAL_PDF = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Count 1 /Kids [3 0 R] >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 16 Tf 72 180 Td (Smoke test) Tj ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000063 00000 n 
0000000122 00000 n 
0000000248 00000 n 
0000000342 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
412
%%EOF
"""


def main() -> int:
    sample_toc = "UNIT | UNIDADE 1 | 1\nCHAPTER | CAPITULO 1 | 1\nSECTION | LEITURA | 1"
    validation = validate_preview(sample_toc)
    if not validation.valid:
        raise SystemExit(f"validate_preview falhou: {validation.errors}")

    with tempfile.TemporaryDirectory(prefix="pdf_builder_smoke_") as tmp_dir:
        tmp_root = Path(tmp_dir)
        input_pdf = tmp_root / "input.pdf"
        output_pdf = tmp_root / "output.pdf"
        input_pdf.write_bytes(MINIMAL_PDF)
        response = process_pdf(
            ProcessRequest(
                input_pdf=str(input_pdf),
                output_pdf=str(output_pdf),
                structured_toc=sample_toc,
                optimize=True,
                color_dpi=150,
                gray_dpi=150,
                jpeg_quality=80,
            )
        )
        if response.status != "success":
            raise SystemExit(f"process_pdf falhou: {response.errors}")
        if not output_pdf.exists():
            raise SystemExit("output.pdf nao foi gerado no smoke test.")
        if response.bookmark_count != 3:
            raise SystemExit(f"bookmark_count inesperado: {response.bookmark_count}")
        print("smoke-test-ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
