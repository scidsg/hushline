# AI Code Policy for Hush Line

This policy defines when Hush Line work can be AI-first versus human-first, based on risk and operational impact. Use it as a gating checklist before implementation: if a task touches funding, production infrastructure, authentication, payments, or other high-risk surfaces, human ownership is required; low-risk work can be AI-led with a qualified human operator. For example, an engineer should lead engineering tasks, and a designer should lead design tasks.

## Decision Matrix

| # | Decision / Stage | Risk | Ownership Mode | Human Lead | AI Usage Guidance (Codex 5.3+ or equivalent) | Human Required When... | Recommended Outcome |
|---|---|---|---|---|---|---|---|
| 1 | Build a prototype that solves a real problem | Low | AI-First | Any | Use AI agents to rapidly scaffold, iterate, and test assumptions | Scope becomes unclear, or domain constraints are legal/safety-critical | Produce a working prototype and clear problem statement |
| 2 | Are you seeking funding? | Very High | Human-First | Any | AI optional, but should be used minimally for better results | Any fundraising strategy, investor materials, diligence, financial modeling, legal structure, and commitments | Funding work is human-owned end-to-end |
| 3 | Is it a service with a database? | High | Human-First | Engineer | AI can draft schema changes and migration scripts, only with human engineer oversight | Any service with a real database | Human engineer owns review, rollback validation, and production execution |
| 4 | Is it a service users can sign up for? | High | Human-First | Engineer | AI optional, only with human engineer oversight | Any real signup/authentication flow or release automation | Hire a human to implement and own authentication and CI/CD |
| 5 | Does it handle financial data/payments (for example Stripe)? | Very High | Human-First | Engineer | AI optional, only with human engineer oversight | Any real financial-data or payment handling | Hire a human to implement and own the feature end-to-end |
| 6 | Does it add/remove env vars, or impact auth, privacy, or security? | High | Human-First | Engineer | AI optional, only with human engineer oversight | Any change touching secrets, access control, privacy boundaries, or security posture | Human engineer owns implementation, review, and release |
| 7 | Is it a DB migration with no auth/env/security impact and a tested rollback plan? | High | Human-First | Engineer | AI can generate migration scripts and test plans under human engineer oversight | Any migration that could affect data integrity, availability, or rollback safety | Human engineer must review, test, and execute migrations in production |
| 8 | Is it a large feature or refactor? | High | Human-First | Engineer | AI optional, only with human engineer oversight | Any broad change spanning multiple systems or high regression risk | Human engineer owns design, rollout plan, and release |
| 9 | Is it a visual design change based on a single person or small group's subjective taste? | Not eligible for AI | Human-First | Designer | Not applicable | Any user-facing visual direction choice based on subjective preference | Handled by human design/product owner |
| 10 | Is it documentation like this matrix (policy/process docs)? | Low | AI-First | Any | Strong fit for drafting, editing, and formatting with human review | Docs define policy, legal/compliance positions, or external commitments | AI drafts, human owner approves final language |

## Practical Policy

| Risk Tier | Typical Work | Delivery Model |
|---|---|---|
| Very High | Payments/financial data, sensitive compliance scope, strategy | Human-owned end-to-end |
| High | Databases, auth, CI/CD, production infra | Human-owned end-to-end |
| Medium | Productization artifacts, early architecture decisions | AI drafts, human decides |
| Low | UI tweaks, internal tools, non-sensitive logic, local apps | AI builds, human reviews |

## Funding Rule

All funding-related work is human-owned end-to-end. AI may be used only for internal brainstorming or research notes and should not be used to generate investor-facing deliverables without full human authorship and review.

## Operating Rules

1. Default to AI-first for low-risk work.
2. Require human ownership for anything high-risk or very high-risk.
3. Escalate from low-risk to high-risk immediately if scope starts touching DB, auth, env vars, or payments.
4. Keep auditability: document who approved risk classification and deployment path.

## A Note from Our Executive Director

> Coding models are improving fast, and Codex 5.3 CLI has genuinely impressed me. For a small tech nonprofit like ours, the question is: do we
use AI to ship high-quality iterations people need now, or build a backlog, apply for grants, wait six months, and maybe still not get
funded? In that case, product gaps remain, and that isn’t responsible product development. It’s also often outside our control. We’ve even
been told by funders not to apply because we haven’t managed millions of dollars in the prior fiscal year. Chicken or the egg? Even if we do
get funded, expecting users to wait half a year for improvements isn’t responsible product stewardship.
> 
> Practically, this is also about quality. At what point does it become product malpractice to ignore a technology that can improve output
quality and speed when used responsibly, in turn helping journalists and lawyers in the field, even when we can hire a team of humans?
>
> It’s also one reason we are monetizing: to stay financially independent and keep hiring real humans.
> 
> If you’d like to donate to Hush Line, go here: https://opencollective.com/hushline/contribute/hush-line-supporter-55786
