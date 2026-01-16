# Troubleshooting

## Fields are not split as expected
- 默认按空白分隔；CSV/TSV 请设置 `-F','` 或 `-F'\t'`。

## Numbers treated as strings
- 确认列中无逗号/单位；必要时先清洗或在 awk 中做转换。
