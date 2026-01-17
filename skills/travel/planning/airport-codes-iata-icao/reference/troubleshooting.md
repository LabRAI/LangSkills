# Troubleshooting

## 查不到 IATA 代码
- 可能原因：小机场没有 IATA；或字段为空
- 处理：改用 ICAO/ident 字段；必要时用 Wikidata/Wikipedia 交叉确认

## 同名城市命中太多
- 处理：增加国家/地区条件（iso_country），并优先用机场全名而非简称

## 订票系统显示的代码不同
- 处理：以航司/票务系统为准；检查是否是“城市代码（多机场集合）”而非单一机场
