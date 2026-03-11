from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass

from pypdf import PdfReader


DOT_LEADER_RE = re.compile(r".+\.{2,}\s*\d{1,4}$")
TRAILING_PAGE_RE = re.compile(r".+\s\d{1,4}$")
HEADING_RE = re.compile(r"\b(unidade|cap[ií]tulo|sec[aã]o|sum[aá]rio)\b", re.IGNORECASE)


@dataclass
class TOCCandidate:
    start_page: int
    end_page: int
    score: float
    raw_text: str
    reasons: list[str]


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def clean_page_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if re.fullmatch(r"\d{1,4}", line):
            continue
        lines.append(line)
    return lines


def extract_front_matter_text(pdf_bytes: bytes, max_pages: int = 20) -> list[tuple[int, str]]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    extracted: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages[:max_pages], start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        extracted.append((index, text))
    return extracted


def _score_page(lines: list[str]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    joined = "\n".join(lines)
    normalized = normalize_text(joined)

    if "sumario" in normalized:
        score += 8
        reasons.append("titulo sumario")

    heading_hits = 0
    dotted_hits = 0
    numbered_hits = 0
    increasing_hits = 0
    previous_page: int | None = None

    for line in lines:
        normalized_line = normalize_text(line)
        if HEADING_RE.search(normalized_line):
            heading_hits += 1
        if DOT_LEADER_RE.match(line):
            dotted_hits += 1
        elif TRAILING_PAGE_RE.match(line):
            numbered_hits += 1

        match = re.search(r"(\d{1,4})$", line)
        if match:
            current_page = int(match.group(1))
            if previous_page is None or current_page >= previous_page:
                increasing_hits += 1
            previous_page = current_page

    score += dotted_hits * 1.4
    score += numbered_hits * 0.6
    score += heading_hits * 1.2
    score += min(increasing_hits, 8) * 0.5

    if dotted_hits:
        reasons.append(f"{dotted_hits} linhas com leaders")
    if numbered_hits:
        reasons.append(f"{numbered_hits} linhas numeradas")
    if heading_hits:
        reasons.append(f"{heading_hits} headings")
    if increasing_hits >= 3:
        reasons.append("paginas crescentes")

    return score, reasons


def detect_toc_candidates(text_by_page: list[tuple[int, str]]) -> list[TOCCandidate]:
    page_payloads: list[tuple[int, list[str], float, list[str]]] = []
    for page_number, text in text_by_page:
        lines = clean_page_lines(text)
        if not lines:
            continue
        score, reasons = _score_page(lines)
        if score > 0:
            page_payloads.append((page_number, lines, score, reasons))

    if not page_payloads:
        return []

    candidates: list[TOCCandidate] = []
    for start_index in range(len(page_payloads)):
        combined_lines: list[str] = []
        combined_score = 0.0
        combined_reasons: list[str] = []
        start_page = page_payloads[start_index][0]
        end_page = start_page

        for end_index in range(start_index, min(start_index + 4, len(page_payloads))):
            page_number, lines, page_score, reasons = page_payloads[end_index]
            if end_index > start_index and page_number != page_payloads[end_index - 1][0] + 1:
                break
            combined_lines.extend(lines)
            combined_score += page_score
            combined_reasons.extend(reasons)
            end_page = page_number

            raw_text = "\n".join(combined_lines).strip()
            if raw_text:
                candidates.append(
                    TOCCandidate(
                        start_page=start_page,
                        end_page=end_page,
                        score=combined_score + min(len(combined_lines), 60) * 0.08,
                        raw_text=raw_text,
                        reasons=sorted(set(combined_reasons)),
                    )
                )

    candidates.sort(key=lambda item: (item.score, len(item.raw_text)), reverse=True)

    unique: list[TOCCandidate] = []
    seen_ranges: set[tuple[int, int]] = set()
    for candidate in candidates:
        key = (candidate.start_page, candidate.end_page)
        if key in seen_ranges:
            continue
        seen_ranges.add(key)
        unique.append(candidate)
    return unique[:5]
