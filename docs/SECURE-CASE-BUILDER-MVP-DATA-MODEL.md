# Secure Case Builder MVP Data Model

Last updated: 2026-09-19

Linked issue: #2318

Parent epic: #2315

Prerequisite: #2326

## Status and Boundary

This document defines the minimum deterministic data model for the Secure Case Builder MVP. It is
an in-memory interface contract for later client implementation, not a database, persistence, or
export schema. It does not authorize product implementation or settle the unresolved labels,
prompts, or workflows recorded in the
[advisor and partner validation record](./SECURE-CASE-BUILDER-ADVISOR-VALIDATION.md).

The model inherits the [pre-build threat model](./SECURE-CASE-BUILDER-THREAT-MODEL.md): opening the
builder creates no case identifier or server record; editing is account-independent and produces
no network traffic; and all draft state exists only in the current page's JavaScript memory and
rendered document. It also follows the flat, optional structure in the
[information architecture prototype](./SECURE-CASE-BUILDER-INFORMATION-ARCHITECTURE.md).

The names in this document are internal structural names. They are not approved interface copy or
legal classifications. In particular, `claim`, `evidence`, `corroborator`, `gap`, `risk`, and the
relationship values remain subject to the human review gates in the prototype and validation
record.

## Model Conventions

- Fields without `?` in the typed contract are required. Fields with `?` are optional.
- `LocalId` values exist only to maintain references in one open page. They are unique within the
  workspace, are never placed in a URL or request, and are not case identifiers.
- `IsoDateTime` is a client-clock UTC timestamp in RFC 3339/ISO 8601 form. It is local audit
  metadata, not a trusted account of when an underlying event occurred.
- Array order is the user-controlled display order. The model does not duplicate order in numeric
  rank fields.
- All prose is user-entered plaintext. The model never derives credibility, completeness,
  severity, urgency, legal merit, or a recommended action from it.
- Optional values are omitted when unknown or unused. Empty strings are invalid; an empty array is
  valid and is distinct from a missing optional field.
- Every entity and relationship is mutable only in memory. Removing one deletes it rather than
  retaining a tombstone or content history.

## Normative Typed Contract

The following TypeScript-style interfaces are the normative logical contract. They describe data
shape and invariants without selecting a frontend framework or creating a serializable artifact.

```ts
type LocalId = string;
type IsoDateTime = string;

interface LocalAuditMetadata {
  createdAt: IsoDateTime;
  updatedAt: IsoDateTime;
  revision: number;
}

type MarkerState = "unmarked" | "marked";

interface UserReviewMarkers {
  uncertainty: MarkerState;
  sensitivity: MarkerState;
}

type ItemDisposition = "active" | "set_aside";

interface WorkspaceItem {
  id: LocalId;
  audit: LocalAuditMetadata;
  review: UserReviewMarkers;
  disposition: ItemDisposition;
}

interface Note extends WorkspaceItem {
  text: string;
}

interface Claim extends WorkspaceItem {
  statement: string;
}

type TemporalCertainty = "unmarked" | "approximate" | "uncertain";

interface TimelineEvent extends WorkspaceItem {
  description: string;
  when?: {
    text: string;
    certainty: TemporalCertainty;
  };
}

interface EvidenceItemMetadata extends WorkspaceItem {
  description: string;
  sourceDescription?: string;
}

interface Corroborator extends WorkspaceItem {
  description: string;
  context?: string;
}

type GapOrRiskKind = "gap" | "risk";

interface GapOrRisk extends WorkspaceItem {
  kind: GapOrRiskKind;
  description: string;
}

type LinkableEntityKind =
  | "note"
  | "claim"
  | "timeline_event"
  | "evidence_item"
  | "corroborator"
  | "gap_or_risk";

interface EntityRef {
  kind: LinkableEntityKind;
  id: LocalId;
}

type RelationshipKind =
  | "related"
  | "supports"
  | "conflicts"
  | "leaves_uncertain"
  | "corroborates"
  | "raises_gap_or_risk";

interface EntityRelationship {
  id: LocalId;
  audit: LocalAuditMetadata;
  from: EntityRef;
  to: EntityRef;
  kind: RelationshipKind;
  note?: string;
}

interface NarrativeBlock {
  id: LocalId;
  audit: LocalAuditMetadata;
  text: string;
  source?: EntityRef;
}

interface NarrativeDraft {
  id: LocalId;
  audit: LocalAuditMetadata;
  title?: string;
  intendedAudience?: string;
  blocks: NarrativeBlock[];
}

type NextAction =
  | "continue"
  | "pause_in_open_page"
  | "explore_recipient_separately"
  | "review_selected_chat_share"
  | "discard_and_leave";

interface SharePlan {
  audit: LocalAuditMetadata;
  nextAction?: NextAction;
  selectedItems: EntityRef[];
}

interface CaseWorkspace {
  schemaVersion: 1;
  audit: LocalAuditMetadata;
  notes: Note[];
  claims: Claim[];
  timelineEvents: TimelineEvent[];
  evidenceItems: EvidenceItemMetadata[];
  corroborators: Corroborator[];
  gapsAndRisks: GapOrRisk[];
  relationships: EntityRelationship[];
  narrativeDrafts: NarrativeDraft[];
  sharePlan: SharePlan;
}
```

