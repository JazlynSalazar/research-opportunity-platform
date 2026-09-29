# Project Design Decisions

This document records important architectural and product decisions made during development of the Research Opportunity Platform.

The purpose is to preserve not only what was built, but why particular approaches were chosen.

---

## 1. Preserve Raw Source Records

### Decision

Raw information collected from APIs, RSS feeds, and websites is stored separately from normalized Opportunity records.

### Reason

Funding sources use different formats and may change over time.

Keeping the original source record makes it possible to:

- Trace normalized data back to its source
- Reprocess records when normalization improves
- Compare old and new source content
- Investigate extraction mistakes
- Preserve provenance

### Result

The platform uses `SourceRecord` as a staging and provenance layer.

---

## 2. Do Not Create Opportunities Directly From Every Discovered Link

### Decision

Links discovered from funding directories are first staged as candidates.

### Reason

Directory pages often contain:

- Navigation links
- Historical recipient pages
- General research pages
- Funding directories
- Actual individual awards

Automatically turning every discovered link into an Opportunity would create large amounts of bad data.

### Result

MSU and BSA use staged candidate verification before normalization.

---

## 3. Keep Source Facts Separate From Inferred Classification

### Decision

Source-authoritative information and automated classification are stored separately.

### Reason

A sponsor may explicitly provide:

- Title
- Deadline
- Eligibility
- Award amount

The platform may infer:

- Plant Science
- Genomics
- Robotics
- Education

Those inferred labels should not be presented as though the sponsor provided them.

### Result

Classification uses separate models and review states.

---

## 4. Treat Unknown Information as Unknown

### Decision

The platform should not invent missing deadlines, award amounts, eligibility, or funding-cycle information.

### Reason

Funding websites often omit fields or retain old information.

Inferring missing values can make the platform look more complete while actually reducing reliability.

### Result

Missing values remain unknown until supported by source evidence.

---

## 5. Use Conservative Deadline Extraction

### Decision

Dates are not automatically treated as current application deadlines.

### Reason

Funding websites often contain historical pages.

Examples encountered during development included:

- A BOTANY 2017 travel-grant page still online in 2026
- A yearless "Applications are due by June 1" statement
- A 2023 fundraiser deadline on a current award page

### Result

Deadline extraction checks:

- Explicit year
- Historical page context
- Deadline context
- Current cycle relevance

Only sufficiently trustworthy dates are promoted into structured Deadline records.

---

## 6. Separate Opportunity From Opportunity Cycle

### Decision

Recurring funding programs are represented by one Opportunity with one or more OpportunityCycle records.

### Reason

A continuing program should not become a completely new Opportunity every year.

Example:

```text
AJB Synthesis Papers and Prize
        |
        +--> 2026 cycle
        +--> future cycle
