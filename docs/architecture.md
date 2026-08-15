# Architecture

```text
Source adapters
    |
    v
Candidate ListingRecord objects
    |
    v
Deterministic entity resolution
    |
    v
Locality + category + privacy validation
    |
    +----------------------+----------------------+
    |                      |                      |
    v                      v                      v
Internal evidence       Review queue        Publish-safe records
                                                   |
                                           +-------+-------+
                                           |               |
                                           v               v
                                     Public bundle    LewesLive import
```

The central rule is **discovery is not publication**. Every adapter reports source class, source identity, retrieval time and source URL. Entity resolution merges evidence without erasing provenance.
