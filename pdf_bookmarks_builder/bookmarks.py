from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


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
class OutlineEntry:
    level: str
    title: str
    page: int


@dataclass
class OutlineNode:
    level: str
    title: str
    page: int
    children: list["OutlineNode"] = field(default_factory=list)


def parse_structured_toc(raw_text: str) -> list[OutlineEntry]:
    entries: list[OutlineEntry] = []
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
        entries.append(OutlineEntry(level=level, title=title, page=int(page_str)))
    if not entries:
        raise ValueError("Nenhuma entrada valida encontrada.")
    return entries


def build_outline_tree(entries: list[OutlineEntry]) -> list[OutlineNode]:
    roots: list[OutlineNode] = []
    current_unit: OutlineNode | None = None
    current_chapter: OutlineNode | None = None

    for entry in entries:
        node = OutlineNode(level=entry.level, title=entry.title, page=entry.page)
        if entry.level == "UNIT":
            roots.append(node)
            current_unit = node
            current_chapter = None
        elif entry.level == "CHAPTER":
            if current_unit is None:
                roots.append(node)
            else:
                current_unit.children.append(node)
            current_chapter = node
        else:
            if current_chapter is not None:
                current_chapter.children.append(node)
            elif current_unit is not None:
                current_unit.children.append(node)
            else:
                roots.append(node)
    return roots


def to_utf16_hex(text: str) -> str:
    return "FEFF" + text.encode("utf-16-be").hex().upper()


def write_pdfmark(tree: list[OutlineNode], output_path: Path) -> None:
    with output_path.open("w", encoding="ascii") as ps_file:
        def emit(node: OutlineNode) -> None:
            line = f"[ /Title <{to_utf16_hex(node.title)}> /Page {node.page}"
            if node.children:
                line += f" /Count {len(node.children)}"
            line += " /OUT pdfmark\n"
            ps_file.write(line)
            for child in node.children:
                emit(child)

        for root in tree:
            emit(root)


def render_tree_text(tree: list[OutlineNode]) -> str:
    lines: list[str] = []

    def walk(node: OutlineNode, depth: int = 0) -> None:
        lines.append(f"{'  ' * depth}- p{node.page} {node.title}")
        for child in node.children:
            walk(child, depth + 1)

    for root in tree:
        walk(root)
    return "\n".join(lines)


def count_nodes(tree: list[OutlineNode]) -> int:
    total = 0
    stack = list(tree)
    while stack:
        node = stack.pop()
        total += 1
        stack.extend(node.children)
    return total
