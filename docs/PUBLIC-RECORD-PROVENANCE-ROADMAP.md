# Public Record Provenance Roadmap (U.S.)

This artifact tracks the active U.S. implementation roadmap and the policy-only EU scaffold used to open follow-on country issues.

## Scope

- Build an authoritative, ever-growing U.S. public-record attorney dataset.
- Keep only listings with strict, per-record official source URLs.
- Remove listings when the official record can no longer be verified.

## Current Baseline (March 10, 2026)

- Active strict listings: `58`
- States with strict listings: `AK`, `AL`, `AR`, `AZ`, `CA`, `CO`, `CT`, `DE`, `GA`, `IA`, `ID`, `IL`, `IN`, `KS`, `MA`, `MD`, `ME`, `MI`, `MN`, `MO`, `MS`, `MT`, `NC`, `ND`, `NE`, `NH`, `NJ`, `NM`, `OH`, `RI`, `SC`, `SD`, `TN`, `TX`, `UT`, `WA`
- Other U.S. rows were removed because they only pointed to generic directory pages (not the exact record URL).

## Strict Provenance Rules

- `source_url` must point to the exact public record URL for that listing.
- `source_url` must be on the expected official state authority domain.
- Generic source pages are rejected.
- Synthetic markers (`listing=` query/fragment hacks) are rejected.
- Chambers/private rankings are rejected as authoritative sources.

## State Adapter Strategy

- Discovery/additions must come from explicit state adapters only.
- All 50 states now have explicit adapter entries in discovery code.
- Each adapter must:
  - query the official state authority source
  - resolve an exact per-record URL
  - emit normalized listing rows that pass strict validation
- Until a state-specific extractor is implemented, that state's adapter remains a no-op.

## 50-State Matrix

