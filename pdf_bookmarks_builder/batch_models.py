from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class BatchItemContract:
    item_id: str
    input_filename: str
    provider: str
    model: str
    detected_raw_toc: str = ""
    validation_status: str = "pending"
    structured_toc_text: str = ""
    bookmark_count: int = 0
    input_size_bytes: int = 0
    optimized_size_bytes: int = 0
    output_size_bytes: int = 0
    final_status: str = "pending"
    error_message: str = ""
    manual_review_required: bool = False
    candidate_summaries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
