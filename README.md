# Academic Literature Alert 中文说明

`academic-literature-alert` 是一个面向出版研究与管理研究的自动文献监测项目。它会定时检索开放学术数据源，对候选文献做严格筛选、去重、排序，并通过邮件推送高质量文献摘要。

它的目标不是“关键词命中就推送”，而是更接近一个轻量级的 Scholar-like 文献雷达：

```text
来源限定 -> 文献类型过滤 -> 黑名单排除 -> 元数据补全 -> 质量评分 -> 邮件推送
```

## ✨ 项目能做什么

- 🔎 从 OpenAlex、Semantic Scholar 等开放学术数据源检索英文文献元数据。
- 🎓 可选使用 SerpAPI Google Scholar API 做 Google Scholar-like 候选发现。
- 🧩 使用 Crossref 补充 DOI、题名、作者、年份、期刊等元数据，但不允许 Crossref-only 文献直接进入邮件。
- 📚 支持用户手动导入中文题录或受限数据库导出的 CSV/XLSX 文件。
- 🧠 按主题相关性、来源质量、发表时间、引用量、可迁移价值进行评分。
- 🚪 使用严格质量门，只推送 priority A/B 文献。
- 🧹 按 DOI 或标题 hash 去重，避免 daily 和 weekly 重复推送。
- ✉️ 渲染 Markdown 与 HTML 邮件，并通过 SMTP 发送。
- 🤖 支持 GitHub Actions 每日/每周自动运行。

## 🛡️ 合规边界

本项目只处理文献元数据，不下载全文 PDF，不绕过登录、付费墙、验证码或反爬机制。

明确不做：

- 不直接调用 ChatGPT 里的 Scholar GPT。
- 不直接爬取 Google Scholar 页面。
- 不直接爬取 CNKI、万方、维普等受限数据库页面。
- 不编造 DOI、摘要、引用量、期刊等级或影响因子。

Google Scholar-like 检索通过 SerpAPI Google Scholar API 实现。SerpAPI 结果只作为候选发现来源，必须经过 OpenAlex / Semantic Scholar / Crossref 补全和质量门过滤后，才可能进入邮件。

CNKI、万方、维普、Web of Science、Scopus、JCR 等受限来源仅支持用户手动导出的题录文件。

## 🧭 运行流程

```text
1. 读取主题配置
2. 检索开放数据源
3. 可选调用 SerpAPI Google Scholar API
4. 合并并补全文献元数据
5. 过滤图书章节、征稿、广告、未来年份等低质量记录
6. 计算主题相关性和综合评分
7. 去重
8. 生成邮件预览
9. 正式运行时发送邮件
10. 记录已推送文献
```

## 📁 项目结构

```text
academic-literature-alert/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── config/
│   ├── topics.yml
│   ├── journals_zh.yml
│   ├── journals_en.yml
│   ├── schedules.yml
│   ├── source_policy.yml
│   ├── exclusion_rules.yml
│   └── email.yml.example
├── data/
│   ├── pushed_records.csv
│   ├── literature_cache.jsonl
│   └── last_email_preview.md
├── logs/
│   └── .gitkeep
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
│   ├── run_pipeline.py
│   └── quality_gate_smoke_test.py
├── .github/
│   └── workflows/
│       ├── daily_literature.yml
│       └── weekly_literature.yml
├── requirements.txt
└── README.md
```

## 🚀 本地安装

进入项目目录：

```bash
cd "/Users/xueyeye/Documents/New project/academic-literature-alert"
```

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

如果遇到权限问题，可以改用：

```bash
python3 -m pip install --user -r requirements.txt
```

核心依赖包括：

```text
requests
PyYAML
```

## 🧪 本地测试与预览

运行质量门测试：

```bash
python3 scripts/quality_gate_smoke_test.py
```

生成 daily 预览，不发送邮件：

```bash
python3 scripts/run_pipeline.py --mode daily --dry-run
```

生成 weekly 预览，不发送邮件：

```bash
python3 scripts/run_pipeline.py --mode weekly --dry-run
```

跳过联网检索，只测试流程：

```bash
python3 scripts/run_pipeline.py --mode daily --dry-run --skip-network
```

使用用户手动导出的题录：

```bash
python3 scripts/run_pipeline.py --mode weekly --dry-run --manual-records path/to/exported_records.csv
```

邮件预览会写入：

```text
data/last_email_preview.md
```

## ✉️ 邮件配置

本地正式发送邮件前，需要设置环境变量：

