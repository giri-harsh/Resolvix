"""Composition-root config. No domain vocabulary lives here — only transport/infra knobs."""
import os

from dotenv import load_dotenv

load_dotenv()

AGORA_APP_ID = os.environ.get("AGORA_APP_ID", "")
AGORA_APP_CERTIFICATE = os.environ.get("AGORA_APP_CERTIFICATE", "")
AGORA_CUSTOMER_ID = os.environ.get("AGORA_CUSTOMER_ID", "")
AGORA_CUSTOMER_SECRET = os.environ.get("AGORA_CUSTOMER_SECRET", "")
AGORA_LLM_SHARED_SECRET = os.environ.get("AGORA_LLM_SHARED_SECRET", "")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# llama-3.1-8b-instant (the PRD's original pick) isn't on this account's model list —
# verified live against /v1/models. openai/gpt-oss-20b is the fastest of the four
# available text models that actually produces clean output: qwen/qwen3.6-27b is a
# reasoning model whose hidden-reasoning phase burns the whole token budget before
# any visible content appears (tested empty at 300 tokens), and groq/compound-mini
# is slower (internal tool-routing overhead). gpt-oss-20b is ALSO a reasoning model —
# `reasoning_format: hidden` (passed via extra_body, not a typed SDK kwarg on this
# installed groq==0.11.0) keeps the <G>/<NG> control-token contract intact, but the
# hidden reasoning still costs real wall-clock time before the first visible token
# (~950ms-1.3s observed live, well past the PRD's 600ms TTFT budget) — a genuine
# latency regression from the model swap, not a bug, and not fixable without a
# faster non-reasoning model becoming available on this account.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")

# TTS: canopylabs/orpheus-v1-english via ConvoAI's "openai" vendor + base_url
# override — playai-tts (the PRD's pick) isn't on this account either. Verified live:
# Groq's /v1/audio/speech endpoint returns 400 model_terms_required for Orpheus until
# the org admin accepts its terms at console.groq.com — code is ready, unverified
# end-to-end until that happens.
GROQ_TTS_BASE_URL = os.environ.get("GROQ_TTS_BASE_URL", "https://api.groq.com/openai/v1")
TTS_MODEL = os.environ.get("TTS_MODEL", "canopylabs/orpheus-v1-english")
# Valid Orpheus voices per a live 400 response: autumn, diana, hannah, austin,
# daniel, troy. "tara" (a playai-tts voice name) was wrong — verified live.
TTS_VOICE = os.environ.get("TTS_VOICE", "autumn")

# ASR: Deepgram, not Agora's own managed "ares" vendor — verified live that ares
# fails outright on this account regardless of language (tested en-IN and en-US,
# both silently dead: agent stays RUNNING but never publishes audio, confirmed via
# Agora's own console log: "ASR module.error_occurred, vendor: ares"). Deepgram's
# ConvoAI vendor page documents both BYOK and a custom `url` field, unlike ASR's
# "openai" vendor which is Realtime-API-shaped and has no such escape hatch.
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
DEEPGRAM_URL = os.environ.get("DEEPGRAM_URL", "wss://api.deepgram.com/v1/listen")
# nova-3 over nova-2: Deepgram's current-generation model, marketed as a strict
# upgrade (faster and more accurate) — no head-to-head latency figure found in
# either Agora's or Deepgram's docs to confirm this quantitatively.
DEEPGRAM_MODEL = os.environ.get("DEEPGRAM_MODEL", "nova-3")

# Public HTTPS base URL this server is reachable at (ngrok/Render/etc) — ConvoAI must
# be able to reach {PUBLIC_BASE_URL}/v1/chat/completions from the internet.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")

AGENT_JOIN_GRACE_MS = int(os.environ.get("AGENT_JOIN_GRACE_MS", "1500"))

# Which domains/ pack is active for this process (PRD Non-Goal: one pack per process).
DEFAULT_DOMAIN = os.environ.get("RESOLVIX_DOMAIN", "campus_akgec")

TOTAL_ANSWER_DEADLINE_MS = int(os.environ.get("TOTAL_ANSWER_DEADLINE_MS", "1800"))
RETRIEVAL_DEADLINE_MS = int(os.environ.get("RETRIEVAL_DEADLINE_MS", "250"))
CLASSIFIER_DEADLINE_MS = int(os.environ.get("CLASSIFIER_DEADLINE_MS", "200"))
TRANSFER_TIMEOUT_MS = int(os.environ.get("TRANSFER_TIMEOUT_MS", "20000"))

# Notify adapters — all optional, all no-op safely if unconfigured (§8.3 degradation ladder).
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "resolvix@example.com")

# Vobiz WhatsApp Business API (pivot v3 §7) — needs a real Vobiz account + a
# provisioned WhatsApp Business Account, not obtainable from here. No-ops
# safely if unset, same as every other notify adapter.
VOBIZ_AUTH_ID = os.environ.get("VOBIZ_AUTH_ID", "")
VOBIZ_AUTH_TOKEN = os.environ.get("VOBIZ_AUTH_TOKEN", "")
VOBIZ_CHANNEL_ID = os.environ.get("VOBIZ_CHANNEL_ID", "")
VOBIZ_WABA_ID = os.environ.get("VOBIZ_WABA_ID", "")

# DEMO SAFETY NET — deliberate hackathon-only escape hatch, not real functionality.
# When on, every call gets one hardcoded line pushed straight to TTS a fixed delay
# after join, bypassing ASR/retrieval/LLM entirely so the demo has one guaranteed-
# correct answer regardless of live pipeline state. Toggle off after the demo by
# unsetting/false-ing DEMO_HARDCODE_MODE — no code changes needed either way.
DEMO_HARDCODE_MODE = os.environ.get("DEMO_HARDCODE_MODE", "false").strip().lower() == "true"
DEMO_HARDCODE_DELAY_S = float(os.environ.get("DEMO_HARDCODE_DELAY_S", "5"))
DEMO_HARDCODE_TEXT = os.environ.get(
    "DEMO_HARDCODE_TEXT",
    "For a no water supply issue, call the BWSSB 24x7 toll-free helpline at 1916. "
    "You can also reach them at 080-2223-8888 or send a WhatsApp message to 8762228888.",
)

# AGORA-MANAGED PIPELINE TOGGLE (event-credits experiment, urgent/time-boxed) — off
# by default so the proven Groq/Deepgram path in agora_client.py is completely
# untouched unless explicitly opted in. When true, join() builds asr/llm/tts blocks
# with credential_mode: "managed" per Agora's documented shape (docs.agora.io
# /en/conversational-ai/rest-api/agent/join) instead of pointing at our own shim/
# Groq/Deepgram accounts. KNOWN TRADEOFF, confirmed with the user before wiring
# this: managed LLM calls OpenAI directly, bypassing our /v1/chat/completions shim
# entirely — no RAG, no <G>/<NG> grounding, no escalation, no ticket creation.
# Managed ASR still uses vendor "deepgram" (not Agora's separate "ares" vendor,
# which was live-confirmed dead earlier tonight — this is a different code path).
USE_AGORA_MANAGED = os.environ.get("USE_AGORA_MANAGED", "false").strip().lower() == "true"
AGORA_MANAGED_LLM_MODEL = os.environ.get("AGORA_MANAGED_LLM_MODEL", "gpt-4o-mini")
AGORA_MANAGED_TTS_VOICE = os.environ.get("AGORA_MANAGED_TTS_VOICE", "English_captivating_female1")
