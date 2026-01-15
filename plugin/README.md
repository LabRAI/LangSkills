# Browser Plugin

MVP：Chrome Extension（检索 / 复制 library / 跳转到网站）。

默认读取 GitHub Pages 的 `index.json`：

- `https://shatianming5.github.io/skill_lain/index.json`

如果你看到 404，通常是因为 GitHub Pages 还没启用或还没部署：到仓库 `Settings → Pages` 把 Source 设为 **GitHub Actions**，然后等 `.github/workflows/build-site.yml` 跑完。

如果仓库是 **Private**，GitHub Pages 也可能不可用（表现为一直 404）；这时要么把仓库改成 Public，要么用下面的“本地联调”方式。

## 本地安装（Chrome）

1. 打开 `chrome://extensions/`
2. 打开右上角 **Developer mode**
3. 点击 **Load unpacked**
4. 选择目录：`plugin/chrome`

## 使用

- 在插件 popup 中搜索 skill
- 点击结果查看 `library.md` 并复制
- 点击 Open 打开网站详情页（使用 `#<id>` 定位）

## 本地联调（不依赖 Pages）

```bash
node scripts/build-site.js --out website/dist
node scripts/serve-site.js --dir website/dist --port 4173
```

然后在插件里把 Base URL 设为：`http://127.0.0.1:4173/`

> 站点由 `scripts/build-site.js` 构建并通过 `.github/workflows/build-site.yml` 部署到 GitHub Pages。
