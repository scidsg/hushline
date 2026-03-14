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

### EU Phase 0B (Strict Provenance Gate)

#### Baseline Alignment

- EU attorney coverage inherits the same strict provenance standard used for the U.S. rollout.
- No EU adapter or seed dataset may land until a country issue records the authoritative source class, exact allowed domains, approved `source_label` values, and any exception evidence required below.

#### Required Source Standard

- `source_url` must be the exact official record URL for that listing.
- `source_url` must not be a search form, search-results page, home page, generic directory landing page, or country summary page.
- `source_url` must not match the listed organization's own `website`; it must point to the external authority source of record.
- The source record must come from an official bar, regulator, judiciary, or statutory authority acting within its published mandate.

#### Allowed-Domain Policy

- Each country issue must list the exact allowed apex domains. Broad suffix rules such as `.eu`, `.gov`, or "official-looking domains" are not acceptable.
- `source_url` host may match one listed apex domain or a documented subdomain of that domain.
- A domain is allowed only when it is controlled by the relevant official authority, or the authority explicitly designates it as the canonical public register.
- Third-party mirrors, internet archives, unofficial PDFs, press summaries, and republished copies are not allowed.
- The "Expected Official Domain(s)" column in the Phase 0A matrix is planning evidence only. It does not approve those domains for implementation until a country issue narrows them into an explicit allowed-domain set.

#### EU Source-Label Taxonomy

| Approved Label Pattern                        | Use When                                                         | Example                                                          |
| --------------------------------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------------- |
| `{Authority Name} attorney directory`         | Official bar or law-society membership/profile directory         | `Conseil national des barreaux attorney directory`               |
| `{Authority Name} attorney register`          | Official statutory or regulatory roll of admitted lawyers        | `BRAK attorney register`                                         |
| `{Authority Name} attorney census record`     | Official nationwide census or roster naming licensed attorneys   | `Consejo General de la Abogacia Espanola attorney census record` |
| `{Authority Name} attorney discipline record` | Official judicial or regulatory disciplinary or sanctions record | `Court of Appeal attorney discipline record`                     |

- Labels must name the authority first and the record class second.
- A country issue must map each permitted source class to one approved display label before implementation starts.
- Marketing or trust-signaling language such as `top`, `best`, `verified`, `recommended`, or private brand names is disallowed in `source_label`.

#### Disallowed Source Classes

- Private rankings and editorial products such as Chambers, Legal 500, and Best Lawyers.
- Lead-generation, referral, or commercial directory sites.
- Law-firm self-reported websites, biographies, or newsroom pages.
- Unofficial caches, mirrors, scraped copies, and search-engine result pages.
- Generic official search entrypoints or directory home pages that do not resolve to a record-specific URL.

#### Narrow Exception Rules

- Federated official bar structures may use multiple official domains only if no single national authority domain exists and the country issue documents the official basis for each participating authority.
- Vendor-hosted domains may be used only if the official authority identifies the domain as its canonical public register and the country issue captures a stable record-specific URL example from that domain.
- No exception may authorize private rankings, lead-gen sites, or unofficial mirrors.
- Each exception requires:
  - an official source proving the authority relationship
  - the exact allowed domains
  - at least one example record-specific URL per domain
  - maintainer approval recorded in the country issue before adapter work starts

### EU Execution Order

1. Treat EU Phase 0B as a hard gate: no EU adapter or seed data before a country issue captures the allowed domains, approved `source_label` values, and any exception evidence.
2. Open country issues only from rows marked `Candidate` or `Deferred`.
3. In each country issue, confirm the exact allowed domain set, whether direct per-record URLs are stable, and which Phase 0B source-label pattern applies.
4. Promote `Deferred` rows to `Candidate` only after a country issue captures the exact search/detail URL shape.
5. Leave `Blocked` rows policy-only until a single authoritative public source, or a maintainer-approved federated policy, is documented.

### EU Phase 0C (Per-Country Feasibility Survey)

- Evidence below was reviewed on March 14, 2026 from official national bar or regulator pages.
- `Open country issue` means an official attorney-level source exposed a reproducible record URL shape that appears compatible with Phase 0B strict provenance.
- `Defer` means the official source is known, but the current public surface still lacks a pinned exact-record URL policy, has material workflow instability, or requires a federated exception that is not yet documented.
- The Phase 0C recommendation column supersedes the provisional Phase 0A status column when they differ.

