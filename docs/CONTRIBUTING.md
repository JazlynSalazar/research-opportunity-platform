---
layout: default
title: Contributing
---

# Contributing to the Research Opportunity Platform

Thank you for your interest in contributing to the Research Opportunity Platform.

This project is being developed as an open-source system for discovering, organizing, and personalizing research funding opportunities.

Contributions may include:

- Adding funding sources
- Improving existing collectors
- Improving normalization
- Improving classification
- Building user-facing features
- Improving documentation
- Writing tests
- Fixing bugs
- Improving accessibility and usability

---

# Project Principles

Before contributing, please review the project's core design principles.

## Preserve Source Provenance

Funding information should remain traceable to the original source.

Whenever possible, preserve:

- Source URL
- External identifier
- Raw source data
- Collection date
- Verification information

Do not discard source evidence after normalization.

---

## Keep Source Facts Separate From Inference

The platform distinguishes between:

```text
Sponsor-provided information
        ↓
Normalized information
        ↓
Automated classification
        ↓
User-specific relevance
