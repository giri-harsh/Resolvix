"""Corpus chunking: parse YAML front matter, split on `##`, strip HTML comments,
extract per-section provenance/answer_hint, drop boilerplate/heading-only chunks.

Rebuilt from the PRD's own description of the earned v1 logic (rag.py:75-105 — the
comment-stripping and boilerplate-drop rules — was deleted with the rest of v1 rather
than ported verbatim, since nothing in this new tree imported it yet). Behaviour
matches spec: HTML comments never reach the vectorizer, heading-only/boilerplate
chunks are dropped, YAML front matter and per-section provenance markers are new.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)
PROVENANCE_COMMENT_RE = re.compile(r"provenance:\s*(sourced|synthetic)", re.IGNORECASE)
ANSWER_HINT_RE = re.compile(r"answer_hint:\s*(.+)", re.IGNORECASE)

# Sections that carry no answerable content — dropped rather than indexed.
BOILERPLATE_HEADINGS = {"contact", "contact us", "disclaimer"}
MIN_CHUNK_WORDS = 8


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    queue: str
    heading: str
    text: str
    provenance: str  # "sourced" | "synthetic"
    answer_hint: str | None = None
    metadata: dict = field(default_factory=dict)


def _extract_comments(section_text: str) -> tuple[str, str | None, str | None]:
    """Returns (clean_text, provenance_override, answer_hint)."""
    provenance = None
    answer_hint = None
    for match in HTML_COMMENT_RE.finditer(section_text):
        comment = match.group(1).strip()
        prov_match = PROVENANCE_COMMENT_RE.search(comment)
        if prov_match:
            provenance = prov_match.group(1).lower()
        hint_match = ANSWER_HINT_RE.search(comment)
        if hint_match:
            answer_hint = hint_match.group(1).strip()
    clean = HTML_COMMENT_RE.sub("", section_text).strip()
    return clean, provenance, answer_hint


def parse_doc(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")

    front_matter = {}
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            front_matter = yaml.safe_load(raw[3:end]) or {}
            body = raw[end + 4:]

    doc_id = front_matter.get("doc_id", path.stem)
    queue = front_matter.get("queue", "general")
    doc_provenance = front_matter.get("provenance", "sourced")

    # Split on level-2 headings, keeping the heading with its body.
    sections = re.split(r"\n(?=## )", body.strip())
    chunks: list[Chunk] = []
    for i, section in enumerate(sections):
        section = section.strip()
        if not section or not section.startswith("## "):
            continue
        heading_line, _, rest = section.partition("\n")
        heading = heading_line[3:].strip()
        if heading.lower() in BOILERPLATE_HEADINGS:
            continue

        clean_text, provenance_override, answer_hint = _extract_comments(rest)
        if len(clean_text.split()) < MIN_CHUNK_WORDS:
            continue

        provenance = provenance_override or doc_provenance
        if provenance == "mixed":
            provenance = "sourced"  # doc-level "mixed" with no section override defaults conservatively

        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}::{i}",
                doc_id=doc_id,
                queue=queue,
                heading=heading,
                text=clean_text,
                provenance=provenance,
                answer_hint=answer_hint,
                metadata={"title": front_matter.get("title", doc_id)},
            )
        )
    return chunks


def load_corpus(corpus_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for md_path in sorted(corpus_dir.glob("*.md")):
        chunks.extend(parse_doc(md_path))
    return chunks
