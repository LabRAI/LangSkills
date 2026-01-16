# Website

MVP：静态站点（搜索 + 查看 + 一键复制 `library.md`），由 `scripts/build-site.js` 从 `skills/` 构建。

## Build

```bash
node scripts/build-site.js --out website/dist
```

构建完成后建议用本地 server 打开（直接双击 `index.html` 可能会因为浏览器限制导致 `fetch(index.json)` 失败）：

```bash
node scripts/serve-site.js --dir website/dist --port 4173
```

然后访问：

- `http://127.0.0.1:4173/`
