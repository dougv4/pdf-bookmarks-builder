from .bookmarks import (
    LLM_PROMPT_TEMPLATE,
    OutlineEntry,
    OutlineNode,
    build_outline_tree,
    count_nodes,
    parse_structured_toc,
    render_tree_text,
    write_pdfmark,
)
from .batch_models import BatchItemContract
from .llm_clients import GeminiClient, OpenAIClient, ProviderClient
from .pdf_ops import CmdResult, apply_bookmarks, file_size_text, optimize_pdf, require_binary
try:
    from .toc_detection import TOCCandidate, detect_toc_candidates, extract_front_matter_text
except ModuleNotFoundError:  # pragma: no cover - optional until pypdf is installed
    TOCCandidate = None
    detect_toc_candidates = None
    extract_front_matter_text = None

__all__ = [
    "BatchItemContract",
    "LLM_PROMPT_TEMPLATE",
    "OutlineEntry",
    "OutlineNode",
    "CmdResult",
    "ProviderClient",
    "OpenAIClient",
    "GeminiClient",
    "TOCCandidate",
    "apply_bookmarks",
    "build_outline_tree",
    "count_nodes",
    "detect_toc_candidates",
    "extract_front_matter_text",
    "file_size_text",
    "optimize_pdf",
    "parse_structured_toc",
    "render_tree_text",
    "require_binary",
    "write_pdfmark",
]
