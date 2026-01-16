# Runner (long-running bots)

这个 runner 提供一个**可断点续跑**的队列执行器：按 `agents/configs/<domain>.yaml` 的 topics 列表逐个运行生成器，并把进度写到 `runs/<run-id>/state.json`。

## Why

- 支持机器人持续运行（天/周级）：循环处理 topics、可设置节流（sleep）、可中断后继续。
- 把“跑了多久/跑到哪/失败了什么”落到可审计的 state 文件，而不是只靠终端输出。

## Usage

```bash
# 1) 单次跑完一个 domain（生成 skeleton 或 capture，取决于 flags）
node agents/runner/run.js --domain linux --out skills --overwrite --capture --capture-strict

# 2) 长跑：无限循环（每个 topic 之间 sleep 30s；每轮结束 sleep 10min）
node agents/runner/run.js --domain linux --out skills --overwrite --capture \
  --loop --sleep-ms 30000 --cycle-sleep-ms 600000

# 3) 断点续跑：传同一个 run-id（state.json 存在则自动 resume）
node agents/runner/run.js --domain linux --run-id linux-weekly --out skills --overwrite --capture --loop
```

## State

- 默认写入：`runs/<run-id>/state.json`
- 关键字段：
  - `cycle`：第几轮循环
  - `cursor`：当前处理到 topics 列表的索引
  - `topics[]`：每个 topic 的 last_success/last_error/attempts 等信息