| State | Official Authority (Domain)                                                    | Adapter Method                                                | Status                                                                       |
| ----- | ------------------------------------------------------------------------------ | ------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| AK    | Alaska Bar Association public directory (`alaskabar.org`)                      | Seeded exact directory profile URL + strict validation        | Seed adapter implemented                                                     |
| AL    | Alabama State Bar public directory (`alabar.org`)                              | Seeded exact directory profile URL + strict validation        | Seed adapter implemented                                                     |
| AR    | Arkansas Bar Association public directory (`arkbar.com`)                       | Seeded exact directory profile URL + strict validation        | Seed adapter implemented                                                     |
| AZ    | State Bar of Arizona public directory (`azbar.org`)                            | Seeded exact directory profile URL + strict validation        | Seed adapter implemented                                                     |
| CA    | State Bar of California attorney profile (`calbar.ca.gov`)                     | Direct attorney detail URL extraction                         | Seed adapter implemented                                                     |
| CO    | Colorado Bar Association public directory (`cobar.org`)                        | Seeded exact directory profile URL + strict validation        | Seed adapter implemented                                                     |
| CT    | Connecticut Bar Association public directory (`ctbar.org`)                     | Seeded exact directory profile URL + strict validation        | Seed adapter implemented                                                     |
| DE    | Delaware Courts published opinions (`courts.delaware.gov`)                     | Seeded exact opinion URL + strict validation                  | Seed adapter implemented; directory-grade attorney records still blocked     |
| FL    | The Florida Bar public directory (`floridabar.org`)                            | Seeded exact directory profile URL + strict validation        | Seed adapter implemented                                                     |
| GA    | State Bar of Georgia speaker profiles (`gabar.org`)                            | Seeded exact speaker profile URL + strict validation          | Seed adapter implemented; public member-directory detail URLs still blocked  |
| HI    | Hawaii State Bar Association attorney recognition records (`hsba.org`)         | Seeded exact recognition record URL + strict validation       | Seed adapter implemented; public member-directory detail URLs still blocked  |
| IA    | Iowa State Bar Association public directory (`iowabar.org`)                    | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| ID    | Idaho State Bar public directory (`isb.idaho.gov`)                             | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| IL    | Illinois ARDC attorney registration records (`iardc.org`)                      | Printable profile URL seed + strict validation                | Adapter implemented                                                          |
| IN    | Indiana State Bar public directory (`inbar.org`)                               | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| KS    | Kansas Judicial Branch attorney records (`kscourts.gov`)                       | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| KY    | Kentucky Bar Association public directory (`kybar.org`)                        | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| LA    | Louisiana Attorney Disciplinary Board attorney records (`ladb.org`)            | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| MA    | Massachusetts BBO attorney records (`massbbo.org`)                             | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| MD    | Maryland Courts attorney discipline records (`courts.state.md.us`)             | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| ME    | Maine Board of Overseers of the Bar public directory (`mainebar.org`)          | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| MI    | State Bar of Michigan public directory (`michbar.org`)                         | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| MN    | Minnesota Courts attorney records (`mncourts.gov`)                             | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| MO    | The Missouri Bar public directory (`mobar.org`)                                | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| MS    | The Mississippi Bar public directory (`msbar.org`)                             | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| MT    | State Bar of Montana public directory (`montanabar.org`)                       | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| NC    | North Carolina State Bar public directory (`ncbar.gov`)                        | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| ND    | North Dakota Court System attorney directory (`ndcourts.gov`)                  | Direct attorney profile URL seed + strict validation          | Seed adapter implemented                                                     |
| NE    | Nebraska Judicial Branch case records (`supremecourt.nebraska.gov`)            | Seeded exact case-call URL + strict validation                | Seed adapter implemented; directory-grade attorney detail URLs still blocked |
| NH    | New Hampshire Bar Association CLE speaker profiles (`nhbar.org`)               | Seeded exact event speaker URL + strict validation            | Seed adapter implemented; public member-directory detail URLs still blocked  |
| NJ    | NJ Courts attorney certification records (`njcourts.gov`)                      | Seeded exact certification record URL + strict validation     | Seed adapter implemented; public attorney-search detail URLs still blocked   |
| NM    | State Bar of New Mexico public directory (`sbnm.org`)                          | Direct member profile URL seed + strict validation            | Seed adapter implemented                                                     |
| NV    | State Bar of Nevada public directory (`nvbar.org`)                             | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| NY    | New York Courts attorney directory (`courts.state.ny.us`)                      | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| OH    | Supreme Court of Ohio attorney directory (`supremecourt.ohio.gov`)             | Fragment profile URL + API-backed record mapping              | Seed adapter implemented                                                     |
| OK    | Oklahoma Bar Association public directory (`okbar.org`)                        | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| OR    | Oregon State Bar public directory (`osbar.org`)                                | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| PA    | Pennsylvania Disciplinary Board attorney directory (`padisciplinaryboard.org`) | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| RI    | Rhode Island Judiciary attorney records (`courts.ri.gov`)                      | Seeded exact attorney-resource roster URL + strict validation | Seed adapter implemented                                                     |
| SC    | South Carolina Bar public directory (`scbar.org`)                              | Seeded exact section roster URL + strict validation           | Seed adapter implemented                                                     |
| SD    | State Bar of South Dakota public directory (`statebarofsouthdakota.com`)       | Seeded exact program roster URL + strict validation           | Seed adapter implemented                                                     |
| TN    | Tennessee Board of Professional Responsibility attorney records (`tbpr.org`)   | Direct attorney detail URL seed + strict validation           | Seed adapter implemented                                                     |
| TX    | State Bar of Texas public directory (`texasbar.com`)                           | Seeded exact member profile URL + strict validation           | Seed adapter implemented                                                     |
| UT    | Utah Courts public legal directory (`utcourts.gov`)                            | Seeded exact committee roster URL + strict validation         | Seed adapter implemented                                                     |
| VA    | Virginia State Bar public directory (`vsb.org`)                                | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| VT    | Vermont Bar Association public directory (`vtbar.org`)                         | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| WA    | Washington State Bar Association legal directory (`mywsba.org`)                | Direct profile URL seed + strict validation                   | Adapter implemented                                                          |
| WI    | State Bar of Wisconsin public directory (`wisbar.org`)                         | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| WV    | West Virginia State Bar public directory (`wvbar.org`)                         | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |
| WY    | Wyoming State Bar public directory (`wyomingbar.org`)                          | Official search flow -> resolve exact result URL              | Adapter scaffolded                                                           |

## Execution Order

1. Implement one adapter at a time and gate merges on strict source validation.
2. Prioritize states with machine-friendly search/results and stable URLs.
3. Add adapter tests:
   - returns direct official record URLs
   - does not emit generic source pages
   - state/domain policy remains enforced
4. Replace scaffolded no-op adapters with state-specific extractors until all 50 states are fully implemented.

## Interrogation Checklist (Per State)

- Does the authority publish firm-level records, attorney-level records, or both?
- Is there a stable canonical result URL per record?
- Are anti-bot controls/captcha present?
- Is an official API/feed available?
- Can provenance be captured reproducibly without private sources?

## EU Phase 0A (Policy-Only Scaffold)

### Scope

- Mirror the U.S. roadmap format before any EU adapter work starts.
- Keep this section policy-only until a country-specific issue validates the source shape.
- Use the EU target set already defined in code: `Austria`, `Belgium`, `Finland`, `France`, `Germany`, `Italy`, `Luxembourg`, `Netherlands`, `Portugal`, `Spain`, `Sweden`.

