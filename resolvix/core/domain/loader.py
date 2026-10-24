"""Discovers and validates a domain pack at boot (§7.5's enforcement point 2, minus
the full test_domain_boundary.py — see tests/test_domain_boundary.py for that)."""
import importlib.util
from pathlib import Path

import yaml

from resolvix.core.domain.protocol import (
    DomainTool,
    LabelledUtterance,
    Queue,
    SlotSpec,
    TurnContext,
    VoiceConfig,
)
from resolvix.core.retrieval.hybrid_index import HybridIndex
from resolvix.core.routing.calibration import CostWeights
from resolvix.core.routing.policy import Thresholds

DOMAINS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "domains"


class YamlDomainPack:
    def __init__(self, pack_dir: Path):
        self._dir = pack_dir
        self.name = pack_dir.name

        with open(pack_dir / "domain.yaml", encoding="utf-8") as f:
            self._domain_cfg = yaml.safe_load(f)
        with open(pack_dir / "escalation.yaml", encoding="utf-8") as f:
            self._escalation_cfg = yaml.safe_load(f)
        exemplars_path = pack_dir / "exemplars.yaml"
        self._exemplars_cfg = []
        if exemplars_path.exists():
            with open(exemplars_path, encoding="utf-8") as f:
                self._exemplars_cfg = yaml.safe_load(f) or []

        self._retriever: HybridIndex | None = None
        self._tools_module = None

    def system_prompt(self, ctx: TurnContext) -> str:
        path = self._dir / "prompts" / "system.md"
        text = path.read_text(encoding="utf-8") if path.exists() else "You are a helpful assistant."
        return text.replace("{{session_id}}", ctx.session_id)

    def clarify_prompt(self, options: str) -> str:
        path = self._dir / "prompts" / "clarify.md"
        template = path.read_text(encoding="utf-8") if path.exists() else "Which of these did you mean: {options}?"
        return template.replace("{options}", options)

    def confirm_prompt(self, queue_label: str, details: str) -> str:
        path = self._dir / "prompts" / "confirm.md"
        default = "To confirm — {queue_label} issue, {details}. Should I file this?"
        template = path.read_text(encoding="utf-8") if path.exists() else default
        try:
            return template.format(queue_label=queue_label, details=details)
        except (KeyError, IndexError):
            # Pack's template used placeholder names this generic call doesn't
            # supply (e.g. {address}/{phone} instead of {details}) — fall back
            # to the generic form rather than crash a live confirm turn on a
            # template mismatch.
            return default.format(queue_label=queue_label, details=details)

    def classify_preamble(self) -> str:
        path = self._dir / "prompts" / "classify_preamble.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def tools(self) -> list[DomainTool]:
        if self._tools_module is None:
            tools_path = self._dir / "tools.py"
            if not tools_path.exists():
                self._tools_module = type("Empty", (), {"TOOLS": []})
            else:
                spec = importlib.util.spec_from_file_location(f"domains.{self.name}.tools", tools_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self._tools_module = module
        return getattr(self._tools_module, "TOOLS", [])

    def retriever(self) -> HybridIndex:
        if self._retriever is None:
            self._retriever = HybridIndex.from_corpus_dir(self._dir / "corpus")
        return self._retriever

    def exemplars(self) -> list[LabelledUtterance]:
        return [LabelledUtterance(text=e["text"], vector=e["vector"]) for e in self._exemplars_cfg]

    def thresholds(self) -> Thresholds:
        t = self._escalation_cfg.get("thresholds", {})
        return Thresholds(
            answer_floor=t.get("answer_floor", 0.55),
            human_floor=t.get("human_floor", 0.50),
            immediacy_hi=t.get("immediacy_hi", 0.62),
            max_clarify=t.get("max_clarify", 2),
        )

    def costs(self) -> CostWeights:
        c = self._escalation_cfg.get("costs", {})
        return CostWeights(
            c_false_transfer=c.get("c_false_transfer", 3.0),
            c_missed_transfer=c.get("c_missed_transfer", 5.0),
            c_wrong_answer=c.get("c_wrong_answer", 4.0),
            c_needless_ticket=c.get("c_needless_ticket", 1.0),
        )

    def synthetic_answerability_penalty(self) -> float:
        return self._escalation_cfg.get("synthetic_answerability_penalty", 0.25)

    def queues(self) -> dict[str, Queue]:
        raw = self._domain_cfg.get("queues", {})
        return {
            key: Queue(
                key=key,
                label=q.get("label", key),
                sla_minutes=q.get("sla_minutes", 480),
                destinations=q.get("destinations", ["console:"]),
                transferable=q.get("transferable", False),
            )
            for key, q in raw.items()
        }

    def identity_fields(self) -> list[SlotSpec]:
        raw = self._domain_cfg.get("identity_fields", [])
        return [SlotSpec(key=s["key"], prompt=s["prompt"], required=s.get("required", True), pattern=s.get("pattern")) for s in raw]

    def voice_config(self) -> VoiceConfig:
        v = self._domain_cfg.get("voice", {})
        return VoiceConfig(
            greeting=self._domain_cfg.get("greeting", ""),
            asr_language=v.get("asr_language", "en-US"),
            tts_voice=v.get("tts_voice"),
            asr_keyterms=v.get("asr_keyterms", []),
        )


def load_pack(name: str) -> YamlDomainPack:
    pack_dir = DOMAINS_ROOT / name
    if not pack_dir.exists():
        raise ValueError(f"unknown domain pack: {name}")
    return YamlDomainPack(pack_dir)


_PACK_CACHE: dict[str, YamlDomainPack] = {}


def get_pack(name: str) -> YamlDomainPack:
    if name not in _PACK_CACHE:
        _PACK_CACHE[name] = load_pack(name)
    return _PACK_CACHE[name]
