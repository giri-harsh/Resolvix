# Resolvix — team starter package

Start here:
1. Read `RESOLVIX_FINAL_PRD.md` (sections 1–3 together at H0, ~45 min).
2. Install and test the frozen contracts in YOUR environment:
   ```
   pip install -e contracts/python pytest pyyaml
   pytest contracts/tests -q        # must be green before you write any code
   ```
3. Open your prompt in `prompts/` and paste it into your coding agent at the repo root:
   - Member A → `prompts/MEMBER_A_voice_runtime.md`  (owns `voice-runtime/`, `integration/`, root files)
   - Member B → `prompts/MEMBER_B_brain.md`          (owns `brain/`)
   - Member C → `prompts/MEMBER_C_ops_dashboard.md`  (owns `ops/`)
4. Never edit another member's directory. Contract changes need all three members (see PRD §6).

Contents
- `contracts/python/resolvix_contracts/` — Pydantic models, Brain protocol, speech/idempotency helpers (v1.0.0, frozen)
- `contracts/jsonschema/` — JSON Schemas generated from the models (C generates TS types from these)
- `contracts/openapi/` — ops-api (C) and voice-runtime (A) HTTP contracts
- `contracts/fixtures/` — 9 brain event streams, ops payloads, Agora request + expected SSE
- `contracts/config/` — departments (frozen), urgency rules (B), SMS templates (C)
- `contracts/kb/` — SAMPLE knowledge base (placeholder data, not real college data)