### Evidence Snapshot (March 14, 2026)

- Public-search availability below reflects an evidence review completed on March 14, 2026.
- Primary evidence came from official national bar/council pages and the European e-Justice "Find a lawyer" provider list (last updated July 1, 2025).
- No EU discovery adapters are implemented yet. Every row below is planning state only.

### Status Definitions

- `Candidate`: official authority and public search are visible enough to open a country implementation issue.
- `Blocked`: no single authoritative country-level source is confirmed yet, or the source shape is split in a way that prevents a safe first adapter.
- `Deferred`: the official authority is known, but the exact search/detail URL policy still needs manual source validation before adapter work starts.

### 11-Country Matrix

| Country     | Official Authority                                                          | Expected Official Domain(s)                            | Public Search                                | Record-Specific URL | Likely Adapter Method                                                              | Status    | Notes                                                                                                 |
| ----------- | --------------------------------------------------------------------------- | ------------------------------------------------------ | -------------------------------------------- | ------------------- | ---------------------------------------------------------------------------------- | --------- | ----------------------------------------------------------------------------------------------------- |
| Austria     | Austrian Bar / Austrian Lawyers (`Osterreichischer Rechtsanwaltskammertag`) | `rechtsanwaelte.at`, `oerak.at`, `service.oerak.at`    | Yes                                          | Yes                 | Official search flow -> resolve exact result URL                                   | Candidate | Official directory and attorney detail pages were both observed on official bar domains.              |
| Belgium     | Split official bars: `AVOCATS.BE` and `Orde van Vlaamse Balies`             | `avocats.be`, `advocaat.be`                            | Yes, but split                               | Unknown             | Federated bar search -> resolve exact result URL per authority                     | Blocked   | No single country-level authority/domain is confirmed for nationwide coverage yet.                    |
| Finland     | Finnish Bar Association                                                     | `asianajajat.fi`                                       | Yes                                          | Unknown             | Official search flow -> validate exact result URL                                  | Deferred  | Public "Find an attorney" flow exists, but the canonical profile URL shape still needs confirmation.  |
| France      | `Conseil national des barreaux`                                             | `avocat.fr`                                            | Yes                                          | Unknown             | Official search flow -> resolve exact result URL                                   | Candidate | National official directory is public; stable record URL policy still needs country issue validation. |
| Germany     | Federal Bar / BRAK Nationwide Register of Lawyers                           | `brak.de`, `rechtsanwaltsregister.org`                 | Yes                                          | Unknown             | Official register search -> resolve exact result URL                               | Candidate | Nationwide official register is public and suitable for a first country issue.                        |
| Italy       | National Bar Council / `Consiglio Nazionale Forense`                        | `consiglionazionaleforense.it`                         | Yes, but entrypoint still needs pinning      | Unknown             | Official register search -> resolve exact result URL or federated local-bar lookup | Deferred  | Official authority is known, but the stable public query surface still needs confirmation.            |
| Luxembourg  | Luxembourg Bar Association                                                  | `barreau.lu`                                           | Yes                                          | Unknown             | Official search flow -> resolve exact result URL                                   | Deferred  | Public bar-register participation is visible, but country-level completeness still needs review.      |
| Netherlands | Netherlands Bar                                                             | `advocatenorde.nl`, `zoekeenadvocaat.advocatenorde.nl` | Yes                                          | Unknown             | Official search flow -> resolve exact result URL                                   | Candidate | National official lawyer search is public and appears viable for follow-on validation.                |
| Portugal    | Portuguese Bar Association / `Ordem dos Advogados`                          | `portal.oa.pt`                                         | No authoritative public search confirmed yet | No                  | Manual authority review before adapter work                                        | Blocked   | Official authority is identified, but no public lawyer-search/detail source is documented here yet.   |
| Spain       | General Council of Spanish Lawyers                                          | `abogacia.es`                                          | Yes                                          | Unknown             | Official census search -> resolve exact result URL                                 | Candidate | National official lawyer census is public; exact per-record URL behavior still needs validation.      |
| Sweden      | Swedish Bar Association                                                     | `advokatsamfundet.se`                                  | Yes                                          | Unknown             | Official search flow -> validate exact result URL                                  | Deferred  | Public member search exists, but canonical detail URLs still need country issue review.               |

### EU Execution Order

1. Open country issues only from rows marked `Candidate` or `Deferred`.
2. In each country issue, confirm the exact allowed domain set and whether direct per-record URLs are stable.
3. Promote `Deferred` rows to `Candidate` only after a country issue captures the exact search/detail URL shape.
4. Leave `Blocked` rows policy-only until a single authoritative public source, or a maintainer-approved federated policy, is documented.
