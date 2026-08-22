# LocalDirectory

Evidence-led local business, place, trade, professional-service and community-directory harvesting engine for **SCC Nexus Data**.

The first configuration targets **Lewes / BN7 + 10 miles** and produces a publication-safe import for LewesLive. The same engine can be reused for another town by changing the postcode/radius configuration rather than rewriting the harvest logic.

## Why this exists

LocalDirectory applies the architecture learned from LocalEventsEngine to persistent directory entities:

1. discover candidates;
2. retain source provenance;
3. normalise names, addresses, postcodes and categories;
4. resolve duplicate entities across sources;
5. enforce geographic/service-area rules;
6. distinguish discovery from verification and publication;
7. suppress potentially private registered-office/residential location data;
8. produce internal, review and public/presentation-site outputs separately.

**Listings are signposts, not recommendations.** Publication does not constitute endorsement, safety assurance or a guarantee of qualifications, insurance, regulated status, price or current availability.

## Current source adapters

| Adapter | Role | Credential |
|---|---|---|
| Food Standards Agency FHRS | Authoritative food-establishment discovery/corroboration | None |
| Care Quality Commission care directory | Authoritative registered health/social-care locations | None |
| Charity Commission full register | Authoritative registered-charity identity and website discovery | None |
| OpenStreetMap Overpass | Broad local place/service discovery and geospatial data | None |
| Lewes Chamber of Commerce | Current local-member discovery/corroboration for the Lewes profile | None |
| Companies House | Active-company candidate discovery and corporate identity | `COMPANIES_HOUSE_API_KEY` |
| JSON-LD | Organisation-owned structured data from discovered/configured websites | None |
| Manual CSV | Curated corrections, existing site listings and hand-verified records | None |

The Companies House adapter deliberately treats a registered office as **non-public and non-trading until independently corroborated**.

The CQC adapter uses the regulator's published care-directory CSV. Physical care locations can be mapped when they are geographically in scope. Services commonly delivered away from the registered office, such as home-care/community services, are retained as service-provider records but the administrative office address/geometry is suppressed from the public map contract.

The Charity Commission adapter uses the Commission's daily full-register JSON extract. It prefilters configured nearby postcode districts, resolves the public contact postcodes to postcode centroids solely to enforce the configured radius, then discards that geometry from the listing. Charity contact addresses, phone numbers and email addresses are not published or mapped because a registered contact address is not assumed to be the charity's visitor or service location. An organisation-owned website may still be published when the register supplies one.

The Lewes Chamber adapter deliberately does not ingest Chamber-listed phone/email details because the Chamber asks that member details are not used for unsolicited mass marketing. Organisation-owned websites can subsequently provide public contact details under the normal provenance rules.

Authoritative reference documentation used for this implementation:

- Companies House public data API: `https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference`
- Companies House authentication: `https://developer.company-information.service.gov.uk/authentication`
- Food Hygiene Rating Scheme API v2: `https://api.ratings.food.gov.uk/help`
- Care Quality Commission data reuse/directory: `https://www.cqc.org.uk/about-us/transparency/using-cqc-data`
- Charity Commission full register download: `https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download`
- OpenStreetMap Overpass API: `https://wiki.openstreetmap.org/wiki/Overpass_API`
- Postcodes.io enrichment: `https://postcodes.io/docs/overview/`

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
python run.py run --config config/lewes.yaml --offline
```

The offline run is deterministic and uses only `data/manual/listings.csv`. A normal run enables live network sources:

```bash
python run.py run --config config/lewes.yaml
```

Optional Companies House source:

```bash
export COMPANIES_HOUSE_API_KEY="..."
python run.py run --config config/lewes.yaml
```

## Outputs

A Lewes run writes to `exports/lewes/`:

```text
listings.json                 complete internal records
listings.csv                  complete internal records
listings.geojson              internal mapped records
source-health.json            per-adapter success/failure and counts
quality-report.json           publication/review/rejection summary
coverage-report.json          publication breadth/depth metrics and release checks
review-queue.json             records still requiring evidence/review
public/
  directory.v1.json           publication-safe records only
  directory.v1.csv
  directory.v1.geojson
  manifest.v1.json
leweslive/
  directory.v1.json           configured presentation-site ingestion contract
  directory.v1.js             browser-ready `window.LEWESLIVE_DIRECTORY`
  manifest.v1.json
```

GitHub Actions further separates these into:

- `local-directory-public-build`
- `local-directory-leweslive-import`
- `local-directory-test-review`
- `local-directory-internal-audit`

## Publication model

Records move through a conservative lifecycle:

`discovered -> review -> published` (or `rejected`).

A record can become publication-safe when one of the following applies and core locality/category checks also pass:

- it is manually verified;
- it comes from an authoritative Class A register appropriate to that entity type (for example FHRS food establishments, CQC regulated care locations or Charity Commission registered charities);
- two independent sources corroborate the same entity;
- organisation-owned JSON-LD provides adequate operational identity and contact/location information.

A Companies House-only record is never automatically published because a registered office is not proof of a public trading location or local service offer.

A source adapter succeeding is also not sufficient to promote a new presentation feed. The Lewes production profile has explicit minimums for total publication-safe records, category depth, trade depth, website/contact/geocoded coverage and multi-source corroboration. A weak harvest is retained for audit/review but does not replace the last governed feed.

## Entity resolution

The deterministic resolver combines evidence using, in order of strength:

- company number;
- website domain;
- normalised telephone number;
- postcode plus similar trading name;
- high-confidence name/category similarity.

Branch/location compatibility checks prevent a chain's different physical locations from being collapsed simply because they share a company number, domain or phone number.

AI is not used to decide whether a business is genuine or safe. Machine-learning/LLM enrichment can be added later only behind deterministic provenance and review gates.

## Privacy

`address_public`, `phone_public` and `email_public` are explicit fields. The public exporter removes suppressed fields and will not emit map geometry for a listing whose address is not public.

This matters particularly for sole traders, home businesses, Companies House registered offices, Charity Commission contact addresses and service providers whose regulated/administrative office is not necessarily a consumer destination.

## Add another town

Generate a new configuration after obtaining a suitable centre coordinate:

```bash
python run.py init \
  --name "Brighton Directory" \
  --location "Brighton" \
  --postcode "BN1 1AA" \
  --latitude 50.8225 \
  --longitude -0.1372 \
  --radius-miles 10 \
  --output config/brighton.yaml
```

Then run:

```bash
python run.py run --config config/brighton.yaml
```

Locality-specific sources (for example a Chamber adapter) should be enabled only by that locality's configuration. Reusable authoritative/national adapters such as FHRS, CQC, Charity Commission and OpenStreetMap remain generic.

## Next source adapters

The architecture intentionally leaves room for category-aware verification adapters including regulated-trade claims where lawful/available, official education bulk datasets, local-authority data and controlled website discovery. New sources should create candidates and provenance; they should not bypass the publication gate.
