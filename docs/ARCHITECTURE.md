# Research Opportunity Platform Architecture

This document describes the architecture of the Research Opportunity Platform and the design principles used to move funding information from external sources into a shared, personalized discovery system.

---

# 1. Architectural Goals

The platform is designed around several core principles:

- Preserve original source data and provenance.
- Keep source-authoritative information separate from inferred classifications.
- Avoid creating canonical Opportunities directly from unverified scraped links.
- Treat missing information as unknown rather than inventing values.
- Keep the shared funding catalog separate from private user information.
- Make automated relevance explainable.
- Support multiple funding sources without requiring each source to use the same data format.
- Allow future laboratories and organizations to collaborate without exposing personal information by default.

---

# 2. High-Level Architecture

The main data flow is:

```text
External Funding Sources
        |
        v
Collectors
        |
        v
Raw Source Records
        |
        v
Verification / Enrichment
        |
        v
Normalization
        |
        v
Canonical Opportunity Catalog
        |
        +-----------------------------+
        |                             |
        v                             v
Opportunity Cycles              Classification
        |                             |
        v                             v
Deadlines                   Classification Review
        |                             |
        +-------------+---------------+
                      |
                      v
              Research Profiles
                      |
                      v
             Personalized Ranking
                      |
                      v
                  Discover
