# Public Record Provenance Roadmap (U.S.)

## Scope

- Build an authoritative, ever-growing U.S. public-record law firm dataset.
- Keep only listings with strict, per-record official source URLs.
- Remove listings when the official record can no longer be verified.

## Current Baseline (March 5, 2026)

- Active strict listings: `7`
- States with strict listings: `CA` only
- Other U.S. rows were removed because they only pointed to generic directory pages (not the exact record URL).

## Strict Provenance Rules

- `source_url` must point to the exact public record URL for that listing.
- `source_url` must be on the expected official state authority domain.
- Generic source pages are rejected.
- Synthetic markers (`listing=` query/fragment hacks) are rejected.
- Chambers/private rankings are rejected as authoritative sources.

## State Adapter Strategy

- Discovery/additions must come from explicit state adapters only.
- Each adapter must:
  - query the official state authority source
  - resolve an exact per-record URL
  - emit normalized listing rows that pass strict validation
- Until an adapter exists, that state remains unsupported for automated additions.

## 50-State Matrix

| State | Official Authority (Domain)                                                    | Adapter Method                                   | Status                  |
| ----- | ------------------------------------------------------------------------------ | ------------------------------------------------ | ----------------------- |
| AK    | Alaska Bar Association public directory (`alaskabar.org`)                      | Official search flow -> resolve exact result URL | Adapter required        |
| AL    | Alabama State Bar public directory (`alabar.org`)                              | Official search flow -> resolve exact result URL | Adapter required        |
| AR    | Arkansas Bar Association public directory (`arkbar.com`)                       | Official search flow -> resolve exact result URL | Adapter required        |
| AZ    | State Bar of Arizona public directory (`azbar.org`)                            | Official search flow -> resolve exact result URL | Adapter required        |
| CA    | State Bar of California attorney profile (`calbar.ca.gov`)                     | Direct attorney detail URL extraction            | Manual strict seed only |
| CO    | Colorado Bar Association public directory (`cobar.org`)                        | Official search flow -> resolve exact result URL | Adapter required        |
| CT    | Connecticut Bar Association public directory (`ctbar.org`)                     | Official search flow -> resolve exact result URL | Adapter required        |
| DE    | Delaware Courts attorney regulation records (`courts.delaware.gov`)            | Official search flow -> resolve exact result URL | Adapter required        |
| FL    | The Florida Bar public directory (`floridabar.org`)                            | Official search flow -> resolve exact result URL | Adapter required        |
| GA    | State Bar of Georgia public directory (`gabar.org`)                            | Official search flow -> resolve exact result URL | Adapter required        |
| HI    | Hawaii State Bar Association public directory (`hsba.org`)                     | Official search flow -> resolve exact result URL | Adapter required        |
| IA    | Iowa State Bar Association public directory (`iowabar.org`)                    | Official search flow -> resolve exact result URL | Adapter required        |
| ID    | Idaho State Bar public directory (`isb.idaho.gov`)                             | Official search flow -> resolve exact result URL | Adapter required        |
| IL    | Illinois ARDC attorney registration records (`iardc.org`)                      | Official search flow -> resolve exact result URL | Adapter required        |
| IN    | Indiana State Bar public directory (`inbar.org`)                               | Official search flow -> resolve exact result URL | Adapter required        |
| KS    | Kansas Judicial Branch attorney records (`kscourts.gov`)                       | Official search flow -> resolve exact result URL | Adapter required        |
| KY    | Kentucky Bar Association public directory (`kybar.org`)                        | Official search flow -> resolve exact result URL | Adapter required        |
| LA    | Louisiana Attorney Disciplinary Board attorney records (`ladb.org`)            | Official search flow -> resolve exact result URL | Adapter required        |
| MA    | Massachusetts BBO attorney records (`massbbo.org`)                             | Official search flow -> resolve exact result URL | Adapter required        |
| MD    | Maryland Courts attorney discipline records (`courts.state.md.us`)             | Official search flow -> resolve exact result URL | Adapter required        |
| ME    | Maine Board of Overseers of the Bar public directory (`mainebar.org`)          | Official search flow -> resolve exact result URL | Adapter required        |
| MI    | State Bar of Michigan public directory (`michbar.org`)                         | Official search flow -> resolve exact result URL | Adapter required        |
| MN    | Minnesota Courts attorney records (`mncourts.gov`)                             | Official search flow -> resolve exact result URL | Adapter required        |
| MO    | The Missouri Bar public directory (`mobar.org`)                                | Official search flow -> resolve exact result URL | Adapter required        |
| MS    | The Mississippi Bar public directory (`msbar.org`)                             | Official search flow -> resolve exact result URL | Adapter required        |
| MT    | State Bar of Montana public directory (`montanabar.org`)                       | Official search flow -> resolve exact result URL | Adapter required        |
| NC    | North Carolina State Bar public directory (`ncbar.gov`)                        | Official search flow -> resolve exact result URL | Adapter required        |
| ND    | State Bar Association of North Dakota public directory (`sband.org`)           | Official search flow -> resolve exact result URL | Adapter required        |
| NE    | Nebraska Judicial Branch attorney directory (`supremecourt.nebraska.gov`)      | Official search flow -> resolve exact result URL | Adapter required        |
| NH    | New Hampshire Bar Association public directory (`nhbar.org`)                   | Official search flow -> resolve exact result URL | Adapter required        |
| NJ    | New Jersey Courts attorney directory (`njcourts.gov`)                          | Official search flow -> resolve exact result URL | Adapter required        |
| NM    | State Bar of New Mexico public directory (`sbnm.org`)                          | Official search flow -> resolve exact result URL | Adapter required        |
| NV    | State Bar of Nevada public directory (`nvbar.org`)                             | Official search flow -> resolve exact result URL | Adapter required        |
| NY    | New York Courts attorney directory (`courts.state.ny.us`)                      | Official search flow -> resolve exact result URL | Adapter required        |
| OH    | Supreme Court of Ohio attorney directory (`supremecourt.ohio.gov`)             | Official search flow -> resolve exact result URL | Adapter required        |
| OK    | Oklahoma Bar Association public directory (`okbar.org`)                        | Official search flow -> resolve exact result URL | Adapter required        |
| OR    | Oregon State Bar public directory (`osbar.org`)                                | Official search flow -> resolve exact result URL | Adapter required        |
| PA    | Pennsylvania Disciplinary Board attorney directory (`padisciplinaryboard.org`) | Official search flow -> resolve exact result URL | Adapter required        |
| RI    | Rhode Island Judiciary attorney records (`courts.ri.gov`)                      | Official search flow -> resolve exact result URL | Adapter required        |
| SC    | South Carolina Bar public directory (`scbar.org`)                              | Official search flow -> resolve exact result URL | Adapter required        |
| SD    | State Bar of South Dakota public directory (`statebarofsouthdakota.com`)       | Official search flow -> resolve exact result URL | Adapter required        |
| TN    | Tennessee Board of Professional Responsibility attorney records (`tbpr.org`)   | Official search flow -> resolve exact result URL | Adapter required        |
| TX    | State Bar of Texas public directory (`texasbar.com`)                           | Official search flow -> resolve exact result URL | Adapter required        |
| UT    | Utah Courts public legal directory (`utcourts.gov`)                            | Official search flow -> resolve exact result URL | Adapter required        |
| VA    | Virginia State Bar public directory (`vsb.org`)                                | Official search flow -> resolve exact result URL | Adapter required        |
| VT    | Vermont Bar Association public directory (`vtbar.org`)                         | Official search flow -> resolve exact result URL | Adapter required        |
| WA    | Washington State Bar Association legal directory (`mywsba.org`)                | Official search flow -> resolve exact result URL | Adapter required        |
| WI    | State Bar of Wisconsin public directory (`wisbar.org`)                         | Official search flow -> resolve exact result URL | Adapter required        |
| WV    | West Virginia State Bar public directory (`wvbar.org`)                         | Official search flow -> resolve exact result URL | Adapter required        |
| WY    | Wyoming State Bar public directory (`wyomingbar.org`)                          | Official search flow -> resolve exact result URL | Adapter required        |

## Execution Order

1. Implement one adapter at a time and gate merges on strict source validation.
2. Prioritize states with machine-friendly search/results and stable URLs.
3. Add adapter tests:
   - returns direct official record URLs
   - does not emit generic source pages
   - state/domain policy remains enforced
4. Expand coverage until all 50 states have implemented adapters.

## Interrogation Checklist (Per State)

- Does the authority publish firm-level records, attorney-level records, or both?
- Is there a stable canonical result URL per record?
- Are anti-bot controls/captcha present?
- Is an official API/feed available?
- Can provenance be captured reproducibly without private sources?
