# Source and verification policy

## Evidence classes

- **A — statutory/official:** government or regulator register/dataset.
- **B — organisation-owned:** provider's own website or structured data.
- **C — trusted local source:** council, chamber, destination body or equivalent.
- **D — open/community data:** OpenStreetMap and similar collaborative datasets.
- **E — search/social discovery:** candidate discovery only unless separately corroborated.
- **F — manual:** LewesLive/SCC Nexus Data curated entry. `manual_verified=true` is an explicit human decision.

## Source usage and rights

Evidence class describes authority; `usage_mode` describes what the engine may do with it.

- **verification:** evidence that may support publication under the category-aware rules below.
- **discovery_only:** a lead, never publication evidence. It does not count as independent corroboration and cannot be promoted by `manual_verified` alone.

Local newspapers, magazines, search results and third-party directories are normally `discovery_only`. From them the engine may note non-creative facts needed to locate the subject. Before publication it must verify those facts at a durable canonical source such as the organiser's or business's own website, an official register, an authorised ticketing page, or direct documented confirmation.

`content_policy: facts_only` means descriptions, slogans, advert artwork, photographs, logos and page layout are not copied. Publisher text supplied through the manual CSV is suppressed automatically. Media is accepted only when it is owned by LewesLive, supplied with permission, or covered by a recorded licence.

Free-to-read does not mean free to republish. The correction/takedown route remains available for any source or subject that disputes an entry.

## Category-aware verification

A directory should not pretend all categories have identical verification rules. A future regulated-source layer can attach regulator IDs and evidence for food premises, care services, charities, gas/electrical work and other regulated categories without turning the directory into an endorsement service.

## Registered offices

Companies House is authoritative for company identity, but a registered office is not assumed to be a customer-facing location or evidence that the company serves Lewes. Companies House-only candidates therefore remain in review and their address is suppressed from public exports.
