# Examples

## 只导出需要的列
```sql
COPY (
  SELECT user_id, event_name, ts
  FROM read_parquet('events.parquet')
  WHERE ts >= '2026-01-01'
) TO 'events_2026.csv' (HEADER);
```

## 先验证再全量
```sql
SELECT * FROM read_csv_auto('data.csv') LIMIT 10;
```
