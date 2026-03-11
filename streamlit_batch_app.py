#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path

import streamlit as st

from pdf_bookmarks_builder.batch_models import BatchItemContract
from pdf_bookmarks_builder.bookmarks import (
    LLM_PROMPT_TEMPLATE,
    build_outline_tree,
    count_nodes,
    parse_structured_toc,
    render_tree_text,
    write_pdfmark,
)
from pdf_bookmarks_builder.llm_clients import GeminiClient, OpenAIClient
from pdf_bookmarks_builder.pdf_ops import apply_bookmarks, optimize_pdf
from pdf_bookmarks_builder.toc_detection import detect_toc_candidates, extract_front_matter_text


APP_TITLE = "PDF Bookmarks Builder V2"
ITEMS_STATE_KEY = "batch_items_v2"
COMMON_MODELS = {
    "OpenAI": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "Custom"],
    "Gemini": ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "Custom"],
}


def make_item_id(filename: str, data: bytes) -> str:
    digest = hashlib.sha1()
    digest.update(filename.encode("utf-8", errors="ignore"))
    digest.update(str(len(data)).encode("ascii"))
    digest.update(data[:2048])
    return digest.hexdigest()[:12]


def sanitize_stem(filename: str) -> str:
    stem = Path(filename).stem
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return cleaned or "document"


def get_api_key(provider: str) -> str:
    return st.session_state.get(f"api_key_{provider.lower()}", "").strip()


def get_model(provider: str, selected_model: str, custom_model: str) -> str:
    if selected_model == "Custom":
        return custom_model.strip()
    return selected_model.strip()


def get_client(provider: str, api_key: str, model: str):
    if provider == "OpenAI":
        return OpenAIClient(api_key=api_key, model=model)
    return GeminiClient(api_key=api_key, model=model)


def build_prompt(raw_toc: str) -> str:
    return LLM_PROMPT_TEMPLATE.replace("{{SUMARIO}}", raw_toc.strip())


def detect_and_structure_item(
    filename: str,
    file_bytes: bytes,
    provider: str,
    model: str,
    api_key: str,
    max_pages: int,
) -> dict[str, object]:
    item_id = make_item_id(filename, file_bytes)
    contract = BatchItemContract(
        item_id=item_id,
        input_filename=filename,
        provider=provider,
        model=model,
        input_size_bytes=len(file_bytes),
        final_status="detected",
    )
    raw_toc = ""
    structured = ""
    preview = ""
    extracted_pages = extract_front_matter_text(file_bytes, max_pages=max_pages)
    candidates = detect_toc_candidates(extracted_pages)
    contract.candidate_summaries = [
        f"p.{candidate.start_page}-{candidate.end_page} | score {candidate.score:.1f} | {', '.join(candidate.reasons)}"
        for candidate in candidates
    ]

    if not candidates:
        contract.validation_status = "manual review required"
        contract.final_status = "review_required"
        contract.manual_review_required = True
        contract.error_message = "Nenhum bloco forte de sumario foi detectado nas paginas iniciais."
        return {
            "contract": contract,
            "input_bytes": file_bytes,
            "raw_toc": raw_toc,
            "structured_toc_text": structured,
            "preview_text": preview,
        }

    best = candidates[0]
    raw_toc = best.raw_text
    contract.detected_raw_toc = raw_toc
    if best.score < 12:
        contract.validation_status = "manual review required"
        contract.manual_review_required = True
        contract.error_message = "Sumario detectado com baixa confianca. Revise antes de gerar o PDF final."
    else:
        contract.validation_status = "detected"

    if api_key:
        client = get_client(provider, api_key, model)
        structured = client.generate(build_prompt(raw_toc))
        preview, contract = apply_validation_results(contract, structured)
    else:
        contract.validation_status = "manual review required"
        contract.manual_review_required = True
        contract.error_message = "API key ausente. Revise e preencha a chave antes de chamar o LLM."

    return {
        "contract": contract,
        "input_bytes": file_bytes,
        "raw_toc": raw_toc,
        "structured_toc_text": structured,
        "preview_text": preview,
    }


def apply_validation_results(contract: BatchItemContract, structured_text: str) -> tuple[str, BatchItemContract]:
    structured = structured_text.strip()
    updated = replace(contract, structured_toc_text=structured)
    if not structured:
        updated.validation_status = "manual review required"
        updated.final_status = "review_required"
        updated.manual_review_required = True
        updated.bookmark_count = 0
        updated.error_message = updated.error_message or "Resposta vazia do LLM."
        return "", updated

    try:
        entries = parse_structured_toc(structured)
        tree = build_outline_tree(entries)
    except ValueError as exc:
        updated.validation_status = "invalid"
        updated.final_status = "review_required"
        updated.manual_review_required = True
        updated.bookmark_count = 0
        updated.error_message = str(exc)
        return "", updated

    updated.validation_status = "valid"
    updated.final_status = "ready"
    updated.bookmark_count = count_nodes(tree)
    updated.error_message = ""
    return render_tree_text(tree), updated