`schemaVersion` versions this interface contract only. It must not be used to imply that workspace
state may be serialized, persisted, restored, or exported.

## Field Requirements

### Shared fields

- **`id` (required except on the workspace and share plan):** ephemeral reference key unique
  across all entity, relationship, narrative, and narrative-block collections in one workspace.
- **`audit` (required):** local creation/update metadata. It contains no actor, account, device,
  network, or recipient identifier.
- **`audit.createdAt` (required):** client-clock time at in-memory creation.
- **`audit.updatedAt` (required):** client-clock time of the latest in-memory mutation; initially
  equals `createdAt`.
- **`audit.revision` (required):** positive integer beginning at `1` and incremented once for each
  committed in-memory mutation.
- **`review.uncertainty` (required on workspace items):** a marker applied explicitly by the user;
  defaults to `unmarked`. It is never inferred or scored.
- **`review.sensitivity` (required on workspace items):** a marker that the user wants to review an
  item for possible identifying, excessive, or otherwise sensitive detail; defaults to
  `unmarked`. It is not a product risk assessment.
- **`disposition` (required on workspace items):** `active` or user-set `set_aside`; defaults to
  `active`. Set-aside content remains recoverable only while the page remains open.

The shared sensitivity marker deliberately records only marked/unmarked state. The reasons and
user-facing labels for marking sensitivity remain unresolved research and review questions; the
MVP model must not silently introduce a taxonomy or severity score.

### Workspace and content entities

- **`CaseWorkspace`:** requires `schemaVersion`, `audit`, every collection, and `sharePlan`; it has
  no optional fields. It has no workspace/case ID, owner, account, persistence, encryption,
  export, or completion field. Every collection starts empty.
- **`Note`:** requires the shared fields and `text`; it has no optional fields. It represents one
  user-authored piece. Splitting and merging are editing operations, not additional metadata.
- **`Claim`:** requires the shared fields and `statement`; it has no optional fields. Its presence
  does not assert truth, legal status, or credibility.
- **`TimelineEvent`:** requires the shared fields and `description`; `when` is optional. Collection
  order expresses relative order. `when.text` permits the user's own level of date precision and
  need not be a machine-parsable date.
- **`EvidenceItemMetadata`:** requires the shared fields and `description`; `sourceDescription` is
  optional. It describes material already available to the user and contains no file, attachment,
  URL fetch, authenticity, custody, or evidentiary score field.
- **`Corroborator`:** requires the shared fields and `description`; `context` is optional. It
  describes a person or source in the user's own terms and has no required legal name, contact
  detail, verification, outreach, or credibility field.
- **`GapOrRisk`:** requires the shared fields, `kind`, and `description`; it has no optional fields.
  `kind` does not represent severity, likelihood, completeness, urgency, or a recommendation to
  fill a gap.
- **`EntityRelationship`:** requires `id`, `audit`, `from`, `to`, and `kind`; `note` is optional.
  It is a directed assertion made by the user and is never inferred by the product.
- **`NarrativeDraft`:** requires `id`, `audit`, and `blocks`; `title` and `intendedAudience` are
  optional. An empty block list is valid. There is no generated, scored, or complete state.
- **`NarrativeBlock`:** requires `id`, `audit`, and `text`; `source` is optional. `source` records
  provenance to an existing workspace item. `text` is an independent working copy and does not
  mutate the source item. Array position is narrative order.
- **`SharePlan`:** requires `audit` and `selectedItems`; `nextAction` is optional. It starts with no
  action and no selected items and contains no recipient, account, conversation, confirmation,
  ciphertext, sent status, or delivery metadata.

## Relationship Model

Relationships are normalized in `CaseWorkspace.relationships` so content entities do not hold
duplicated adjacency lists. `from` is the entity making the user-authored assertion and `to` is
the entity it concerns. The following combinations are valid for the MVP:

- Any linkable entity may point to any different linkable entity with `related`.
- An evidence item may point to a claim or timeline event with `supports`, `conflicts`, or
  `leaves_uncertain`.
