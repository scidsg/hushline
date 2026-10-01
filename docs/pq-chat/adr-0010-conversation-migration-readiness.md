# ADR-0010: PQ Chat Conversation Migration

Status: **Implemented for integration; validation and review pending**

Date: 2026-09-30

Decision gate: G11 of `scidsg/hushline#2365`

Issue: `scidsg/hushline#2406`

## Context

The earlier readiness-only decision for `#2376` recorded G9 and G10 as
implementation blockers. The maintainer's 2026-09-27 correction superseded
that sequencing: build the complete integration with synthetic data, then
bring the finished revision and evidence for approval. Protected delivery and
credential lifecycle implementations are now present on the integration
branch, so this ADR records the implemented migration contract rather than the
historical blocker.

Human product, accessibility, cryptographic, and independent security review
remain release gates. This record does not approve merge to `main` or launch.

## Decision

Eligible authenticated two-party conversations automatically select
`HL-PQCHAT-1` for the next send without an opt-in, setup page, additional
credential, pairing step, confirmation, or prompt. Eligibility is derived from
server-held account identity, current archive epoch, and signed active device
memberships whose authenticated capabilities and archive suite select the
same protocol.

The first complete protected write and the conversation's minimum protocol
version advance in one database transaction under a row lock. The minimum is
monotonic. Every classical writer checks the stored minimum independently of
request negotiation fields or feature settings, so stale clients and stripped
fields cannot append classical ciphertext after migration.

Readers remain version-aware. Legacy and protected messages share one ordered
timeline, while each record's stored protocol version controls its visible
description. Protected status never relabels legacy history, and the UI states
that authentication remains classical.

Failed, paused, or update-needed sends retain the composer content. A durable
protected outbox operation becomes read-only while retry is pending so edited
text cannot be confused with the exact-byte retry. The composer clears and
reports success only after the protected storage acknowledgement.

## Rollout Controls

The deployment exposes three controls:

- `PQ_CHAT_AUTO_MIGRATION_ENABLED` enables or disables new automatic
  conversation migrations.
- `PQ_CHAT_MIGRATION_ROLLOUT_PERCENT` selects a deterministic conversation
  cohort from 0 through 100 percent.
- `PQ_CHAT_PROTECTED_WRITES_PAUSED` is the kill switch for new protected
  writes.

Automatic migration and its cohort default to disabled/zero until an approved
deployment explicitly enables a staged population. This keeps the finished
integration reviewable without treating code completion as launch approval.

The first two controls affect only conversations whose stored minimum has not
advanced. Disabling them cannot lower an existing minimum or reopen the
classical writer. The kill switch permits acknowledgement recovery for an
already committed idempotent operation, rejects new protected commits, and
does not affect protected or legacy reads.

## Security Invariants

1. Signed current device capabilities, not client assertions alone, determine
   migration eligibility.
2. The protected write and floor transition are atomic; neither can become
   visible alone.
3. Conversation minimum versions only increase.
4. Missing, stripped, stale, forged, or conflicting negotiation never permits
   a below-floor write.
5. Feature controls never reactivate classical writes in upgraded threads.
6. Each message retains its own version and security description.
7. Protected readers stay available while writes are paused.
8. Draft clearing and success UI require a committed acknowledgement.
9. Telemetry and errors contain no plaintext, draft, private key, protocol
   state, archive secret, token, or exact ciphertext.

## Implementation Evidence

- `hushline/routes/message.py`: authenticated eligibility, deterministic
  cohorting, atomic floor enforcement, old-writer refusal, kill switch, and
  mixed-version payloads.
- `hushline/templates/conversation.html`: accessible conversation policy,
  update-needed/pause states, and truthful per-message descriptions.
- `assets/js/chat-key-lifecycle.js`: automatic protected selection, policy
  refresh, draft-safe exact-operation retry, and acknowledgement-only success.
- `hushline/config.py` and Docker Compose configurations: parsed rollout and
  pause controls available to supported deployments.
- `tests/test_pq_message_storage.py`: automatic migration, flag disablement,
  stripped negotiation, protected/classical mixed history, idempotent
  acknowledgement recovery, kill-switch read preservation, and monotonic
  floor coverage.
- `tests/test_frontend_compat.py`: client downgrade, polling, retry, draft, and
  status contract coverage.

## Pending Release Evidence

The implementation is ready for integration validation, not release approval.
The following remain pending at the exact final revision:

- Chromium, Firefox, and WebKit normal/private-mode runs, including stale
  cached assets and supported-client recovery;
- keyboard and screen-reader checks, accessibility 100, and performance at
  least 95;
- synthetic click/prompt counts, rollout/rollback drills, and capture-free
  Playwright artifacts;
- full CI, dependency audits, CodeQL, and workflow security checks; and
- product/accessibility, full-stack security, and independent security review
  with remediation and retest.

An application rollback is permitted only to a revision that retains both the
protected reader and authoritative below-floor write refusal. No approval,
merge, or production launch is asserted by this ADR.