def sync_items_from_ui() -> list[dict[str, object]]:
    items = st.session_state.get(ITEMS_STATE_KEY, [])
    synced: list[dict[str, object]] = []
    for item in items:
        contract: BatchItemContract = item["contract"]
        raw_key = f"raw_toc_{contract.item_id}"
        structured_key = f"structured_toc_{contract.item_id}"
        raw_toc = st.session_state.get(raw_key, item.get("raw_toc", "")).strip()
        structured = st.session_state.get(structured_key, item.get("structured_toc_text", "")).strip()
        contract = replace(contract, detected_raw_toc=raw_toc)
        preview_text, contract = apply_validation_results(contract, structured)
        synced.append(
            {
                **item,
                "contract": contract,
                "raw_toc": raw_toc,
                "structured_toc_text": structured,
                "preview_text": preview_text,
            }
        )
    st.session_state[ITEMS_STATE_KEY] = synced
    return synced


def rerun_item_with_llm(item_id: str, provider: str, model: str, api_key: str) -> None:
    items = st.session_state.get(ITEMS_STATE_KEY, [])
    updated_items: list[dict[str, object]] = []
    for item in items:
        contract: BatchItemContract = item["contract"]
        if contract.item_id != item_id:
            updated_items.append(item)
            continue
        raw_toc = st.session_state.get(f"raw_toc_{item_id}", item.get("raw_toc", "")).strip()
        contract = replace(contract, provider=provider, model=model, detected_raw_toc=raw_toc)
        if not raw_toc:
            contract.validation_status = "manual review required"
            contract.final_status = "review_required"
            contract.manual_review_required = True
            contract.error_message = "Bloco bruto do sumario vazio."
            updated_items.append({**item, "contract": contract, "raw_toc": raw_toc, "structured_toc_text": "", "preview_text": ""})
            continue
        try:
            structured = get_client(provider, api_key, model).generate(build_prompt(raw_toc))
            preview_text, contract = apply_validation_results(contract, structured)
            updated_items.append(
                {
                    **item,
                    "contract": contract,
                    "raw_toc": raw_toc,
                    "structured_toc_text": structured,
                    "preview_text": preview_text,
                }
            )
            st.session_state[f"structured_toc_{item_id}"] = structured
        except Exception as exc:
            contract.validation_status = "manual review required"
            contract.final_status = "review_required"
            contract.manual_review_required = True
            contract.error_message = str(exc)
            updated_items.append({**item, "contract": contract, "raw_toc": raw_toc, "structured_toc_text": item.get("structured_toc_text", ""), "preview_text": item.get("preview_text", "")})
    st.session_state[ITEMS_STATE_KEY] = updated_items


