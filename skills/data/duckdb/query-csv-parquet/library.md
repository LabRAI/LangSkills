# Library

## Copy-paste commands（从文件到结果文件）

```sql
-- 1) Read a CSV (auto-detect schema)
SELECT * FROM read_csv_auto('data.csv') LIMIT 5;

-- 2) Read a Parquet
SELECT count(*) FROM read_parquet('data.parquet');

-- 3) Persist to a table (optional)
CREATE TABLE t AS SELECT * FROM read_csv_auto('data.csv');

-- 4) Export results
COPY (SELECT * FROM t) TO 'out.parquet' (FORMAT 'parquet');
COPY (SELECT * FROM t) TO 'out.csv' (HEADER, DELIMITER ',');
```

## Prompt snippet

```text
You are a data engineer. Given a CSV/Parquet file path, write a DuckDB SQL workflow to inspect schema, query, and export results.
Constraints:
- Steps <= 12 with verification.
- Mention safety for PII and output paths.
```
