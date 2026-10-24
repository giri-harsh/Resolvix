"""THE CONTRACT (§7.3). Nothing under core/ may name a domain concept — everything
that gives meaning to a queue, a slot, or a prompt lives behind this interface,
loaded from domains/<pack>/.
"""
from dataclasses import dataclass, field
from typing import Callable, Protocol

from resolvix.core.retrieval.protocol import Retriever
from resolvix.core.routing.calibration import CostWeights
from resolvix.core.routing.policy import Thresholds


@dataclass
class TurnContext:
    session_id: str
    slots: dict
    turns: list


@dataclass
class Queue:
    key: str
    label: str
    sla_minutes: int
    destinations: list[str]
    transferable: bool = False


@dataclass
class SlotSpec:
    key: str
    prompt: str
    required: bool = True
    pattern: str | None = None


@dataclass
class VoiceConfig:
    greeting: str
    asr_language: str = "en-US"
    tts_voice: str | None = None
    # Domain-specific terms Deepgram's nova-3 keyterm prompting should bias
    # toward (§ASR fix — "hall ticket" misheard as "my whole"). Empty list is a
    # valid, harmless default for a pack that doesn't need it — keeps this
    # feature domain-swappable rather than campus-specific.
    asr_keyterms: list[str] = field(default_factory=list)


@dataclass
class LabelledUtterance:
    text: str
    vector: dict


@dataclass
class DomainTool:
    name: str
    description: str
    fn: Callable
    required_slots: list[str] = field(default_factory=list)


class DomainPack(Protocol):
    name: str

    def system_prompt(self, ctx: TurnContext) -> str: ...
    def clarify_prompt(self, options: str) -> str: ...
    def confirm_prompt(self, queue_label: str, details: str) -> str: ...
    def tools(self) -> list[DomainTool]: ...
    def retriever(self) -> Retriever: ...
    def exemplars(self) -> list[LabelledUtterance]: ...
    def thresholds(self) -> Thresholds: ...
    def costs(self) -> CostWeights: ...
    def queues(self) -> dict[str, Queue]: ...
    def identity_fields(self) -> list[SlotSpec]: ...
    def voice_config(self) -> VoiceConfig: ...