def build_zip_bundle(
    items: list[dict[str, object]],
    optimize_before_bookmarks: bool,
    color_resolution: int,
    gray_resolution: int,
    jpeg_quality: int,
) -> tuple[bytes, list[dict[str, object]]]:
    bundle = io.BytesIO()
    manifest: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="pdf_bookmarks_batch_") as tmp_dir:
        tmp_root = Path(tmp_dir)
        with zipfile.ZipFile(bundle, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in items:
                contract: BatchItemContract = item["contract"]
                contract = replace(contract)
                stem = sanitize_stem(contract.input_filename)
                contract.input_size_bytes = len(item["input_bytes"])
                raw_toc = item.get("raw_toc", "")
                structured_toc = item.get("structured_toc_text", "")
                preview_text = item.get("preview_text", "")

                if contract.validation_status != "valid":
                    contract.final_status = "skipped"
                    contract.error_message = contract.error_message or "Item nao esta valido para gerar bookmarks."
                    manifest.append(contract.to_dict())
                    if raw_toc:
                        archive.writestr(f"reports/{stem}.raw-toc.txt", raw_toc)
                    if structured_toc:
                        archive.writestr(f"reports/{stem}.structured-toc.txt", structured_toc)
                    continue

                item_dir = tmp_root / contract.item_id
                item_dir.mkdir(parents=True, exist_ok=True)
                input_path = item_dir / "input.pdf"
                working_input_path = input_path
                optimized_path = item_dir / "optimized.pdf"
                pdfmark_path = item_dir / "bookmarks.ps"
                output_path = item_dir / f"{stem}.bookmarked.pdf"
                preview_path = item_dir / f"{stem}.toc-preview.txt"

                input_path.write_bytes(item["input_bytes"])
                write_pdfmark(build_outline_tree(parse_structured_toc(structured_toc)), pdfmark_path)
                preview_path.write_text(preview_text, encoding="utf-8")

                results = []
                if optimize_before_bookmarks:
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
                        contract.optimized_size_bytes = optimized_path.stat().st_size
                else:
                    contract.optimized_size_bytes = input_path.stat().st_size

                if not results or results[-1].code == 0:
                    results.extend(apply_bookmarks(working_input_path, pdfmark_path, output_path))

                error_result = next((result for result in results if result.code != 0), None)
                if error_result is not None or not output_path.exists():
                    contract.final_status = "error"
                    contract.error_message = error_result.stderr if error_result else "Arquivo final nao foi gerado."
                    manifest.append(contract.to_dict())
                    archive.writestr(f"reports/{stem}.logs.txt", "\n\n".join(f"$ {result.cmd}\n{result.stdout}\n{result.stderr}" for result in results))
                    continue

                contract.output_size_bytes = output_path.stat().st_size
                contract.final_status = "completed"
                contract.error_message = ""
                manifest.append(contract.to_dict())

                archive.write(output_path, arcname=f"output/{output_path.name}")
                archive.write(preview_path, arcname=f"reports/{preview_path.name}")
                archive.writestr(f"reports/{stem}.raw-toc.txt", raw_toc)
                archive.writestr(f"reports/{stem}.structured-toc.txt", structured_toc)

            manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)
            archive.writestr("manifest.json", manifest_json)

            csv_buffer = io.StringIO()
            fieldnames = [
                "input_filename",
                "provider",
                "model",
                "validation_status",
                "bookmark_count",
                "input_size_bytes",
                "optimized_size_bytes",
                "output_size_bytes",
                "final_status",
                "error_message",
            ]
            writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
            writer.writeheader()
            for row in manifest:
                writer.writerow({field: row.get(field, "") for field in fieldnames})
            archive.writestr("summary.csv", csv_buffer.getvalue())

    bundle.seek(0)
    return bundle.getvalue(), manifest


