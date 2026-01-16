# CLI

MVP：`search/open/copy`（基于仓库内 `skills/` 扫描生成索引，不依赖外部服务）。

## Usage

```bash
node cli/skill.js list
node cli/skill.js search find
node cli/skill.js show linux/filesystem/find-files
node cli/skill.js copy linux/filesystem/find-files
node cli/skill.js copy linux/filesystem/find-files --clipboard
node cli/skill.js open linux/filesystem/find-files
```

## Online（HTTP）

当你不想扫描本地 `skills/`（或希望从 GitHub Pages / 本地站点读取索引）时，给 CLI 传 `--base-url` / `--index-url`：

```bash
# 先本地起站点（或换成 GitHub Pages Base URL）
node scripts/build-site.js --out website/dist
node scripts/serve-site.js --dir website/dist --port 4173

# 用 HTTP index.json 搜索/查看
node cli/skill.js search find --base-url http://127.0.0.1:4173/
node cli/skill.js show linux/filesystem/find-files --file library --base-url http://127.0.0.1:4173/
```

