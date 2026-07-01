---
name: academic-literature-alert
description: literature monitoring and email alert workflow for academic publishing, publishing management, digital publishing, media management, communication studies, management research, and technology-frontier topics. use when the user needs to retrieve, score, deduplicate, summarize, and email metadata for recent, high-impact, highly cited, transferable, or technology-related academic literature without downloading full texts.
---

# Academic Literature Alert

This Skill supports academic literature metadata alerts for publishing management, scholarly publishing, digital publishing, digital content industries, media management, communication studies, management research, and technology-frontier topics.

It retrieves, scores, deduplicates, summarizes, and emails metadata only. It does not download full-text PDFs, scrape paywalled databases, bypass logins, solve CAPTCHAs, or work around anti-bot controls.

## Data Sources

- Chinese literature: prioritize journal websites, RSS feeds, open pages, and bibliographic records manually exported by the user as CSV or XLSX.
- English literature: prioritize open metadata APIs including Crossref, OpenAlex, and Semantic Scholar.
- Restricted databases such as CNKI, Wanfang, VIP, Web of Science, Scopus, and JCR are supported only through user-provided exported records.
- Missing abstracts, DOI values, citation counts, impact metrics, or journal rankings must be marked as missing. Do not invent missing metadata.

## Daily And Weekly Alerts

- Daily alerts emphasize freshness and breadth. They select 1-2 items each from classic highly cited English literature, transferable management and communication research, technology-frontier research, and digital publishing or digital content industry research.
- Weekly alerts emphasize quality and topic fit. They select 4 recent high-quality items across publishing management, scholarly publishing, digital publishing, and digital content industries, normally 2 Chinese and 2 English items when available.

## Output Fields

Each pushed item should include:

- title
- authors
- year or publication date
- journal or venue
- DOI or URL
- source data provider
- abstract or explicit missing marker
- topic category
- score and reading priority
- recommendation reason
- relation to publishing management, scholarly publishing, or digital publishing research

## Scoring Rules

The default scoring combines:

- topic relevance
- source quality
- recency
- citation influence
- transferable value for publishing, management, communication, or digital content research

Items are assigned reading priorities:

- A: high priority
- B: useful priority
- C: optional tracking

Detailed rules live in `references/scoring_rules.md`.

## Deduplication Rules

- Same DOI means same literature record.
- If DOI is missing, normalized title hash is used.
- The same item should not be pushed again within 90 days.
- Classic highly cited English literature should not be pushed again within 180 days.
- Missing abstracts do not permit fabricated summaries.

## Email Template

Emails are rendered from `references/email_template.md`. The default message contains a short digest, grouped items, metadata, recommendation reasons, and data-source notes.

## GitHub Actions

The repository includes:

- `.github/workflows/daily_literature.yml`
- `.github/workflows/weekly_literature.yml`

Both workflows install dependencies, read email settings from GitHub Actions Secrets, run the pipeline, and commit updated cache and pushed-record files back to the repository when there are changes.

## Modify Topic Areas

Edit `config/topics.yml` to add, remove, or rename topic groups and keywords. The scoring script reads those groups and uses them to estimate relevance and category assignment.
