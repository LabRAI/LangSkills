# Adapters (source → doc items)

Adapters 把“爬哪里”抽象为统一接口，便于 scale 到更多内容源（Q6）。

## Interface (concept)

- `discover(source) -> DocItem[]`：枚举可处理的文档对象（URL、文件、API endpoint 等）
- `fetch(docItem) -> RawSnapshot`：抓取原始内容并记录元信息（etag/last-modified/git sha）
- `parse(raw) -> ParsedDoc`：抽取结构（标题层级、代码块、参数表等）
- `extractCandidates(parsed) -> TopicCandidate[]`：从文档结构推导可形成 skill 的任务点

本 repo 当前实现了：

- `http_seed_crawl`：`agents/crawler/run.js`（seeds→发现→去重→入队；写 state/log；缓存写 `.cache/web`）

后续可扩展（先给骨架，不强依赖第三方库）：

- `github_repo`：按 include globs 枚举 markdown/skill 文件；按 commit 增量刷新
- `sitemap_docs`：读 `sitemap.xml` 枚举页面；按 URL pattern 过滤
- `openapi`：endpoint/operation/params/errors → candidates
- `manpage`：SYNOPSIS/OPTIONS/EXAMPLES → candidates

