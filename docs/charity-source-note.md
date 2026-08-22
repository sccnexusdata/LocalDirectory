# Charity Commission locality note

The Charity Commission full-register contact postcode is used only as a discovery and radius-filtering signal.

A contact postcode is not assumed to be the charity's operating, visitor or service-delivery location. The adapter therefore:

- keeps only currently registered main charities;
- prefilters configured nearby postcode districts;
- resolves the contact postcode to a centroid solely to test the configured radius;
- does not retain that centroid as public map geometry;
- suppresses the registered contact address, phone and email from the public bundle;
- retains the Charity Commission identity/provenance and organisation-owned website when present.

This source is a directory signpost, not an endorsement or an assertion that services are delivered from the registered contact address.
