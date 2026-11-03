# Literature Alert - daily - 2026-11-03

## Summary

- Items selected: 1
- Data sources: openalex
- Note: metadata-only alert. No full-text PDF is downloaded or attached.
- 本次运行时间: 2026-11-03T07:01:03Z
- 检索起点 since_date: 2026-08-05T07:01:03Z
- 检索截止 until_date: 2026-11-03T07:01:03Z
- 时间窗口策略: fallback_backfill_days
- 候选文献数: 209
- 最终推送数: 1
- selected_topic_distribution: {'technology_frontier': 1}
- selected_journal_distribution: {'Marketing Science': 1}

## 1. Frontiers: Reducing Disparity Between LLMs and Humans: Optimal LLM Sample Calibration

- 标题: Frontiers: Reducing Disparity Between LLMs and Humans: Optimal LLM Sample Calibration
- 作者: Yan Leng, Yunxin Sang, Ashish Agarwal
- 年份: 2026
- 期刊或来源: Marketing Science
- DOI: 10.1287/mksc.2024.0983
- URL: https://openalex.org/W4395015967
- 摘要: Large language models (LLMs) are increasingly used to measure preferences and opinions, but outputs vary across prompts, personas, and model checkpoints, leaving analysts with multiple noisy elicitation variants and no principled way to combine them. Existing practice typically relies on heuristic aggregation---uniform averaging, population-weighted post-stratification, or selecting the single best subgroup---which uses fixed ex ante weights and can remain misaligned with human benchmarks. We propose Human Mimicry Calibration (HuMCal), a post-hoc calibration method that learns credibility weights over elicitation variants using only aggregate benchmark data, with no access to model internals or subgroup-level labels. HuMCal is model-agnostic and baseline-safe on the calibration split: its optimized loss weakly dominates any fixed-weight rule over the same subgroup set, including uniform weighting, post-stratification, and the best single subgroup. We evaluate HuMCal in a revealed-preference market-structure application using U.S. bank-card transactions and in a public-opinion application using Pew survey data. Across both settings, HuMCal improves alignment on the calibration split relative to all fixed-weight baselines. Out of sample, source-learned weights outperform heuristic baselines across time, geography, industry, and topic in the large majority of evaluations, although transfer is empirical rather than guaranteed. Recalibration with newer LLM checkpoints often improves alignment further. These results suggest that HuMCal can serve as a scalable calibration tool for LLM-based measurement when collecting fresh benchmark data for each target setting is costly.
- 引用量: 3
- 数据来源: openalex
- 推荐理由: priority B with score 61; matched topic technology_frontier; citation count 3
- 与出版研究的关系: Relevant to AI, data governance, recommendation systems, knowledge graphs, or technology-enabled publishing workflows.
- 阅读优先级: B (score: 61)
- Matched topics: technology_frontier
- Category: digital_publishing

## Compliance Note

This email contains metadata and short summaries only. Missing metadata is marked as 未获取 and not fabricated.