def render_item_review(item: dict[str, object], provider: str, model: str, api_key: str) -> None:
    contract: BatchItemContract = item["contract"]
    badge = f"{contract.validation_status} | {contract.final_status}"
    with st.expander(f"{contract.input_filename} - {badge}", expanded=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("Entrada", f"{contract.input_size_bytes / 1024 / 1024:.2f} MB")
        c2.metric("Marcadores", str(contract.bookmark_count))
        c3.metric("Status", contract.validation_status)

        if contract.error_message:
            st.warning(contract.error_message)

        if contract.candidate_summaries:
            st.caption("Candidatos detectados")
            for summary in contract.candidate_summaries:
                st.write(f"- {summary}")

        st.text_area(
            "Bloco bruto detectado",
            key=f"raw_toc_{contract.item_id}",
            height=220,
        )
        if st.button("Reprocessar com LLM", key=f"rerun_{contract.item_id}", use_container_width=True):
            if not api_key:
                st.error("Preencha a API key antes de reprocessar com o LLM.")
            elif not model:
                st.error("Defina um modelo valido antes de reprocessar com o LLM.")
            else:
                rerun_item_with_llm(contract.item_id, provider, model, api_key)
                st.rerun()

        st.text_area(
            "Sumario estruturado (editavel)",
            key=f"structured_toc_{contract.item_id}",
            height=260,
        )

        if item["contract"].validation_status == "valid":
            st.code(item.get("preview_text", ""), language="text")
        else:
            st.info("Corrija o sumario estruturado ate o status ficar `valid`.")


def build_ui() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption("Lote de PDFs com deteccao automatica do sumario + LLM + bookmarks + otimizacao")
    st.info(
        "Fluxo da V2:\n"
        "1. Envie varios PDFs.\n"
        "2. Escolha OpenAI ou Gemini e informe sua API key.\n"
        "3. Clique em `Detectar e organizar sumarios`.\n"
        "4. Revise o bloco bruto detectado e o sumario estruturado de cada arquivo.\n"
        "5. Ajuste manualmente quando necessario ou reprocese com o LLM.\n"
        "6. Clique em `Gerar lote final` para baixar um ZIP com os PDFs finais e relatorios."
    )

    with st.sidebar:
        st.subheader("Dependencias")
        for dep in ("gs", "qpdf"):
            if shutil.which(dep):
                st.success(f"{dep}: ok")
            else:
                st.error(f"{dep}: ausente")

        st.divider()
        st.subheader("LLM")
        provider = st.selectbox("Provedor", ["OpenAI", "Gemini"])
        st.text_input(
            "API key",
            type="password",
            key=f"api_key_{provider.lower()}",
            help="A chave fica apenas na sessao atual do Streamlit.",
        )
        selected_model = st.selectbox("Modelo", COMMON_MODELS[provider], index=0)
        custom_model = ""
        if selected_model == "Custom":
            custom_model = st.text_input("Modelo customizado", value="")
        model = get_model(provider, selected_model, custom_model)
        max_pages = st.slider("Paginas iniciais para buscar sumario", 5, 40, 20, 1)

        st.divider()
        st.subheader("Otimizacao")
        optimize_before_bookmarks = st.checkbox("Otimizar PDF antes de aplicar bookmarks", value=True)
        color_resolution = st.slider("Color DPI", 72, 300, 150, 1)
        gray_resolution = st.slider("Gray DPI", 72, 300, 150, 1)
        jpeg_quality = st.slider("JPEG quality", 40, 95, 80, 1)

    uploaded_pdfs = st.file_uploader("Upload dos PDFs", type=["pdf"], accept_multiple_files=True)

    col_detect, col_build = st.columns(2)
    detect_clicked = col_detect.button("Detectar e organizar sumarios", type="primary", use_container_width=True)
    build_clicked = col_build.button("Gerar lote final", use_container_width=True)

    if detect_clicked:
        if not uploaded_pdfs:
            st.error("Envie pelo menos um PDF.")
            return
        api_key = get_api_key(provider)
        if not api_key:
            st.error("Preencha a API key para usar o LLM.")
            return
        if not model:
            st.error("Defina um modelo valido.")
            return

        items: list[dict[str, object]] = []
        with st.status("Detectando sumarios e chamando o LLM...", expanded=True) as status:
            for uploaded_pdf in uploaded_pdfs:
                file_bytes = uploaded_pdf.getvalue()
                status.write(f"Processando `{uploaded_pdf.name}`...")
                try:
                    item = detect_and_structure_item(
                        filename=uploaded_pdf.name,
                        file_bytes=file_bytes,
                        provider=provider,
                        model=model,
                        api_key=api_key,
                        max_pages=max_pages,
                    )
                    items.append(item)
                    st.session_state[f"raw_toc_{item['contract'].item_id}"] = item.get("raw_toc", "")
                    st.session_state[f"structured_toc_{item['contract'].item_id}"] = item.get("structured_toc_text", "")
                except Exception as exc:
                    contract = BatchItemContract(
                        item_id=make_item_id(uploaded_pdf.name, file_bytes),
                        input_filename=uploaded_pdf.name,
                        provider=provider,
                        model=model,
                        input_size_bytes=len(file_bytes),
                        validation_status="manual review required",
                        final_status="error",
                        error_message=str(exc),
                        manual_review_required=True,
                    )
                    items.append(
                        {
                            "contract": contract,
                            "input_bytes": file_bytes,
                            "raw_toc": "",
                            "structured_toc_text": "",
                            "preview_text": "",
                        }
                    )
            st.session_state[ITEMS_STATE_KEY] = items
            status.update(label="Analise concluida", state="complete", expanded=False)

    items = sync_items_from_ui() if st.session_state.get(ITEMS_STATE_KEY) else []

    if items:
        st.subheader("Revisao por arquivo")
        for item in items:
            render_item_review(item, provider, model, get_api_key(provider))

    if build_clicked:
        items = sync_items_from_ui()
        missing = [dep for dep in ("gs", "qpdf") if not shutil.which(dep)]
        if missing:
            st.error(f"Dependencias ausentes: {', '.join(missing)}")
            return
        if not items:
            st.error("Nenhum item analisado. Rode a deteccao antes de gerar o lote.")
            return

        with st.status("Gerando lote final...", expanded=True) as status:
            status.write("Aplicando otimizacao e bookmarks item a item...")
            zip_bytes, manifest = build_zip_bundle(
                items=items,
                optimize_before_bookmarks=optimize_before_bookmarks,
                color_resolution=color_resolution,
                gray_resolution=gray_resolution,
                jpeg_quality=jpeg_quality,
            )
            status.update(label="Lote final concluido", state="complete", expanded=False)

        completed = sum(1 for row in manifest if row["final_status"] == "completed")
        ready = sum(1 for row in manifest if row["validation_status"] == "valid")

        st.subheader("Resultado do lote")
        c1, c2, c3 = st.columns(3)
        c1.metric("Arquivos analisados", str(len(manifest)))
        c2.metric("Prontos para gerar", str(ready))
        c3.metric("Concluidos", str(completed))

        st.download_button(
            label="Baixar ZIP do lote",
            data=zip_bytes,
            file_name="pdf-bookmarks-batch.zip",
            mime="application/zip",
            use_container_width=True,
        )


if __name__ == "__main__":
    build_ui()
