# DuckDB：用 SQL 直接查询 CSV/Parquet 并导出结果

## Goal
- 不写复杂 ETL，直接用 DuckDB 的表函数读 CSV/Parquet，用 SQL 做筛选/聚合，并把结果导出为 CSV/Parquet。

## When to use
- 你手上只有一个/几个数据文件（CSV/Parquet），想快速做探索性查询
- 你需要把查询结果导出成新的文件给下游系统/分析用

## When NOT to use
- 数据量巨大且需要持续增量（更适合把数据落仓/用专门的调度与分区策略）
- 你不清楚数据是否包含敏感信息但准备随意复制/上传（先做数据治理与脱敏）

## Prerequisites
- Environment: 本地 shell 或可运行 DuckDB 的环境
- Permissions: 读写输入/输出文件路径权限
- Tools: DuckDB（CLI 或任意驱动）
- Inputs needed: 数据文件路径（CSV/Parquet）、目标输出格式与路径、预期的行数/字段

## Steps (<= 12)
1. 启动 DuckDB：`duckdb`（或 `duckdb <db-file>` 让查询结果可持久化）[[1]]
2. 直接查询 CSV：`SELECT * FROM read_csv_auto('data.csv') LIMIT 5;`[[1]]
3. 在正式聚合前先确认 schema：`DESCRIBE SELECT * FROM read_csv_auto('data.csv');`[[1]]
4. 查询 Parquet：`SELECT count(*) FROM read_parquet('data.parquet');`[[2]]
5. 需要复用结果时落表：`CREATE TABLE t AS SELECT * FROM read_csv_auto('data.csv');`[[1]]
6. 导出 Parquet（推荐用于分析/列式存储）：`COPY (SELECT * FROM t) TO 'out.parquet' (FORMAT 'parquet');`[[3]]
7. 导出 CSV（给通用工具/表格软件）：`COPY (SELECT * FROM t) TO 'out.csv' (HEADER, DELIMITER ',');`[[3]]
8. 验收：对比行数与字段：`SELECT count(*) FROM t;` + `PRAGMA table_info('t');`[[1]]

## Verification
- `LIMIT` 抽样结果字段/值符合预期（编码、日期、空值）
- `count(*)` 与你对数据规模的预期一致（或能解释差异）
- 导出的 `out.csv/out.parquet` 能被下游工具正确读取

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 覆盖写出文件可能丢失旧结果；导出前检查输出路径是否正确
- Privacy/credential handling: 不要把包含 PII/密钥的数据文件导出到共享目录或提交到仓库
- Confirmation requirement: 在导出前先用 `LIMIT` 与 `DESCRIBE` 做抽样确认，再跑全量聚合/导出

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] DuckDB docs: CSV Overview: https://duckdb.org/docs/data/csv/overview.html
- [2] DuckDB docs: Parquet Overview: https://duckdb.org/docs/data/parquet/overview.html
- [3] DuckDB docs: COPY statement: https://duckdb.org/docs/sql/statements/copy.html
