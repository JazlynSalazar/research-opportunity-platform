# Research Opportunity Platform Roadmap

This roadmap tracks planned development for the Research Opportunity Platform.

The project is being developed incrementally so that new features preserve source provenance, user privacy, and clear separation between source-authoritative information and inferred relevance.

---

## Current Status

The current proof of concept supports:

- Multi-source funding collection
- Source provenance
- Canonical Opportunities
- Funding cycles and deadlines
- Automated classification
- Classification review
- User authentication
- Private user-owned research profiles
- Starter profile templates
- Browser-based profile creation and editing
- Personalized relevance ranking
- Approved and provisional relevance
- Search and filtering in Discover

---

# Phase 1 — Funding Discovery Foundation

**Status: Mostly complete**

Core goals:

- Collect funding opportunities from multiple sources
- Preserve raw source records
- Normalize opportunities into a shared schema
- Track sponsors and sources
- Track opportunity cycles
- Track deadlines
- Preserve eligibility information
- Support source-specific enrichment

Implemented sources include:

- Grants.gov
- National Science Foundation
- Botanical Society of America
- American Floral Endowment
- Horticultural Research Institute
- Michigan State University

Additional source development will continue throughout the project.

---

# Phase 2 — Classification and Relevance

**Status: Working proof of concept**

Implemented:

- Automated rules-based classification
- Research-domain classifications
- Method and technology classifications
- Purpose classifications
- Classification review workflow
- Approved classifications
- Provisional classifications
- Weighted relevance scoring

Current relevance categories include examples such as:

- Plant Science
- Agriculture
- Genomics
- Robotics
- Automation
- Phenotyping
- Imaging
- Bioinformatics
- Education
- Workforce Development
- Extension
- Fellowship Support

Future improvements:

- Expand classification vocabulary
- Improve synonym handling
- Improve classification precision
- Add better evidence tracking
- Evaluate machine-learning or embedding-based classification
- Preserve explainable relevance results

---

# Phase 3 — Multi-User Research Profiles

**Status: Implemented proof of concept**

Implemented:

- Django authentication
- Private user-owned profiles
- Starter profile templates
- Blank profile creation
- Template copying
- Profile editing
- Weighted relevance signals
- Default profiles
- Profile duplication
- Profile archiving
- Profile deletion
- Research-profile selector in Discover

Future improvements:

- Better profile-building interface
- Controlled vocabulary selection
- Research-topic autocomplete
- Better profile templates
- Career-stage preferences
- Eligibility preferences
- Funding-size preferences
- Geographic or institutional preferences

---

# Phase 4 — Saved Opportunities

**Status: Next major feature**

Goal:

Allow users to save interesting opportunities without immediately creating a formal application record.

Planned model:

```text
User
  |
  +--> SavedOpportunity
          |
          +--> Opportunity
          +--> Saved date
          +--> Priority
          +--> Private notes
          +--> Discovery profile
