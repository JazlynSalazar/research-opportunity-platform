---
layout: default
title: Research Opportunity Platform
---

# Research Opportunity Platform

An open-source platform for discovering, organizing, and personalizing research funding opportunities.

The project is designed to bring funding opportunities from federal agencies, universities, foundations, professional societies, and industry programs into one searchable system while preserving source provenance and keeping researcher-specific information private.

---

## What the Platform Does

The Research Opportunity Platform currently supports:

- Automated and semi-automated funding collection
- Multi-source opportunity aggregation
- Raw source-data preservation
- Opportunity normalization
- Funding-cycle and deadline tracking
- Eligibility information
- Automated classification
- Human classification review
- Private user research profiles
- Weighted research interests
- Personalized opportunity ranking
- Approved and provisional relevance
- Search and filtering

---

## Current Funding Sources

Current integrations include:

- Grants.gov
- National Science Foundation
- Botanical Society of America
- Michigan State University
- American Floral Endowment
- Horticultural Research Institute

Additional sources are planned, including USDA NIFA, industry programs, scientific societies, foundations, sequencing programs, and university internal funding.

See [Funding Data Sources](DATA_SOURCES.md) for the current integration status.

---

## How It Works

```text
Funding Sources
      |
      v
Collection
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
Canonical Opportunities
      |
      v
Classification
      |
      v
Research Profiles
      |
      v
Personalized Discover