```bash
export EMAIL_SENDER="your_sender@example.com"
export EMAIL_PASSWORD="your_smtp_password"
export EMAIL_RECEIVER="receiver@example.com"
export SMTP_HOST="smtp.example.com"
export SMTP_PORT="587"
```

注意：

- 不要把真实邮箱密码写入代码。
- 不要把 SMTP 密码写入 YAML。
- 不要提交任何 Secret、token、password。
- dry-run 只生成预览，不会发送邮件。
- 非 dry-run 模式缺少邮件变量会直接报错，不会静默跳过。

## 🎓 SerpAPI Scholar-like 检索

本项目支持通过 SerpAPI Google Scholar API 获取 Google Scholar-like 候选文献。

本地启用：

```bash
export SERPAPI_API_KEY="your_serpapi_key"
```

GitHub Actions 中启用，需要添加可选 Secret：

```text
SERPAPI_API_KEY
```

如果 `SERPAPI_API_KEY` 缺失：

- SerpAPI 检索会自动跳过。
- 流程不会报错。
- 项目会继续使用 OpenAlex、Semantic Scholar、手动导入等来源。

SerpAPI 使用策略在这里配置：

```text
config/source_policy.yml
```

关键参数：

```yaml
serpapi_google_scholar:
  enabled: true
  role: discovery_only
  allow_direct_email_push: false
  max_results_per_query: 10
```

含义是：SerpAPI 只负责发现候选，不允许直接推送；每个主题组最多生成 2 条 Scholar-style 查询，避免 API 消耗过大。

## 🚦 质量门规则

正式推送前，文献必须通过严格筛选。

daily 至少要求：

- priority 为 A 或 B。
- score 不低于 65。
- 期刊或来源明确。
- 不是 Crossref-only。
- 不是 uncategorized。
- 不是黑名单文献。
- 不是未来年份文献。
- 文献类型为 article / review / journal-article / review-article。

weekly 至少要求：

- priority 为 A 或 B。
- score 不低于 70。
- 期刊或来源明确。
- 中文文献来自手动导入或中文期刊白名单。
- 英文文献来自 SerpAPI、OpenAlex、Semantic Scholar、Publish or Perish 导出或英文期刊白名单。
- 不推 Crossref-only。
- 不推来源为“未获取”的内容。
- 不推征稿、广告、出版社介绍、会议宣传、图书章节。

黑名单配置在：

```text
config/exclusion_rules.yml
```

当前会排除：

- Francis Academic Press
- Clausius Scientific Press
- DOI 前缀 `10.61726`
- 征稿、投稿、会议通知、目录、序言、前言、广告、预刊等内容
- call for papers、publisher notice、preface、table of contents 等英文噪声项

## 🧠 主题配置

主题关键词在这里维护：

```text
config/topics.yml
```

当前覆盖方向包括：

- 学术出版
- 科技期刊治理
- 出版企业管理
- 数字出版
- 融合出版
- 智能出版
- 数据出版
- 知识服务
- 数字阅读
- 网络文学
- 有声书
- 知识付费
- 游戏出版
- 数字游戏产业
- 互动叙事
- 跨媒介叙事
- IP 开发
- 版权运营
- 出版平台治理
- 生成式 AI 与出版伦理

默认主题组：

```text
academic_publishing
publishing_management
digital_publishing
game_and_interactive_publishing
transferable_management_communication
technology_frontier
```

## 📚 期刊白名单

中文期刊白名单：

```text
config/journals_zh.yml
```

英文期刊白名单：

```text
config/journals_en.yml
```

这两个文件不只是“评分加分名单”，也是主动 discovery 的入口。每个期刊条目都应使用结构化配置，至少包含：

```yaml
- name: "Journal Name"
  language: en
  enabled: true
  aliases: []
  issn: ""
  eissn: ""
  openalex_source_id: ""
  source_id: ""
  quality_tags: []
  subject_tags: []
  discovery:
    use_openalex: true
    use_semantic_scholar: true
    use_cnki_import: false
    use_google_scholar_import: true
    use_official_site: false
  metadata_status: "unresolved"
  metadata_note: "Journal quality, indexing and ranking should be verified manually."
```

新增中文期刊示例：

```yaml
- name: 新增期刊名
  quality_note: core status to be manually verified
```

新增英文期刊示例：

```yaml
- journal: Example Journal
  quality_note: metrics to be manually verified
```

不要在没有人工核验的情况下写入 CSSCI、北大核心、AMI、JCR、CiteScore、SJR、ABS、影响因子等等级信息。

