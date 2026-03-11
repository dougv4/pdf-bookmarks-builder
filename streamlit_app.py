#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import streamlit as st


APP_TITLE = "PDF Bookmarks Builder"

LLM_PROMPT_TEMPLATE = """Transforme o sumario desformatado abaixo em um formato estritamente estruturado para marcadores de PDF.

Regras obrigatorias:
- Retorne apenas linhas no formato `LEVEL | TITLE | PAGE`
- `LEVEL` deve ser apenas um destes valores: `UNIT`, `CHAPTER`, `SECTION`
- `TITLE` deve preservar o texto do sumario
- `PAGE` deve ser um numero inteiro
- Uma entrada por linha
- Nao inclua comentarios, markdown, cercas de codigo, bullets ou texto extra
- Ignore subtitulos menores que nao devam virar marcador
- Mantenha a hierarquia correta: `UNIT > CHAPTER > SECTION`

Exemplo de saida valida:
UNIT | UNIDADE 1: Olhares em perspectiva | 16
CHAPTER | CAPITULO 1: Romantismo: poesia (I) / Classes de palavras: revisao (I) / Noticia e enquete | 19
SECTION | LITERATURA | 19
SECTION | Foco no texto | 21

Agora converta o texto abaixo:

{{SUMARIO}}
"""


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


