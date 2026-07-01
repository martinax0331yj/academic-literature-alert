# Scoring Rules

Each item receives a score from 0 to 100.

| Dimension | Default Weight | Description |
| --- | ---: | --- |
| Topic relevance | 35 | Keyword and phrase match against `config/topics.yml`. |
| Source quality | 20 | Journal whitelist match or trusted open metadata source. |
| Recency | 15 | Recent literature receives more points; classic mode still allows older highly cited work. |
| Citation influence | 15 | Citation count or open reference-count proxies when available. Missing values are marked as missing. |
| Transferable value | 15 | Method, theory, platform, governance, AI, management, or communication relevance beyond the narrow source topic. |

Reading priority:

- A: score >= 75
- B: score >= 55 and < 75
- C: score < 55

Scoring is a triage aid. It is not a substitute for expert reading.