- A corroborator may point to a claim, timeline event, or evidence item with `corroborates`.
- A gap or risk may point to a claim, timeline event, evidence item, or corroborator with
  `raises_gap_or_risk`.

These values record only the user's chosen relationship. `supports` does not establish truth or
sufficiency; `conflicts` does not establish falsity; `corroborates` is not a credibility finding;
and `raises_gap_or_risk` does not predict harm or direct further evidence gathering. Final terms
and whether they appear in the product remain blocked on the reviews identified in the validation
record.

The relationship graph must satisfy all of these invariants:

1. Both references resolve to existing entities with the matching `kind`.
2. A relationship cannot point to itself.
3. Duplicate triples of `(from, to, kind)` are invalid.
4. Removing an entity removes every relationship, narrative-block source, and share selection that
   references it in the same in-memory update.
5. Setting an entity aside retains its relationships, but views must expose that endpoint as set
   aside rather than silently hiding the relationship.
6. Changing the order of a collection does not change relationships.
7. A relationship note is optional user text and receives no automated interpretation.

This graph directly supports claim-to-event and evidence-to-claim/event mapping, corroborator
links, and gap/risk links without embedding copies of content or creating hidden derived facts.

## State and Audit Rules

### Initial state

A new page constructs one `CaseWorkspace` with `schemaVersion: 1`, revision `1`, empty collections,
and a `SharePlan` whose `selectedItems` is empty and `nextAction` is absent. It does not create a
workspace ID, browser/server record, account association, or network request.

### Mutation

- Creating an entity gives it a fresh `LocalId`, equal `createdAt`/`updatedAt` values, and revision
  `1`; workspace `updatedAt` and revision also advance.
- Editing content or markers advances that object's `updatedAt` and revision and advances the
  workspace audit metadata.
- Reordering a collection advances the workspace audit metadata; the ordered objects themselves
  are unchanged.
- Adding, editing, or removing a relationship updates the relationship collection and workspace
  metadata only. It does not modify the linked content entities.
- Removing an entity performs the referential cleanup rule above as one in-memory mutation.
- Local audit data is current-state metadata, not an undo log. Undo/recovery behavior is still an
  unresolved workflow question and must not be inferred from `revision`.

Client timestamps and revision counters must never be presented as independently verified facts,
chain-of-custody records, or evidence of what occurred outside the builder.

### Narrative copies

Adding a source item to a narrative creates a `NarrativeBlock` containing a copy of the selected
text and an optional `source` reference. Later edits to either value do not propagate to the other.
If the source is removed, the reference is removed but the user-authored narrative text remains
until the user removes it.

### Share planning

`selectedItems` is an ordered, duplicate-free list of explicit user selections and is empty by
default. Selecting `review_selected_chat_share` does not send anything and does not add recipient
or account data to the workspace. A later, separately reviewed handoff may construct an ephemeral
preview from the selected items and pass only confirmed plaintext into the existing client-side
chat E2EE path. Cancellation or failure must leave no sent or persisted representation in this
model.

## MVP Storage Constraints

The data model may be instantiated only in current-page application memory and rendered UI state.
For the MVP:

- do not add SQLAlchemy models, migrations, database tables or columns, server sessions, draft
  APIs, administrative views, backups, or account export fields;
- do not serialize any part of the workspace into URLs, query strings, fragments, browser history
  state, form actions, cookies, Web Storage, IndexedDB, Cache Storage, service workers, autofill
  stores, logs, analytics, error reports, or telemetry;
- do not create autosave, recovery, synchronization, collaboration, import, download, print,
  clipboard, operating-system share, or generated-file behavior;
- do not accept or require file upload; evidence items contain descriptions only;
- do not send workspace state to Hush Line or a third party during editing;
- do not retain deleted content, revisions, relationship history, or tombstones; and
- on reload, navigation, close, discard, back/forward restoration, or a new route visit, restore no
  workspace state.

No arbitrary maximum item count or text length is selected in this model because stakeholder and
usability evidence is not available. A later implementation must define memory-safety bounds and
accessible error/recovery behavior through product, accessibility, and security review; it must
not silently truncate content, upload overflow, or treat a technical limit as a judgment about
case completeness.

Ordinary JavaScript memory is plaintext. The MVP must not add a workspace encryption key,
ciphertext field, or “encrypted at rest” claim: those would not protect content while the page is
open and would introduce unsupported key management. The only encryption boundary is the existing
account-chat E2EE implementation after an explicit, separately reviewed share confirmation.

## Deferred Fields and Separate Future Schemas

