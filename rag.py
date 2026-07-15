"""
Lightweight RAG over trusted campus docs.

Design choice for hackathon reliability: TF-IDF retrieval (scikit-learn) instead of
embedding-model downloads. No external model weights, no network dependency at
runtime, fast enough to run inside an IVR turn (<1s). Groq is used only for the
final answer *phrasing*, constrained to the retrieved chunk -- never asked to
answer from its own knowledge. This keeps hallucination risk low, which is the
whole point of "safe refusal when uncertain."
"""

import os
import glob
import re
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_extraction import text as _sk_text
from sklearn.metrics.pairwise import cosine_similarity

try:
    from groq import Groq
except ImportError:
    Groq = None

DOCS_DIR = os.path.join(os.path.dirname(__file__), "docs")

# Plain TF-IDF has no concept of word forms -- "visit" and "visited" are
# unrelated tokens to it, which silently drops genuinely relevant chunks
# from retrieval entirely (not just ranks them lower). A tiny suffix-based
# stemmer closes most of this gap without pulling in a heavy NLP dependency.
_STEM_SUFFIXES = ["ing", "edly", "ies", "ied", "ers", "er", "ed", "es", "s"]


def _stem(word: str) -> str:
    for suf in _STEM_SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            if suf == "ies":
                return word[:-3] + "y"
            return word[: -len(suf)]
    return word


def _stemming_tokenizer(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    return [_stem(t) for t in tokens if t not in _sk_text.ENGLISH_STOP_WORDS]

CATEGORY_FILES = {
    "1": "fee_structure.md",
    "2": "hostel_rules.md",
    "3": "exam_schedule.md",
    "4": "admissions.md",
    "5": "placements.md",
    "6": None,  # "other" -> search across everything, plus application_forms.md content
}

CATEGORY_LABELS = {
    "1": "Fees",
    "2": "Hostel",
    "3": "Exams",
    "4": "Admissions",
    "5": "Placements",
    "6": "General / Other",
}


@dataclass
class RagResult:
    answer: str
    confidence: float
    source_file: str
    chunk: str


def _chunk_markdown(text: str) -> list[str]:
    """Split a markdown doc into chunks by ## headings.

    Drops generic boilerplate sections (like a trailing "## Contact" pointer)
    that share vocabulary with many queries but never actually answer them --
    with pure TF-IDF these can outrank the real answer chunk.
    """
    parts = re.split(r"\n(?=## )", text)
    chunks = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if p.lower().startswith("## contact"):
            continue
        # Drop chunks that are just a heading line with no real body text --
        # e.g. a lone "# Doc Title" before the first "##" section. These are
        # short enough that TF-IDF concentrates term weight on them and lets
        # them outrank chunks that actually contain the answer.
        body = re.sub(r"^#{1,2}\s*.+", "", p, count=1).strip()
        if len(body.split()) < 4:
            continue
        chunks.append(p)
    return chunks


class DocIndex:
    def __init__(self):
        self.chunks: list[str] = []
        self.sources: list[str] = []
        self.vectorizer = TfidfVectorizer(tokenizer=_stemming_tokenizer, token_pattern=None)
        self.matrix = None
        self._build()

    def _build(self):
        for path in sorted(glob.glob(os.path.join(DOCS_DIR, "*.md"))):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            for chunk in _chunk_markdown(text):
                self.chunks.append(chunk)
                self.sources.append(os.path.basename(path))
        if self.chunks:
            self.matrix = self.vectorizer.fit_transform(self.chunks)

    def search(self, query: str, category: str | None = None, top_k: int = 3):
        if not self.chunks:
            return []

        allowed_file = CATEGORY_FILES.get(category) if category else None
        query_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(query_vec, self.matrix).flatten()

        ranked = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)

        results = []
        for i in ranked:
            if allowed_file and self.sources[i] != allowed_file:
                continue
            results.append((self.chunks[i], self.sources[i], float(sims[i])))
            if len(results) >= top_k:
                break
        return results


_index = DocIndex()

_groq_client = None
if Groq and os.getenv("GROQ_API_KEY"):
    _groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def _phrase_answer(query: str, chunks: list[str]) -> str:
    """Ask Groq to phrase a short spoken-friendly answer, strictly from the chunks."""
    combined = "\n\n---\n\n".join(chunks)

    if not _groq_client:
        # Fallback: strip the markdown heading and return the body directly
        # (still safe, just less polished than an LLM-phrased answer)
        body = re.sub(r"^##?\s*.+\n", "", chunks[0]).strip()
        return body

    system_prompt = (
        "You are a campus helpdesk voice assistant. Answer the student's question "
        "in 2-3 short spoken sentences, using ONLY the information in the provided "
        "document excerpts. Some excerpts may be irrelevant to the question -- ignore "
        "those and use only the one(s) that actually answer it. Do not add any "
        "information not present in the excerpts. If none of the excerpts actually "
        "answer the question, respond with the single word NOT_ANSWERABLE and "
        "nothing else -- no punctuation, no explanation."
    )
    user_prompt = f"Document excerpts:\n{combined}\n\nStudent question: {query}"

    try:
        completion = _groq_client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=200,
        )
        return completion.choices[0].message.content.strip()
    except Exception:
        # If Groq call fails for any reason, fall back to raw chunk rather than crash the call
        return chunk


def answer_query(query: str, category: str | None = None) -> RagResult:
    # IMPORTANT: the "safe refusal" guarantee depends on GROQ_API_KEY being set.
    # TF-IDF similarity alone is keyword overlap, not relevance -- a query like
    # "pet dog in my room" can score HIGHER against "Room Allotment" than a truly
    # relevant query scores against its correct chunk. No single threshold fixes
    # this because the irrelevant case can outrank the relevant one. Groq's
    # NOT_ANSWERABLE check is the actual relevance filter; retrieval score only
    # decides which chunks are worth showing it. Do not demo without a Groq key.
    if not _groq_client:
        print(
            "[RAG WARNING] GROQ_API_KEY not set -- running on retrieval score alone. "
            "Safe-refusal behavior is not reliable in this mode. Set GROQ_API_KEY before demoing."
        )
    threshold = float(os.getenv("RAG_CONFIDENCE_THRESHOLD", "0.18"))
    results = _index.search(query, category=category, top_k=4)

    if not results:
        return RagResult(answer="", confidence=0.0, source_file="", chunk="")

    top_chunk, top_source, top_score = results[0]

    if top_score < threshold:
        return RagResult(answer="", confidence=top_score, source_file=top_source, chunk=top_chunk)

    chunks = [c for c, _, _ in results]
    phrased = _phrase_answer(query, chunks)
    # Robust check: Groq occasionally adds trailing punctuation despite instructions
    # not to (e.g. "NOT_ANSWERABLE."), so match on a cleaned/prefix basis rather
    # than requiring byte-exact equality -- an exact-only check let that leak
    # through as a literal answer to the student, which is worse than useless.
    cleaned = phrased.strip().strip(".!\"'").upper()
    if cleaned == "NOT_ANSWERABLE" or cleaned.startswith("NOT_ANSWERABLE"):
        return RagResult(answer="", confidence=top_score, source_file=top_source, chunk=top_chunk)

    return RagResult(answer=phrased, confidence=top_score, source_file=top_source, chunk=top_chunk)
