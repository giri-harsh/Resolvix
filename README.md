<div align="center">

<img src="https://user-images.githubusercontent.com/placeholder/typing-svg-banner.gif" width="0" height="0" alt="" />

# 🧠 RESOLVIX

### *The AI That Answers Before You Even Finish Dialing.*

**Grounded. Disciplined. Engineered for real operations.**

<br/>

[![Launch Live Demo](https://img.shields.io/badge/🚀_LAUNCH_LIVE_DEMO-Click_Here-4A9EFF?style=for-the-badge&labelColor=0B0F1A)](https://giri-harsh.github.io/Saathi-AI-Seva/frontend/index.html)

<br/>

[![Node.js](https://img.shields.io/badge/Node.js-%3E%3D18-339933?style=for-the-badge&logo=node.js&logoColor=white)](https://nodejs.org)
[![Twilio](https://img.shields.io/badge/Twilio-Voice%20%7C%20SMS%20%7C%20WhatsApp-F22F46?style=for-the-badge&logo=twilio&logoColor=white)](https://www.twilio.com)
[![RAG](https://img.shields.io/badge/RAG-HNSW%20%2F%20ChromaDB-4B8BBE?style=for-the-badge)](#-ai-pipeline)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](./LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=for-the-badge)](#-contributing)

<br/>

---

## 🎬 See It In Action

<div align="center">

<img src="./assets/1.gif" width="720" alt="Resolvix live demo" />

<br/>
<sub><i>Confident → Partial → Escalate, back to back — captured live from the running prototype.</i></sub>

</div>

---

## ⚡ The 15-Second Pitch

Campus and enterprise helplines answer the same handful of questions **hundreds of times a day**. Resolvix is the AI that picks up the phone, retrieves a grounded answer from approved documents, and — when it isn't sure — **says so, asks the right follow-up, and hands off a ticket a human can act on in seconds.**

Not a chatbot wearing a phone costume. **It *is* the phone line, engineered to think.**

<div align="center">

| 🎙️ Voice-first | 📚 Grounded | 🚦 Disciplined | 🎫 Actionable | 📊 Self-improving |
|:---:|:---:|:---:|:---:|:---:|
| No app, no login | Every answer cited | 3-tier confidence | Pre-filled tickets | Logs its own gaps |

</div>

---

## 🏆 Engineered For Impact

We **spearheaded** a shift away from reactive, human-only helplines toward a grounded, disciplined AI front line — **pioneering** a three-tier confidence system that most hackathon-grade voice agents never attempt.

| Metric | Target |
|---|---|
| 🎯 Retrieval precision (RAG grounding) | **≥ 92%** |
| 📉 Projected reduction in repeat call volume reaching staff | **30–40%** |
| ⚡ End-to-end retrieval latency (query → chunks) | **~180ms** |
| 🗣️ Full voice-response latency (STT → LLM → TTS) | **~900ms–1.2s** |
| ⏱️ Staff ticket-response initiation (vs. same-day baseline) | **~12 minutes** |
| 💰 Total infrastructure cost | **$0 — every service on a free tier** |
| 🏫 Addressable institutions (India, if scaled) | **1,000+ colleges · low tens of millions of students** |

> *Targets reflect engineered design specs based on the current architecture — labeled honestly as projections, not yet production-verified at scale.*

---

## 🧬 How Resolvix Thinks

```mermaid
flowchart TD
    A[📞 Caller dials in] --> B[Resolvix answers directly]
    B --> C[🎙️ Speech-to-Text]
    C --> D["🔍 HNSW-indexed vector retrieval<br/>(ChromaDB, per-department)"]
    D --> E["🧠 Single structured LLM call<br/>Gemini Flash / Groq"]
    E -->|Confident| F[✅ Speak answer + citation]
    E -->|Partial| G[⚠️ Speak answer + flag doubt + offer human]
    E -->|Escalate| H[🔴 Ask 2–3 clarifying questions]
    H --> I[🏷️ Tag urgency]
    I --> J{Department reachable?}
    J -->|Yes| K[☎️ Live transfer]
    J -->|No| L[🎫 Structured ticket → staff]
    G -->|Accepts| H
```

**Fail-safes engineered in from day one** — no matching documents → escalate, never fabricate a citation. LLM/API timeout → clean fallback response. The call **never dead-ends.**

---

## 🛠️ Tech Stack

<div align="center">

![Node.js](https://img.shields.io/badge/Node.js-339933?style=flat-square&logo=node.js&logoColor=white)
![Express](https://img.shields.io/badge/Express-000000?style=flat-square&logo=express&logoColor=white)
![Twilio](https://img.shields.io/badge/Twilio-F22F46?style=flat-square&logo=twilio&logoColor=white)
![React](https://img.shields.io/badge/React-61DAFB?style=flat-square&logo=react&logoColor=black)
![Gemini](https://img.shields.io/badge/Gemini_Flash-8E75B2?style=flat-square&logo=googlegemini&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-F55036?style=flat-square)
![ChromaDB](https://img.shields.io/badge/ChromaDB-HNSW-4B8BBE?style=flat-square)
![AWS Polly](https://img.shields.io/badge/AWS_Polly-FF9900?style=flat-square&logo=amazonaws&logoColor=white)

</div>

| Layer | Choice | Why |
|---|---|---|
| Backend | Node.js + Express | Extends an already-working codebase — extending beats rewriting |
| Telephony | Twilio (Voice/SMS/WhatsApp) | Already integrated, free-tier friendly |
| TTS | AWS Polly | Zero new provider risk |
| Vector store | ChromaDB, **HNSW**-indexed | Free, local, sub-200ms retrieval at hackathon scale |
| LLM | Gemini Flash / Groq | Generous free tier, low-latency structured inference |
| Frontend | React | Extends existing dashboard prototype |
| Storage | Flat JSON | Labeled simplification — not a production claim |

---

## ✅ Prerequisites

- **Node.js** `>= 18`
- A **Twilio** account (free trial works)
- **Gemini** or **Groq** API key
- (Optional) **AWS** account for Polly TTS
- **ngrok** or a public HTTPS URL for local Twilio webhooks

## 🚀 Quick Start

```bash
git clone https://github.com/your-org/resolvix.git
cd resolvix/backend
npm install
cp .env.example .env    # fill in your API keys
npm run demo            # spins up server + public tunnel
```

Ingest your own documents into the vector store:

```bash
node rag/ingest.js --dir ./data/documents
```
## 🚀 Demo :)
<img src="./assets/resolvix-demo.gif" width="720" alt="Resolvix live demo" />
---

<div align="center">

<img src="https://media.giphy.com/media/QBd2kLB5qDmysEXre9/giphy.gif" width="260" alt="robot waving hello, fun eye-catching gif" />

<br/>
<sub>Resolvix, probably, the moment it resolves your ticket correctly.</sub>

</div>

---

## 🗺️ Roadmap

- [x] Inbound RAG helpline with cited answers
- [x] Three-tier confidence + clarifying questions
- [x] Structured tickets · SMS/WhatsApp to staff
- [x] Caller history · insights panel · live transfer
- [ ] SLA-based auto-escalation for un-actioned tickets
- [ ] Cross-document contradiction detection (**AST**-level document diffing under evaluation)
- [ ] Proactive outbound deadline reminders
- [ ] Real authentication & role-based dashboard
- [ ] Multi-college self-serve onboarding at **ten million+** student scale

---

## 🤝 Contributing

Issues and PRs welcome. For larger changes (new LLM provider, schema changes, new department logic), open an issue first so we can align on approach.

## 📄 License

MIT — see [`LICENSE`](./LICENSE).

## ✉️ Contact

Built by **Harsh Giri** — Founder, Resolvix
📧 your.email@example.com · 🔗 [LinkedIn](https://linkedin.com/in/giri-harsh) · 🐙 [GitHub](https://github.com/giri-harsh)

<div align="center">

### 📞 One call. No wait. No repeated questions.

⭐ *If Resolvix is useful or interesting, consider starring the repo.*

</div>
