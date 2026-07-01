# Literature Alert Email Template

Subject:

```text
[Literature Alert] {{ mode }} digest - {{ run_date }}
```

Body:

```markdown
# Literature Alert - {{ mode }} - {{ run_date }}

## Summary

- Items selected: {{ item_count }}
- Data sources: {{ sources }}
- Note: metadata-only alert. No full-text PDF is downloaded or attached.

{% for item in items %}
## {{ loop.index }}. {{ item.title }}

- Priority: {{ item.priority }} (score: {{ item.score }})
- Category: {{ item.category }}
- Authors: {{ item.authors }}
- Year/date: {{ item.year }}
- Venue: {{ item.venue }}
- DOI/URL: {{ item.link }}
- Source: {{ item.source }}
- Abstract: {{ item.abstract }}
- Recommendation: {{ item.recommendation_reason }}
- Research relation: {{ item.research_relation }}

{% endfor %}

## Compliance Note

This email contains metadata and short summaries only. Missing metadata is marked as missing and not fabricated.
```
