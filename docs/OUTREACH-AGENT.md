# Outreach Agent

Hush Line includes an admin-only outreach workspace at `Settings -> Outreach`.

## Purpose

The outreach workspace turns Hush Line's automated directory listings into a human-reviewed lead queue. It is designed to help the team:

- share what Hush Line is and who we are
- identify organizations and practices that appear to fit Hush Line
- draft an invitation to join without sending messages automatically

## Current Scope

This is intentionally narrow.

- Leads come from existing automated directory listings:
  - public record listings
  - GlobaLeaks listings
  - SecureDrop listings
- Hush Line generates a deterministic fit score and draft outreach copy.
- The UI exposes only public contact paths already associated with the listing.
- Outreach state is tracked so the team can work through the queue over time.
- The queue can be refreshed to reopen the current automated listing set for a new outreach pass without erasing prior completion history.
- Leads can also be marked as converted when an organization joins.
- Hush Line does not send outreach messages from this feature.

## Guardrails

- Human review is required before any outreach happens.
- Only public listing data is used.
- No private email discovery or hidden-contact scraping is performed.
- No suppression workflow or auto-follow-up exists yet.

## Follow-Up Ideas

- add do-not-contact tracking
- add manual status markers such as drafted / contacted / replied
- add CSV export for reviewed leads
- add organization-specific prompt tuning for outreach drafts
