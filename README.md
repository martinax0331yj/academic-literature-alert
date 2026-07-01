# Academic Literature Alert

`academic-literature-alert` is a metadata-only literature monitoring and email alert project for publishing management, scholarly publishing, digital publishing, digital content industries, media management, communication studies, management research, and technology-frontier topics.

It contains a ChatGPT Skill, Python retrieval and scoring scripts, editable configuration, cache and deduplication files, logs, and GitHub Actions workflows for daily and weekly alerts.

## What It Does

- Retrieves English literature metadata from open sources such as Crossref, OpenAlex, and Semantic Scholar.
- Supports Chinese bibliographic records manually exported by the user as CSV or XLSX.
- Scores items by topic relevance, source quality, recency, citation influence, and transferable value.
- Deduplicates by DOI or normalized title hash.
- Renders Markdown and HTML email digests.
- Sends email through SMTP when environment variables or GitHub Secrets are configured.
- Keeps cache and pushed records under `data/`.

## Compliance

This project does not download full-text PDFs and does not bypass logins, paywalls, CAPTCHAs, or anti-bot controls. Restricted databases such as CNKI, Wanfang, VIP, Web of Science, Scopus, and JCR are supported only through user-provided exported bibliographic records.

If abstracts, DOI values, citation counts, impact factors, or journal ranking data are missing, the scripts mark them as missing. They do not fabricate metadata.

See `references/retrieval_policy.md`.

## Repository Structure

```text
academic-literature-alert/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── retrieval_policy.md
│   ├── journal_whitelist.md
│   ├── scoring_rules.md
│   └── email_template.md
├── scripts/
│   ├── fetch_literature.py
│   ├── score_literature.py
│   ├── render_email.py
│   ├── send_email.py
│   └── run_pipeline.py
├── config/
│   ├── topics.yml
│   ├── journals_zh.yml
│   ├── journals_en.yml
│   ├── schedules.yml
│   └── email.yml.example
├── data/
│   ├── pushed_records.csv
│   └── literature_cache.jsonl
├── logs/
│   └── .gitkeep
├── .github/
│   └── workflows/
│       ├── daily_literature.yml
│       └── weekly_literature.yml
├── requirements.txt
├── README.md
└── .gitignore
```

## Install

```bash
cd academic-literature-alert
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run Locally

If your local shell does not have a `python` command, use `python3` in the commands below.

Generate a daily preview without sending real email:

```bash
python scripts/run_pipeline.py --mode daily --dry-run
```

Generate a weekly preview without sending real email:

```bash
python scripts/run_pipeline.py --mode weekly --dry-run
```

Use a manually exported Chinese or restricted-database bibliography file:

```bash
python scripts/run_pipeline.py --mode weekly --dry-run --manual-records path/to/exported_records.csv
```

If you want to test without network retrieval:

```bash
python scripts/run_pipeline.py --mode daily --dry-run --skip-network
```

Email preview output is saved to:

```text
data/last_email_preview.md
```

## Email Settings

For local runs, set environment variables:

```bash
export EMAIL_SENDER="your_sender@example.com"
export EMAIL_PASSWORD="your_smtp_password"
export EMAIL_RECEIVER="receiver@example.com"
export SMTP_HOST="smtp.example.com"
export SMTP_PORT="587"
```

Do not write real passwords into code, YAML files, or committed files.

## GitHub Actions Secrets

In GitHub, open:

```text
Settings -> Secrets and variables -> Actions
```

Create these repository secrets:

```text
EMAIL_SENDER
EMAIL_PASSWORD
EMAIL_RECEIVER
SMTP_HOST
SMTP_PORT
```

## Scheduled Runs

Daily workflow:

- File: `.github/workflows/daily_literature.yml`
- Schedule: every day at about Beijing time 08:30
- UTC cron: `30 0 * * *`
- Command: `python scripts/run_pipeline.py --mode daily`

Weekly workflow:

- File: `.github/workflows/weekly_literature.yml`
- Schedule: every Monday at about Beijing time 09:00
- UTC cron: `0 1 * * 1`
- Command: `python scripts/run_pipeline.py --mode weekly`

Both workflows commit changed cache, preview, and pushed-record files back to the repository.

## Manual GitHub Sync

GitHub CLI was not required for this project. If `gh` is unavailable or not logged in, create a private repository named `academic-literature-alert` on GitHub, then run:

```bash
git remote add origin https://github.com/<YOUR_USERNAME>/academic-literature-alert.git
git branch -M main
git add .
git commit -m "init academic literature alert skill"
git push -u origin main
```

If a first local commit already exists, skip the `git add` and `git commit` commands and run:

```bash
git remote add origin https://github.com/<YOUR_USERNAME>/academic-literature-alert.git
git branch -M main
git push -u origin main
```

## Modify Topic Areas

Edit:

```text
config/topics.yml
```

Add or remove keywords under existing groups, or add a new group under `groups`. The scoring script uses these keywords to estimate category and relevance.

Default topic groups:

- `academic_publishing`
- `publishing_management`
- `digital_publishing`
- `game_and_interactive_publishing`
- `transferable_management_communication`
- `technology_frontier`

## Modify Journal Whitelists

Chinese journal whitelist:

```text
config/journals_zh.yml
```

Add entries like:

```yaml
- name: 新增期刊名
  quality_note: core status to be manually verified
```

English journal whitelist:

```text
config/journals_en.yml
```

Add entries under the relevant field:

```yaml
- journal: Example Journal
  quality_note: metrics to be manually verified
```

Do not add JCR, CiteScore, SJR, ABS, impact factor, CSSCI, AMI, or Peking University Core information unless it has been manually verified.

## Data Files

`data/pushed_records.csv` records:

```text
doi,title_hash,title,category,first_seen_date,pushed_date,source,status
```

Deduplication rules:

- Same DOI means duplicate.
- If DOI is missing, normalized title hash is used.
- The same item is not pushed again within 90 days.
- Classic highly cited English literature is not pushed again within 180 days.

`data/literature_cache.jsonl` stores raw retrieved metadata records.

## Development Notes

The fallback seed records exist only so dry-run tests can complete when open APIs are unavailable. They are marked with `source=fallback_seed` and missing metadata remains marked as missing.
