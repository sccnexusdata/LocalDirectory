# Adding a locality or presentation site

LocalDirectory is the shared harvesting, corroboration, validation and publication engine. It must not contain presentation code or assume that every run is for LewesLive.

## Contract

A locality config owns:

- project/output slug
- locality name and geographic scope
- source selection and source limits
- quality/coverage gates
- optional presentation-site bundle identity

A presentation website owns:

- branding and logos
- CSS and page layout
- maps and UI
- hosting/deployment secrets
- the consumer workflow that imports the certified directory bundle

## 1. Create a locality config

Copy `config/lewes.yaml` to a new file such as `config/brighton.yaml` and replace the locality-specific values. Do not edit `config/default.yaml` into another production town; it is deliberately neutral.

The presentation-site output is opt-in:

```yaml
outputs:
  directory: exports
  site_bundle:
    slug: brightonlive
    js_global: BRIGHTONLIVE_DIRECTORY
```

The bundle slug becomes both the generated output directory and the `published/<slug>/` release directory. The JavaScript global is the namespace consumed by the presentation site.

## 2. Calibrate quality gates

Do not copy Lewes coverage thresholds blindly. Run the new locality in review mode, inspect source coverage and category distribution, then set evidence-based thresholds for that locality.

The engine must continue to distinguish discovery from corroborated publication. A larger town may legitimately require higher absolute coverage thresholds while also exposing more duplicate and stale records.

## 3. Run the configured harvest

```bash
python run.py run --config config/brighton.yaml
```

A configured `brightonlive` bundle will be written below the locality output root with:

- `directory.v1.json`
- `directory.v1.js`
- `manifest.v1.json`

The browser JavaScript file will expose `window.BRIGHTONLIVE_DIRECTORY`; it will not create a LewesLive namespace.

## 4. Publish through the shared workflow

The weekly workflow accepts a `config_path`. Lewes remains the scheduled default, while another locality can be run with its own config. Publication uses the configured bundle slug, so the same workflow can stage `published/leweslive`, `published/brightonlive`, or another approved consumer without code duplication.

## 5. Consumer-site integration

The presentation repository should import only the governed published bundle. It should not copy LocalDirectory source code, harvesting plugins, source credentials or review/audit outputs into the website repository.

Use the same release pattern as LewesLive:

1. retrieve the configured `published/<site>/` bundle;
2. validate schema, record IDs and manifest count;
3. stage the candidate on the website's `/test/` environment;
4. verify the exact candidate remotely;
5. promote the tested commit/feed only after its gates pass.

## Non-negotiable portability rule

A run configured for another locality must not create `leweslive/`, `published/leweslive/` or `window.LEWESLIVE_DIRECTORY` unless that locality explicitly selected those values. The test suite includes a Brighton-named consumer to enforce this boundary.
