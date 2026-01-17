# Docker（可选）

本仓库没有额外依赖（不需要 `npm install`），因此可以用 Docker 快速把运行环境固定为 Node.js 20，并在容器里跑 bots / 自检。

## 快速开始

```bash
docker build -t langskills .
docker run --rm -it langskills
```

默认会运行离线自检（等价于 `node scripts/self-check.js --m0 --skip-remote`）。

## 运行 orchestrator（长跑）

建议把 `skills/`、`runs/`、`.cache/` 挂载出来，方便断点续跑与复用缓存：

```bash
docker run --rm -it \
  -v "$PWD/skills:/app/skills" \
  -v "$PWD/runs:/app/runs" \
  -v "$PWD/.cache:/app/.cache" \
  langskills \
  node agents/orchestrator/run.js --domain linux --run-id linux-docker --loop
```

## 多 bot 并发（docker-compose）

示例见 `docker-compose.yml`（linux + integrations 两个 orchestrator），启动：

```bash
docker compose up --build
```