ISSN、eISSN 和 OpenAlex source_id 比期刊名称更可靠。期刊名称可能有缩写、改名、大小写或符号差异，而 source_id 可以直接定位 OpenAlex 的期刊来源，减少误抓。

解析期刊元数据：

```bash
python3 scripts/resolve_journal_metadata.py
```

解析报告位置：

```text
logs/journal_metadata_resolution_report.md
```

如果 OpenAlex 无法唯一确认期刊，脚本会保留空字段并标记 `metadata_status: unresolved`。不要手动编造 ISSN、OpenAlex source_id、影响因子或分区；无法解析的条目需要人工核验。

## 🕒 GitHub Actions 定时任务

daily workflow：

```text
.github/workflows/daily_literature.yml
```

- 北京时间约每天 08:30 运行。
- UTC cron：`30 0 * * *`
- 正式命令：`python scripts/run_pipeline.py --mode daily`
- 支持手动 dry-run。

weekly workflow：

```text
.github/workflows/weekly_literature.yml
```

- 北京时间约每周一 09:00 运行。
- UTC cron：`0 1 * * 1`
- 正式命令：`python scripts/run_pipeline.py --mode weekly`
- 支持手动 dry-run。
- weekly 无合格文献时，也会发送状态邮件：

```text
本周暂无符合筛选条件的高质量期刊论文。
```

## 🔐 GitHub Secrets

在 GitHub 仓库中打开：

```text
Settings -> Secrets and variables -> Actions
```

需要配置：

```text
EMAIL_SENDER
EMAIL_PASSWORD
EMAIL_RECEIVER
SMTP_HOST
SMTP_PORT
```

可选配置：

```text
SERPAPI_API_KEY
```

workflow 只会打印 `configured: yes/no`，不会打印 Secret 的真实值。

## 🧾 数据文件与去重

已推送记录：

```text
data/pushed_records.csv
```

字段：

```text
doi,title_hash,title,category,first_seen_date,pushed_date,source,status
```

检索缓存：

```text
data/literature_cache.jsonl
```

最近一次邮件预览：

```text
data/last_email_preview.md
```

去重规则：

- DOI 相同视为同一篇文献。
- DOI 缺失时使用规范化标题 hash。
- 普通文献 90 天内不重复推送。
- 经典高被引文献 180 天内不重复推送。
- daily 和 weekly 共用推送记录，避免互相重复。

## 📨 邮件内容字段

每篇进入邮件的文献至少包含：

- 标题
- 作者
- 年份
- 期刊或来源
- DOI
- URL
- 摘要
- 引用量
- 数据来源
- 推荐理由
- 与出版研究的关系
- 阅读优先级

缺失字段统一显示为：

```text
未获取
```

## 🧯 常见问题

### 为什么没有文献进入邮件？

这通常是正常现象。项目采用“宁缺毋滥”的质量门，如果候选文献来源不清、文献类型不对、缺少期刊、低相关或命中黑名单，就不会进入邮件。

### 为什么 dry-run 显示没有真实联网结果？

可能原因：

- 本地未安装 `requests` 或 `PyYAML`。
- 本地网络不可用。
- 没有配置 `SERPAPI_API_KEY`。
- 开放 API 暂时不可访问。

GitHub Actions 会先安装 `requirements.txt`，再运行检索。

### 为什么 Crossref 不能单独推送？

Crossref 更适合补充 DOI 和出版信息。仅凭 Crossref 宽泛关键词命中，容易混入征稿、图书章节、出版社广告或无关记录，因此 Crossref-only 文献默认被质量门排除。

### 为什么中文文献要手动导入或走白名单？

中文学术数据库通常有登录、版权和反爬限制。项目不直接爬取 CNKI 等平台，所以中文文献主要来自用户手动导出的题录或维护过的期刊白名单。

## 🧰 常用命令

查看仓库状态：

```bash
git status
```

运行 smoke test：

```bash
python3 scripts/quality_gate_smoke_test.py
```

生成 weekly 预览：

```bash
python3 scripts/run_pipeline.py --mode weekly --dry-run
```

提交修改：

```bash
git add README.md
git commit -m "docs: add Chinese README"
```

推送到 GitHub：

```bash
git push origin main
```

## 🪄 维护原则

- 不提交真实密码或 token。
- 不把 fallback metadata 当成真实文献推送。
- 不为了凑数量放宽质量门。
- 不编造摘要、DOI、引用量或期刊等级。
- 不直接爬取 Google Scholar 或 CNKI。
- 优先维护主题词、白名单和黑名单，让邮件越跑越干净。
