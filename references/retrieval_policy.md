# Retrieval Policy

This project retrieves and processes literature metadata only.

1. Do not crawl, download, or save full-text PDFs.
2. Do not bypass CNKI, Wanfang, VIP, Web of Science, Scopus, JCR, or any other database permission system.
3. Restricted databases are supported only through bibliographic files manually exported by the user.
4. If abstracts, DOI values, citation counts, journal impact factors, or rankings are missing, mark them as missing. Do not fabricate values.
5. All pushed records must preserve their data source.
6. If a data source fails, log the error and continue with other available sources.
7. Respect robots.txt, rate limits, API terms, and publisher website access policies.
8. Store credentials only in environment variables or GitHub Secrets.
