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

