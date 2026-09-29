# Development Log

This document records major milestones in the development of the Research Opportunity Platform.

The goal is to document meaningful project changes, design decisions, new data sources, and working features without recording every small debugging step.

---

## September 28, 2026 — Multi-User Personalized Discovery

### Research Profiles

Added database-backed research profiles.

Converted the original proof-of-concept profiles into reusable starter templates:

- Plant Science and Agricultural Technology
- Plant Genomics and Pathology
- Agricultural Robotics and Technology
- Education and Workforce Development
- Graduate Fellowships and Awards

Added user ownership to research profiles so each logged-in researcher can maintain private profiles.

### Authentication

Added Django authentication and login/logout functionality.

Private profiles are tied to the authenticated user.

### Browser-Based Profile Management

Added a normal user interface for managing research profiles outside Django Admin.

Users can now:

- Create a blank research profile
- Copy a starter template
- Edit the profile name and description
- Add relevance signals
- Assign Low, Medium, or High importance
- Remove relevance signals
- Duplicate profiles
- Choose a default profile
- Archive and restore profiles
- Delete profiles

### FarmBot Research Profile

Created a custom FarmBot Research profile using relevance signals including:

- Robotics
- Automation
- Phenotyping
- Imaging
- Education

This demonstrated that researchers can create profiles that are different from the original starter templates.

### Personalized Discover

Removed the original hard-coded Plant-Tech relevance profile.

Discover can now use a private research profile selected by the logged-in user.

Added filtering by:

- Research profile
- Search term
- Relevance
- Funding source
- Opportunity type
- Funding-cycle status

### Relevance Scoring

Separated personalized relevance into two categories.

**Approved relevance**

Uses classification labels that have been reviewed and approved.

**Provisional relevance**

Uses automated classification labels that have not yet been human-reviewed.

This allows newly collected opportunities to appear in personalized results without incorrectly presenting automated classifications as confirmed facts.

The FarmBot Research profile successfully returned personalized provisional matches.

---

## September 27–28, 2026 — Botanical Society of America Integration

Added the Botanical Society of America as a funding source.

### BSA Collection

Imported the official BSA awards directory.

Discovered 114 candidate BSA award-related pages.

### Candidate Verification

Created a verification process to distinguish between:

- Active award programs
- Possible award programs
- Historical award-recipient pages
- Directory or navigation pages
- Pages requiring manual review

This prevented historical recipient pages from becoming funding opportunities.

### Opportunity Normalization

Verified BSA award programs can now become canonical Opportunities in the funding database.

### BSA Classification

Added BSA pages to the shared classification system.

### Cycle and Deadline Extraction

Created conservative extraction logic for:

- Funding-cycle status
- Deadline candidates
- Eligibility evidence
- Dollar amounts
- Historical-page indicators

The system intentionally avoids assigning a year to a deadline unless the source provides one.

### Historical Data Protection

A BSA page for a BOTANY 2017 travel grant contained the text:

> Applications are due by June 1.

Because the page referred to BOTANY 2017 and did not provide a current deadline year, the system correctly prevented this deadline from being promoted as a current funding deadline.

### AJ Harris Graduate Student Research Award

The page contained a 2023 fundraiser deadline.

The first parser incorrectly treated that fundraiser deadline as the award deadline.

The extraction logic was updated to exclude fundraising and donation deadlines.

The award now remains a valid program with an unknown current application deadline rather than being incorrectly marked closed.

### AJB Synthesis Papers and Prize

The source page provided current 2026 information.

The platform successfully extracted and structured:

- 2026 funding cycle
- Closed status
- June 5, 2026 deadline
- Eligibility evidence
- Source provenance

This became the first BSA award with structured cycle information displayed in Discover.

---

## September 2026 — Michigan State University Funding

Added Michigan State University as a funding source.

Configured program-level sources including:

- Project GREEEN
- Research Enhancement Award
- Graduate School Travel Funding
- Dissertation Completion Fellowships
- Graduate School Fellowship Directory
- Horticulture scholarships
- MSU scholarship catalog
- Institutionally Limited Proposals

### Directory Discovery

Added discovery of individual funding links from MSU funding directories.

### Candidate Staging

Created staged candidate records rather than immediately creating Opportunities.

This allows individual links to be verified before entering the canonical database.

### Candidate Verification

Verified candidate pages can be classified as:

- Individual award
- Possible funding program
- Directory or navigation page
- Needs review

The first candidate set contained 82 records.

The verification process correctly separated genuine AcademicWorks scholarships from generic funding and research-navigation pages.

### Verified MSU Awards

High-confidence individual awards can now be normalized into the canonical Opportunity database.

---

## September 2026 — NSF Integration

Added National Science Foundation funding collection.

Implemented:

- NSF RSS collection
- SourceRecord staging
- Official NSF page enrichment
- Opportunity normalization
- Classification using enriched page text

NSF funding pages are visible in Discover.

Structured current-cycle extraction remains a future improvement.

---

## September 2026 — AFE and HRI Integration

Added official funding pages from:

- American Floral Endowment
- Horticultural Research Institute

Implemented:

- Official page collection
- Source provenance
- Opportunity normalization
- Classification

More detailed deadline and cycle extraction is planned.

---

## September 2026 — Grants.gov Pipeline

Grants.gov became the primary federal funding source for the initial platform.

Implemented:

- Grants.gov search API collection
- Raw SourceRecord staging
- Opportunity-detail enrichment
- Forecast and posted opportunity support
- Opportunity normalization
- Eligibility extraction
- Funding category extraction
- Funding cycle creation
- Deadline creation
- Award range information
- Classification

### Paginated Collection

Added paginated keyword searching.

The platform can collect multiple pages of search results and record coverage information including:

- Reported total
- Rows fetched
- Unique records
- Pages fetched
- Completion status

### Multi-Keyword Discovery

Added funding-discovery searches covering areas such as:

- Agriculture
- Horticulture
- Plant science
- Genomics
- Plant pathology
- Plant breeding
- Phenotyping
- Robotics
- Automation
- STEM education
- Workforce development
- Fellowships

### Automated Update Pipeline

Added a single update workflow covering:

- Discovery
- Enrichment
- Normalization
- Classification

Added PipelineRun history so pipeline execution can be reviewed.

### Pipeline Lock

Added a local lock to prevent two update processes from running simultaneously.

### Local Scheduling

Configured a macOS LaunchAgent to run the Grants.gov update pipeline automatically.

---

## Core Data Model

The platform currently includes canonical models for:

- Sponsor
- Source
- Opportunity
- OpportunityCycle
- Deadline
- EligibilityCriterion
- Tag
- ImportRun
- SourceRecord
- ClassificationResult
- ClassificationReview
- PipelineRun
- ResearchProfile
- ResearchProfileWeight

---

## Current Architecture Checkpoint

The working platform now combines:

```text
Multiple funding sources
        ↓
Collection and provenance
        ↓
Verification and enrichment
        ↓
Normalization
        ↓
Canonical funding catalog
        ↓
Classification
        ↓
Private user research profiles
        ↓
Personalized Discover
