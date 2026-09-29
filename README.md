# Research Opportunity Platform

An open-source platform for discovering, organizing, and personalizing research funding opportunities.

## Project Goal

Research funding information is spread across federal agencies, universities, professional societies, foundations, companies, and individual program websites.

This project aims to create a shared platform that can:

- Automatically collect research funding opportunities
- Preserve the original source and provenance
- Normalize opportunities into a common structure
- Track funding cycles and deadlines
- Classify opportunities by research topic and purpose
- Let researchers create private research-interest profiles
- Rank opportunities based on those profiles
- Eventually support saved opportunities, application tracking, notes, and internal deadlines

## Current Features

The current proof of concept includes:

- Grants.gov collection and enrichment
- NSF funding collection
- Botanical Society of America award discovery
- American Floral Endowment funding sources
- Horticultural Research Institute funding sources
- Michigan State University funding discovery
- Opportunity, funding cycle, deadline, eligibility, and provenance models
- Automated classification
- Classification review
- User login and logout
- Private research profiles
- Starter profile templates
- Browser-based profile creation and editing
- Weighted relevance signals
- Personalized Discover results
- Approved and provisional relevance scoring
- Search, source, opportunity type, and funding-status filters

## Current Architecture

```text
Funding Sources
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
Canonical Opportunities
      |
      +--> Funding Cycles
      +--> Deadlines
      +--> Eligibility
      |
      v
Classification
      |
      v
Research Profiles
      |
      v
Personalized Discover
