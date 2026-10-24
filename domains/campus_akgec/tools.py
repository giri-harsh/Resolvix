"""Domain-specific tools beyond the core ticket/transfer/retrieval machinery — the
only domain Python (§7.2). Empty for now: nothing in the campus pack's flow needs a
tool beyond core's built-in ticket creation and transfer, so an empty list here beats
inventing a tool call nothing exercises. Add entries as real needs surface (e.g. a
hostel-room-availability lookup) — the DomainTool contract is in core/domain/protocol.py.
"""
from resolvix.core.domain.protocol import DomainTool

TOOLS: list[DomainTool] = []
