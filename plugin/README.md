# Browser Plugin

MVP：Chrome Extension（检索 / 复制 library / 跳转到网站）。

默认读取本地站点的 `index.json`（推荐用于开发与演示）：

- `http://127.0.0.1:4173/index.json`

如果你希望读取 GitHub Pages 的部署产物：到仓库 `Settings → Pages` 把 Source 设为 **GitHub Actions**，然后等 `.github/workflows/build-site.yml` 跑完；再在插件里把 Base URL 设为：

- `https://labrai.github.io/LangSkills/`（对应 `https://labrai.github.io/LangSkills/index.json`）

如果仓库是 **Private**，GitHub Pages 也可能不可用（表现为一直 404）；这时用下面的“本地联调”方式即可。

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

默认 Base URL 就是：`http://127.0.0.1:4173/`（如你改过，可在插件里再设回）

> 站点由 `scripts/build-site.js` 构建并通过 `.github/workflows/build-site.yml` 部署到 GitHub Pages。