def parse_structured_toc(raw_text: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for line_no, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3:
            raise ValueError(f"Linha {line_no}: esperado formato `LEVEL | TITLE | PAGE`.")
        level, title, page_str = parts
        level = level.upper()
        if level not in {"UNIT", "CHAPTER", "SECTION"}:
            raise ValueError(f"Linha {line_no}: LEVEL invalido `{level}`.")
        if not page_str.isdigit():
            raise ValueError(f"Linha {line_no}: PAGE invalido `{page_str}`.")
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            raise ValueError(f"Linha {line_no}: TITLE vazio.")
        entries.append({"level": level, "title": title, "page": int(page_str)})
    if not entries:
        raise ValueError("Nenhuma entrada valida encontrada.")
    return entries


def build_outline_tree(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    roots: list[dict[str, object]] = []
    current_unit: dict[str, object] | None = None
    current_chapter: dict[str, object] | None = None

    def make_node(entry: dict[str, object]) -> dict[str, object]:
        return {
            "level": entry["level"],
            "title": entry["title"],
            "page": entry["page"],
            "children": [],
        }

    for entry in entries:
        level = str(entry["level"])
        node = make_node(entry)
        if level == "UNIT":
            roots.append(node)
            current_unit = node
            current_chapter = None
        elif level == "CHAPTER":
            if current_unit is None:
                roots.append(node)
            else:
                current_unit["children"].append(node)
            current_chapter = node
        else:
            if current_chapter is not None:
                current_chapter["children"].append(node)
            elif current_unit is not None:
                current_unit["children"].append(node)
            else:
                roots.append(node)
    return roots


def to_utf16_hex(text: str) -> str:
    return "FEFF" + text.encode("utf-16-be").hex().upper()


def write_pdfmark(tree: list[dict[str, object]], output_path: Path) -> None:
    with output_path.open("w", encoding="ascii") as ps_file:
        def emit(node: dict[str, object]) -> None:
            children = node["children"]
            line = f"[ /Title <{to_utf16_hex(str(node['title']))}> /Page {int(node['page'])}"
            if children:
                line += f" /Count {len(children)}"
            line += " /OUT pdfmark\n"
            ps_file.write(line)
            for child in children:
                emit(child)

        for root in tree:
            emit(root)


def render_tree_text(tree: list[dict[str, object]]) -> str:
    lines: list[str] = []

    def walk(node: dict[str, object], depth: int = 0) -> None:
        indent = "  " * depth
        lines.append(f"{indent}- p{node['page']} {node['title']}")
        for child in node["children"]:
            walk(child, depth + 1)

    for root in tree:
        walk(root)
    return "\n".join(lines)


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


def count_nodes(tree: list[dict[str, object]]) -> int:
    total = 0
    stack = list(tree)
    while stack:
        node = stack.pop()
        total += 1
        stack.extend(node["children"])
    return total


def build_ui() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption("Upload do PDF + otimizacao opcional + geracao de marcadores")

    with st.sidebar:
        st.subheader("Dependencias")
        deps = ("gs", "qpdf")
        for dep in deps:
            if shutil.which(dep):
                st.success(f"{dep}: ok")
            else:
                st.error(f"{dep}: ausente")
        st.divider()
        st.subheader("Otimizacao")
        optimize_before_bookmarks = st.checkbox(
            "Otimizar PDF antes de aplicar bookmarks",
            value=True,
        )
        color_resolution = st.slider("Color DPI", 72, 300, 150, 1)
        gray_resolution = st.slider("Gray DPI", 72, 300, 150, 1)
        jpeg_quality = st.slider("JPEG quality", 40, 95, 80, 1)

    left, right = st.columns([1, 1])
    with left:
        uploaded_pdf = st.file_uploader("Upload do PDF", type=["pdf"])
        output_name = st.text_input("Nome do PDF de saida", value="output.bookmarked.pdf")
    with right:
        st.subheader("Formato esperado")
        st.code(
            "UNIT | UNIDADE 1: Titulo | 16\n"
            "CHAPTER | CAPITULO 1: Titulo do capitulo | 19\n"
            "SECTION | LITERATURA | 19",
            language="text",
        )

    raw_summary = st.text_area(
        "Cole aqui o sumario formatado",
        height=320,
        placeholder="UNIT | UNIDADE 1: Olhares em perspectiva | 16\nCHAPTER | CAPITULO 1: ... | 19\nSECTION | LITERATURA | 19",
    )

    with st.expander("Prompt para limpar um sumario desformatado com LLM"):
        st.code(LLM_PROMPT_TEMPLATE, language="text")

    preview_button = st.button("Validar e gerar preview", use_container_width=True)
    build_button = st.button("Gerar PDF com marcadores", type="primary", use_container_width=True)

    tree: list[dict[str, object]] | None = None
    entries: list[dict[str, object]] = []

    if raw_summary.strip():
        try:
            entries = parse_structured_toc(raw_summary)
            tree = build_outline_tree(entries)
        except ValueError as exc:
            st.error(str(exc))

    if preview_button and tree is not None:
        st.subheader("Preview da arvore")
        st.code(render_tree_text(tree), language="text")
        c1, c2 = st.columns(2)
        c1.metric("Entradas", str(len(entries)))
        c2.metric("Marcadores", str(count_nodes(tree)))

    if build_button:
        missing = [dep for dep in ("gs", "qpdf") if not shutil.which(dep)]
        if missing:
            st.error(f"Dependencias ausentes: {', '.join(missing)}")
            return
        if uploaded_pdf is None:
            st.error("Envie um PDF antes de gerar os marcadores.")
            return
        if tree is None:
            st.error("Corrija o sumario estruturado antes de continuar.")
            return
        if not output_name.lower().endswith(".pdf"):
            st.error("O nome de saida precisa terminar com .pdf")
            return

        input_bytes = uploaded_pdf.getvalue()

        with tempfile.TemporaryDirectory(prefix="pdf_bookmarks_app_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "input.pdf"
            working_input_path = input_path
            optimized_path = tmp_path / "optimized.pdf"
            pdfmark_path = tmp_path / "bookmarks.ps"
            output_path = tmp_path / output_name
            preview_path = tmp_path / "bookmarks-preview.txt"

            input_path.write_bytes(input_bytes)
            write_pdfmark(tree, pdfmark_path)
            preview_path.write_text(render_tree_text(tree), encoding="utf-8")

            with st.status("Aplicando marcadores...", expanded=True) as status:
                results: list[CmdResult] = []
                if optimize_before_bookmarks:
                    status.write("Executando otimizacao com Ghostscript + qpdf...")
                    optimize_results = optimize_pdf(
                        input_pdf=input_path,
                        output_pdf=optimized_path,
                        color_resolution=color_resolution,
                        gray_resolution=gray_resolution,
                        jpeg_quality=jpeg_quality,
                    )
                    results.extend(optimize_results)
                    if optimize_results and optimize_results[-1].code == 0:
                        working_input_path = optimized_path

                if not results or results[-1].code == 0:
                    status.write("Aplicando marcadores e linearizando resultado final...")
                    results.extend(apply_bookmarks(working_input_path, pdfmark_path, output_path))

                for res in results:
                    status.write(f"`$ {res.cmd}`")
                    if res.stdout:
                        status.code(res.stdout)
                    if res.stderr:
                        status.code(res.stderr)
                    if res.code != 0:
                        status.update(label="Falha ao gerar marcadores", state="error", expanded=True)
                        st.error("Processo interrompido. Veja os logs acima.")
                        return

                if not output_path.exists():
                    status.update(label="Falha ao gerar marcadores", state="error", expanded=True)
                    st.error("Arquivo de saida nao foi gerado.")
                    return

                status.update(label="Marcadores gerados", state="complete", expanded=False)

            out_bytes = output_path.read_bytes()
            before_size = input_path.stat().st_size
            after_size = output_path.stat().st_size
            optimized_size = working_input_path.stat().st_size

            st.subheader("Resultado")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Entrada", f"{before_size / 1024 / 1024:.2f} MB")
            c2.metric("Apos otimizar", f"{optimized_size / 1024 / 1024:.2f} MB")
            c3.metric("Saida", f"{after_size / 1024 / 1024:.2f} MB")
            c4.metric("Marcadores", str(count_nodes(tree)))

            st.write(f"- Entrada: `{file_size_text(input_path)}`")
            if optimize_before_bookmarks:
                st.write(f"- Apos otimizacao: `{file_size_text(working_input_path)}`")
            st.write(f"- Saida: `{file_size_text(output_path)}`")

            st.download_button(
                label="Baixar PDF com marcadores",
                data=out_bytes,
                file_name=output_name,
                mime="application/pdf",
                use_container_width=True,
            )
            st.download_button(
                label="Baixar preview da arvore",
                data=preview_path.read_text(encoding="utf-8"),
                file_name="bookmarks-preview.txt",
                mime="text/plain",
                use_container_width=True,
            )


if __name__ == "__main__":
    build_ui()
