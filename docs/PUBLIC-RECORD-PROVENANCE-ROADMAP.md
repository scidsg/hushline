# Public Record Provenance Roadmap (U.S.)

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
