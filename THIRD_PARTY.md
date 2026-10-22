# Third-party notices

ProtoRepair's original code is MIT-licensed. Public protocol fixture text is
adapted from the sources below. The adaptations are limited to condensing the
assembly excerpt, substituting a commercial NMC811 where stated, adding clearly
labeled test values, and creating synthetic seeded faults. The source paper's
scientific claims are not reproduced and no abstract is included.

| ID | Source | License | Public? | Changes / use |
|---|---|---|---|---|
| P2 / G02, G03–G06, G14 | Llanos et al., “High Voltage Cycling Stability of LiF-Coated NMC811 Electrode,” *ACS Applied Materials & Interfaces* 2024, 16, 2216–2230. DOI [10.1021/acsami.3c14394](https://doi.org/10.1021/acsami.3c14394) | CC BY 4.0 | Yes | Assembly excerpt condensed; commercial NMC811 substituted; LiF coating omitted; G03–G06 are synthetic faults; G14 adds labeled test values (50 µm Li, solids/NMP, 120 °C CAM dry, water ppm). |
| P4 / G07, G08 | Zhang et al., *Nature Communications* 2025, 16, 3344. DOI [10.1038/s41467-025-58627-3](https://doi.org/10.1038/s41467-025-58627-3) | CC BY 4.0 | Yes | Text condensed; “5.0 wt% NMP” and “3 mAh g−1” retained as natural ambiguities; G08 changes 40 µm Li to 4 µm. |
| P5 / G09–G11 | Yan et al., *Nature Communications* 2026, 17. DOI [10.1038/s41467-026-72530-5](https://doi.org/10.1038/s41467-026-72530-5) | CC BY 4.0 | Yes | Text condensed; G10 adds a 1,200 ppm NMC811 water value; G11 reduces salt concentrations. |
| P1 / G01, G13 | Sigma-Aldrich technical protocol, “Streamlined Electrode Fabrication.” [Source link](https://www.sigmaaldrich.com/US/en/technical-documents/protocol/materials-science-and-engineering/batteries-supercapacitors-and-fuel-cells/streamlined-electrode-fabrication-user-friendly-guide-cathode-electrodes) | All rights reserved | **No** | Local-only evaluation. No source text, procedure, or derived clean fixture is published; P1 is not used as public evidence metadata. |
| P3 / G12 | Peng et al., *Nature Communications* 2025, 17, 590. DOI [10.1038/s41467-025-67290-7](https://doi.org/10.1038/s41467-025-67290-7) | CC BY-NC-ND 4.0 | **No** | Local-only evaluation; no source text or fixture is published. |

## Software

- [Streamlit](https://streamlit.io/) — Apache-2.0.
- [Pint](https://pint.readthedocs.io/) — BSD-3-Clause.
- [requests](https://requests.readthedocs.io/) — Apache-2.0.
- [python-dotenv](https://github.com/theskumar/python-dotenv) — BSD-3-Clause.
- [jsonschema](https://github.com/python-jsonschema/jsonschema) — MIT.
- [pytest](https://pytest.org/) — MIT.

## Evidence metadata

Public evidence cards are metadata-only. Retrieval was powered by **Valency MCP
Bond** (https://www.valency.io/bond/). No abstracts, raw MCP responses, Valency
screenshots, or logos are included; no endorsement is implied. Numeric thresholds
are attributed to curated reference items or manufacturer datasheets, not to
abstracts. The runtime does not call Valency and ships no Valency token.

## Hazard note

NMP, Li metal, HF, and coin-cell assembly are hazardous. This repository is a
text/arithmetic checker, not a safety review. Follow institutional EHS and PI
review.