| Country     | Official source evidence                                                                                                                                                                                                                                                                                                                                    | Record level seen                 | Provenance URL status                                                                                                       | Concrete blocker risks                                                                                                                                                                      | Likely adapter strategy                                        | Recommendation     |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ------------------ |
| Austria     | [OERAK search](https://service.oerak.at/ravzsuche/Pages/SearchForm.aspx); indexed [OERAK lawyer detail](https://www.oerak.at/en/support-and-services/services/find-a-lawyer/?cHash=0b3d29ab383516621630094d435b7783&tx_rafinden_simplesearch%5Baction%5D=show&tx_rafinden_simplesearch%5Bcontroller%5D=LawyerSearch&tx_rafinden_simplesearch%5Blid%5D=7709) | Attorney                          | Yes. Official lawyer detail pages on `oerak.at` expose a lawyer-specific `lid` URL shape.                                   | Search-form discovery is still required to resolve `lid`; detail URLs include `cHash`, so the country issue should confirm which query parts are canonical before import.                   | Search-form workflow -> HTML detail-page extraction            | Open country issue |
| Belgium     | [OVB search](https://www.advocaat.be/nl/); indexed [OVB lawyer detail](https://www.advocaat.be/nl/zoek-een-advocaat/advocaat/b4743534-d3e4-4d87-a53c-5629a9f3bbc4); [AVOCATS.BE search](https://www.avocats.be/fr/trouver-un-avocat)                                                                                                                        | Attorney, but split by bar system | Partial. Stable UUID attorney URLs were observed on `advocaat.be`; no AVOCATS.BE lawyer-detail URL was surfaced.            | Nationwide coverage is federated across multiple official authorities and domains; French/German-side detail URL shape remains unpinned; Phase 0B multi-domain exception needed.            | Federated search-form workflow per authority                   | Defer              |
| Finland     | [Finnish Bar Association attorney-search guidance](https://asianajajat.fi/en/legal-advice/how-do-i-find-an-attorney-at-law/)                                                                                                                                                                                                                                | Attorney                          | Unknown. The official page says the search tool covers all Finnish attorneys-at-law, but no canonical profile URL surfaced. | No indexed attorney-detail URL was observed on the official domain; search/detail flow may be JS-driven or otherwise unindexed, so exact-record provenance is not yet reproducible.         | Search-form workflow                                           | Defer              |
| France      | [CNB national directory](https://www.cnb.avocat.fr/fr/annuaire-des-avocats-de-france); [avocat.fr directory landing page](https://www.avocat.fr/annuaire-des-avocats-de-france)                                                                                                                                                                             | Attorney                          | Unknown. The national directory is public, but the official landing page exposes it via an embedded `iframe`.               | The embedded directory obscures the canonical host and exact allowed-domain set for record URLs; no direct lawyer permalink was surfaced in the official crawl.                             | Search-form workflow after canonical host/domain pinning       | Defer              |
| Germany     | [BRAK register overview](https://www.brak.de/service/bundesweites-amtliches-anwaltsverzeichnis/); [official register search](https://www.bea-brak.de/bravsearch/index.brak)                                                                                                                                                                                 | Attorney                          | Not yet. BRAK says the register covers all admitted lawyers, but no stable detail URL was captured.                         | On March 14, 2026 the public register redirected to `http://bravsearch.bea-brak.de/bravsearch/` and returned an expired-dialog or unknown-error state, suggesting a session-bound workflow. | Search-form workflow only if session-safe detail URLs exist    | Defer              |
| Italy       | [CNF lawyer-search endpoint](https://www.consiglionazionaleforense.it/web/cnf/ricerca-avvocati)                                                                                                                                                                                                                                                             | Attorney (expected)               | Not yet. The official CNF endpoint could not be validated as a public record source.                                        | On March 14, 2026 the official CNF search endpoint returned HTTP `403`, so the access path, exact detail URL shape, and any anti-bot controls remain unverified.                            | Defer until official public search/detail flow is confirmed    | Defer              |
| Luxembourg  | [Barreau de Luxembourg annuaire](https://www.barreau.lu/annuaire/); [RGPD annuaire note](https://www.barreau.lu/rgpd/); [tableau/list descriptions](https://www.barreau.lu/le-metier-davocat/devenir-avocat/presentation/)                                                                                                                                  | Attorney and firm                 | Unknown. The public annuaire and privacy notice confirm published bar data, but no distinct per-lawyer URL was observed.    | Search results appear inline on the annuaire page; an exact lawyer permalink has not yet been pinned, and the privacy notice frames publication as public verification data.                | Search-form workflow; static seed only if exact URLs are found | Defer              |
| Netherlands | [NOvA search](https://zoekeenadvocaat.advocatenorde.nl/); indexed [attorney detail example](https://zoekeenadvocaat.advocatenorde.nl/advocaten/velp-gld/de-heer-mr-wg-damen/11398673937)                                                                                                                                                                    | Attorney and firm                 | Yes. Public attorney URLs under `/advocaten/.../{id}` are stable and crawlable on the official domain.                      | The source also exposes office pages under `/kantoren/.../{id}`; the adapter must avoid treating firm pages as attorney provenance when both surfaces exist.                                | HTML detail-page extraction                                    | Open country issue |
| Portugal    | [OA microsite home](https://advogado.oa.pt/); [OA notice documenting `https://advogado.oa.pt/nnnnnnn`](https://portal.oa.pt/comunicacao/comunicados/2022/informacao-nova-funcionalidade-pagina-pessoal-do-advogado/); [profile example](https://advogado.oa.pt/13639L)                                                                                      | Attorney                          | Yes. OA states each lawyer receives a direct page keyed by professional number, and public profile pages are crawlable.     | Discovery still depends on the OA public search path that maps names to `cédula` numbers; contact forms use a robot check, but the profile pages themselves are public.                     | Search-form workflow -> direct profile extraction              | Open country issue |
| Spain       | [General Census of Lawyers](https://www.abogacia.es/servicios/ciudadanos/censo-general-de-letrados/)                                                                                                                                                                                                                                                        | Attorney                          | Unknown. The official census says it exposes a lawyer file, but no record-specific URL was surfaced in crawl.               | The official landing page routes users into app/mobile and census flows, but the exact public lawyer-profile URL pattern remains unverified.                                                | Search-form workflow                                           | Defer              |
| Sweden      | [Swedish Bar Association member-search entry point](https://www.advokatsamfundet.se/en/)                                                                                                                                                                                                                                                                    | Attorney (members only)           | Unknown. The official site says the public can search among all members, but no profile URL pattern was surfaced.           | No public member-detail permalink or search endpoint was observed in crawl, suggesting a JS-driven or otherwise opaque search/results flow.                                                 | Search-form workflow                                           | Defer              |
