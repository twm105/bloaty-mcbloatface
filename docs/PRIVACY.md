# Data Practices & Privacy

This document describes how Bloaty McBloatface handles user data. It is a POC-level summary, not a legal privacy policy.

---

## What Data Is Collected

| Category | Examples | Sensitivity |
|----------|----------|-------------|
| **Account** | Email, hashed password | PII |
| **Meal data** | Uploaded photos, AI-extracted ingredients, meal names, timestamps | Health-adjacent |
| **Symptom data** | Symptom tags, severity scores, start/end times, AI elaboration text | Health / sensitive |
| **Diagnosis results** | Trigger correlations, confidence scores, medical citations | Health / sensitive |
| **Session data** | Session tokens, IP address, user agent | Technical |
| **AI usage logs** | Model, token counts, estimated cost (no prompt content stored) | Operational |

## Where Data Is Stored

- **PostgreSQL** on EC2 (encrypted EBS volume) — all structured data
- **EBS bind mount** (`/opt/bloaty/uploads`) — uploaded meal images
- **S3** — automated daily backups (database dumps + upload snapshots)
- **Redis** — ephemeral only (message queue, SSE pub/sub); no persistent user data

All infrastructure runs in a single AWS region. No CDN or edge caching of user data.

## Access Model

- **Invite-only registration** — new accounts require an admin-generated invite link
- **Single admin** — one admin user manages invites and account resets
- **No public access** — all routes require authentication
- **Ownership isolation** — every database query filters by `user_id`; users cannot access each other's data

## AI Processing

Meal images and text (ingredient names, symptom descriptions, historical data for diagnosis) are sent to the **Anthropic Claude API** for analysis. Review [Anthropic's data usage policy](https://www.anthropic.com/privacy) for their retention and training practices.

- Passwords, emails, session tokens, and user IDs are **never** sent to the AI
- AI responses are validated through Pydantic schemas before storage or display
- See [SECURITY.md](SECURITY.md) § AI/LLM Security for full details

## Retention & Deletion

- Users can delete individual meals and symptoms through the UI
- Full data export (GDPR-style) is planned but not yet implemented
- Account deletion requires admin action (no self-service yet)
- Database backups are retained in S3 with lifecycle policies TBD

## Analytics & Tracking

- **No third-party analytics** (no Google Analytics, no tracking pixels)
- **No cookies beyond the session cookie** (HttpOnly, SameSite=Lax)
- **No data sharing** with third parties (except Anthropic API as described above)
- CDN resources (htmx, Alpine.js, Chart.js) are loaded with SRI integrity hashes
