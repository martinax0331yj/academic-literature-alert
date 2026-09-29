# Literature Alert - daily - 2026-09-29

## Summary

- Items selected: 1
- Data sources: openalex
- Note: metadata-only alert. No full-text PDF is downloaded or attached.
- 本次运行时间: 2026-09-29T05:53:44Z
- 检索起点 since_date: 2026-07-01T05:53:44Z
- 检索截止 until_date: 2026-09-29T05:53:44Z
- 时间窗口策略: fallback_backfill_days
- 候选文献数: 216
- 最终推送数: 1
- selected_topic_distribution: {'technology_frontier': 1}
- selected_journal_distribution: {'Information Processing & Management': 1}

## 1. Automatic binary security classification of arabic mobile app reviews using transformer models and active learning

- 标题: Automatic binary security classification of arabic mobile app reviews using transformer models and active learning
- 作者: Taghreed Bagies
- 年份: 2026
- 期刊或来源: Information Processing & Management
- DOI: 10.1016/j.ipm.2026.105162
- URL: https://openalex.org/W7214556449
- 摘要: Mobile application user reviews provide valuable insights into user-reported issues, including security concerns that are critical for software engineering activities such as requirements analysis and system design. However, existing research has largely focused on English reviews and lacks systematic approaches for identifying security-related feedback in Arabic, a low-resource language in this domain. In this paper, we address this gap by developing an integrated approach for automated binary classification of security-related versus non-security-related Arabic mobile app reviews, grounded in a structured set of security requirement categories derived from software engineering literature. We collected 14,667,283 reviews from 56 mobile applications across multiple domains, including government, finance, and social platforms. Using natural language processing techniques and sentiment-based filtering, positive reviews were removed as a dataset-reduction step, while neutral and negative reviews were retained for subsequent analysis. To construct a high-quality labeled dataset, we developed an annotation approach combining keyword-guided sample selection, expert annotation, and iterative dataset refinement using active learning. During the active learning phase, semantic feature representations were generated using Low-Rank Adaptation-enhanced sentence transformers and combined with machine learning classifiers within an agreement-based active learning strategy to identify candidate samples for expert validation. The process was conducted over ten iterations, starting with 300 expert-annotated reviews and terminating when classifier performance stabilized. Following the stopping criterion, the final classifier-agreement samples were expert-validated and used to construct a held-out test set rather than being added to the training data. The active learning process resulted in a final training dataset of 10,632 expert-validated reviews. In addition, 1000 expert-validated reviews were reserved as a held-out test set and excluded from model training. The training dataset was used to fine-tune three transformer models, namely CAMeLBERT, MARBERT, and Paraphrase, for binary classification of security-related and non-security-related reviews. CAMeLBERT achieved the highest performance among the fine-tuned models, with 95.76% accuracy and 95.77% F1-score under 10-fold cross-validation and 91.20% accuracy and 91.16% F1-score on the held-out test set. To support practical adoption, we developed a web-based interface integrated with a large language model to enable real-time classification and provide interpretable explanations. The resulting dataset and developed approach contribute to advancing security-aware analysis of Arabic user-generated content and support software engineers in identifying security-related concerns in mobile application reviews.
- 引用量: 0
- 数据来源: openalex
- 推荐理由: priority B with score 62; matched topic technology_frontier; citation count 0
- 与出版研究的关系: Relevant to AI, data governance, recommendation systems, knowledge graphs, or technology-enabled publishing workflows.
- 阅读优先级: B (score: 62)
- Matched topics: technology_frontier
- Category: academic_publishing

## Compliance Note

This email contains metadata and short summaries only. Missing metadata is marked as 未获取 and not fabricated.
