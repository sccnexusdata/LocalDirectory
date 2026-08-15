# LewesLive import contract

`exports/<slug>/leweslive/directory.v1.json` contains only `publish_safe=true` records.

Top level:

```json
{
  "schemaVersion": "1.0",
  "generatedAt": "ISO-8601 timestamp",
  "listings": []
}
```

Each listing contains stable `id`, name, type, category, description, public contact/location fields, service area, confidence, provenance summary and `lastChecked`.

`directory.v1.js` contains the same payload assigned to `window.LEWESLIVE_DIRECTORY`, allowing a static LewesLive build to load the file without a runtime API.