The following fields are deliberately absent. They must not be added to the MVP interfaces as
optional placeholders. Each category needs validated user evidence, an updated threat model, and
the named specialist reviews before it can receive a separate versioned schema.

- **Persistence and collaboration:** durable case/workspace ID, owner/account ID, collaborators,
  roles, permissions, saved revisions, tombstones, autosave, sync, recovery, retention, and deletion
  status. These create durable case-existence, identity, authorization, access-pattern, and recovery
  risks.
- **Draft encryption:** ciphertext or envelope, nonce, algorithm, key ID, wrapped key, key
  derivation, recovery material, and rotation version. A protected durable draft needs an
  end-to-end key and recovery design; adding metadata cannot make in-memory plaintext “encrypted
  at rest.”
- **Export and transfer:** export format/version, generated filename, file timestamps, print/PDF
  state, external destination, and transfer receipt. Exports create copies, metadata, previews,
  backups, and deletion behavior outside the current boundary.
- **File evidence:** blob or upload ID, original filename, MIME type, byte size, content hash,
  EXIF/media metadata, preview, object-storage key, malware result, and custody/authenticity fields.
  MVP evidence is description-only. File intake and metadata can identify people and need storage,
  scanning, and deletion controls.
- **AI or automated analysis:** prompt, model/provider/version, transcript, generated text,
  summary, embedding, classification, confidence, score, recommendation, and feedback. Remote or
  automated processing can expose plaintext, distort meaning, imply credibility or advice, and
  create new telemetry and retention paths.
- **Case law and legal analysis:** citation, jurisdiction, cause of action, legal element,
  precedent link, similarity/match score, eligibility, privilege, limitation date, and predicted
  outcome. The case-education component is deferred and must remain educational and independent of
  user case data if later approved.
- **Investigation and assessment:** verification status, evidence sufficiency, corroborator
  credibility, severity, likelihood, urgency, retaliation prediction, completeness, and tasks to
  gather more evidence. The builder must not investigate, score, predict, or encourage proactive
  evidence gathering.
- **Delivery and recipient state:** recipient/account/conversation ID, address, key material,
  encryption envelope, delivery state, read receipt, and message ID. These belong to the existing
  chat protocol after explicit confirmation, not to the local workspace.

Future work must version its own persistence, encryption, or export envelope instead of assuming
that `CaseWorkspace` is safe to stringify. A future migration must explicitly define validation,
forward/backward compatibility, authenticated-encryption coverage, key recovery, data minimization,
and deletion behavior before any durable copy exists.

## Validation Checklist for a Later Client Implementation

A later implementation of this contract must reject or safely repair state that violates these
rules before rendering or sharing:

- schema version is exactly `1`;
- every collection exists and contains only its declared entity type;
- all IDs are non-empty and globally unique within the workspace;
- audit timestamps are well-formed UTC timestamps and revisions are positive integers;
- required prose is non-empty after the user's explicit edit is committed;
- enum values match the closed sets above;
- relationship endpoints and kinds satisfy the relationship matrix and graph invariants;
- narrative and selection references resolve to allowed existing entities;
- selection and relationship triples contain no duplicates; and
- no undeclared persistence, file, AI, legal-analysis, recipient, encryption, or delivery fields
  are treated as supported MVP state.

This checklist is not authority to accept serialized input or restore a draft. It defines
deterministic behavior for state created within the same open page.

## Acceptance-Criteria Traceability

- **Required and optional fields:** the typed contract and field tables distinguish them directly.
- **Entity coverage:** workspace, note, claim, timeline event, evidence metadata, corroborator,
  gap/risk, narrative draft, and share plan/next action all have explicit interfaces.
- **Relationships:** the normalized graph, allowed-pair matrix, and referential rules define links
  among claims, events, evidence, corroborators, and gaps/risks.
- **Uncertainty, sensitivity, and risk:** user-controlled review markers, temporal certainty, and
  gap/risk entities represent them without automated scoring or conclusions.
- **Timestamps and audit metadata:** local audit metadata has deterministic create/update/revision
  rules without identities or retained histories.
- **MVP storage:** the storage section fixes the memory-only, no-file, no-server, no-restoration
  boundary.
- **Future constraints:** persistence/encryption/export requirements remain visible, while AI,
  file, case-law, collaboration, and delivery fields are explicitly separated from the MVP.

## Review Gate

This model may support implementation only after the existing source-stakeholder, product,
content, accessibility, legal, security/privacy, and account-chat protocol gates have recorded
accepted decisions. If those decisions change the categories, relationship terms, persistence,
export, file, or sharing boundary, update the threat model, user stories, information architecture,
this contract, and `docs/USE-CASES.md` as applicable before implementation.
