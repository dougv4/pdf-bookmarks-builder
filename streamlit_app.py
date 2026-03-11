#!/usr/bin/env python3
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import streamlit as st

from pdf_bookmarks_builder.bookmarks import (
    LLM_PROMPT_TEMPLATE,
    build_outline_tree,
    count_nodes,
    parse_structured_toc,
    render_tree_text,
    write_pdfmark,
)
from pdf_bookmarks_builder.pdf_ops import apply_bookmarks, file_size_text, optimize_pdf


APP_TITLE = "PDF Bookmarks Builder"


def build_ui() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption("Upload do PDF + otimizacao opcional + geracao de marcadores")
    st.info(
        "Como usar:\n"
        "1. Suba o PDF.\n"
        "2. Copie o sumario bruto do livro.\n"
        "3. Abra o bloco `Prompt para limpar um sumario desformatado com LLM` e use esse prompt no seu LLM.\n"
        "4. Cole no app apenas a resposta final no formato `LEVEL | TITLE | PAGE`.\n"
        "5. Clique em `Validar e gerar preview` para revisar a arvore.\n"
        "6. Se o preview estiver correto, clique em `Gerar PDF com marcadores`.\n"
        "7. Baixe o PDF final com bookmarks."
    )

    with st.sidebar:
        st.subheader("Dependencias")
        for dep in ("gs", "qpdf"):
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

    tree = None
    entries = []

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
                results = []
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
