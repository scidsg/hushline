# Public Record Provenance Roadmap (U.S.)

## Scope

- Build an authoritative, ever-growing U.S. public-record attorney dataset.
- Keep only listings with strict, per-record official source URLs.
- Remove listings when the official record can no longer be verified.

## Current Baseline (March 5, 2026)

- Active strict listings: `27`
- States with strict listings: `CA`, `IL`, `OH`, `TN`, `WA`
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

| State | Official Authority (Domain)                                                    | Adapter Method                                      | Status                   |
| ----- | ------------------------------------------------------------------------------ | --------------------------------------------------- | ------------------------ |
| AK    | Alaska Bar Association public directory (`alaskabar.org`)                      | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| AL    | Alabama State Bar public directory (`alabar.org`)                              | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| AR    | Arkansas Bar Association public directory (`arkbar.com`)                       | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| AZ    | State Bar of Arizona public directory (`azbar.org`)                            | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| CA    | State Bar of California attorney profile (`calbar.ca.gov`)                     | Direct attorney detail URL extraction               | Seed adapter implemented |
| CO    | Colorado Bar Association public directory (`cobar.org`)                        | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| CT    | Connecticut Bar Association public directory (`ctbar.org`)                     | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| DE    | Delaware Courts attorney regulation records (`courts.delaware.gov`)            | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| FL    | The Florida Bar public directory (`floridabar.org`)                            | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| GA    | State Bar of Georgia public directory (`gabar.org`)                            | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| HI    | Hawaii State Bar Association public directory (`hsba.org`)                     | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| IA    | Iowa State Bar Association public directory (`iowabar.org`)                    | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| ID    | Idaho State Bar public directory (`isb.idaho.gov`)                             | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| IL    | Illinois ARDC attorney registration records (`iardc.org`)                      | Printable profile URL seed + strict validation      | Adapter implemented      |
| IN    | Indiana State Bar public directory (`inbar.org`)                               | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| KS    | Kansas Judicial Branch attorney records (`kscourts.gov`)                       | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| KY    | Kentucky Bar Association public directory (`kybar.org`)                        | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| LA    | Louisiana Attorney Disciplinary Board attorney records (`ladb.org`)            | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| MA    | Massachusetts BBO attorney records (`massbbo.org`)                             | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| MD    | Maryland Courts attorney discipline records (`courts.state.md.us`)             | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| ME    | Maine Board of Overseers of the Bar public directory (`mainebar.org`)          | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| MI    | State Bar of Michigan public directory (`michbar.org`)                         | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| MN    | Minnesota Courts attorney records (`mncourts.gov`)                             | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| MO    | The Missouri Bar public directory (`mobar.org`)                                | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| MS    | The Mississippi Bar public directory (`msbar.org`)                             | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| MT    | State Bar of Montana public directory (`montanabar.org`)                       | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| NC    | North Carolina State Bar public directory (`ncbar.gov`)                        | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| ND    | State Bar Association of North Dakota public directory (`sband.org`)           | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| NE    | Nebraska Judicial Branch attorney directory (`supremecourt.nebraska.gov`)      | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| NH    | New Hampshire Bar Association public directory (`nhbar.org`)                   | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| NJ    | New Jersey Courts attorney directory (`njcourts.gov`)                          | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| NM    | State Bar of New Mexico public directory (`sbnm.org`)                          | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| NV    | State Bar of Nevada public directory (`nvbar.org`)                             | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| NY    | New York Courts attorney directory (`courts.state.ny.us`)                      | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| OH    | Supreme Court of Ohio attorney directory (`supremecourt.ohio.gov`)             | Fragment profile URL + API-backed record mapping    | Seed adapter implemented |
| OK    | Oklahoma Bar Association public directory (`okbar.org`)                        | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| OR    | Oregon State Bar public directory (`osbar.org`)                                | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| PA    | Pennsylvania Disciplinary Board attorney directory (`padisciplinaryboard.org`) | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| RI    | Rhode Island Judiciary attorney records (`courts.ri.gov`)                      | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| SC    | South Carolina Bar public directory (`scbar.org`)                              | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| SD    | State Bar of South Dakota public directory (`statebarofsouthdakota.com`)       | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| TN    | Tennessee Board of Professional Responsibility attorney records (`tbpr.org`)   | Direct attorney detail URL seed + strict validation | Seed adapter implemented |
| TX    | State Bar of Texas public directory (`texasbar.com`)                           | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| UT    | Utah Courts public legal directory (`utcourts.gov`)                            | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| VA    | Virginia State Bar public directory (`vsb.org`)                                | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| VT    | Vermont Bar Association public directory (`vtbar.org`)                         | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| WA    | Washington State Bar Association legal directory (`mywsba.org`)                | Direct profile URL seed + strict validation         | Adapter implemented      |
| WI    | State Bar of Wisconsin public directory (`wisbar.org`)                         | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| WV    | West Virginia State Bar public directory (`wvbar.org`)                         | Official search flow -> resolve exact result URL    | Adapter scaffolded       |
| WY    | Wyoming State Bar public directory (`wyomingbar.org`)                          | Official search flow -> resolve exact result URL    | Adapter scaffolded       |

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
