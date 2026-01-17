# Sources

> 每条来源需包含：URL、摘要、访问日期，以及它支撑了哪一步。
> 生成器会在本地缓存抓取结果（`.cache/`，默认不提交），这里记录抓取指纹用于审计。

## [1]
- URL: https://ourairports.com/data/
- Accessed: 2026-01-17
- Summary: OurAirports 提供 airports.csv 等公开机场数据（用于第一层查询与字段说明）。
- Supports: Steps 2-4, 8-9
- License: Public-Domain
- Fetch cache: miss
- Fetch bytes: 13278
- Fetch sha256: 8b0d0f8b21b7097340a0dbb1ccbb79fde3e832dc925a34f802142ad313dfaa0b

## [2]
- URL: https://www.wikidata.org/wiki/Property:P238
- Accessed: 2026-01-17
- Summary: Wikidata 的 IATA 机场代码属性（P238），用于交叉验证。
- Supports: Steps 1, 5, 8
- License: CC0-1.0
- Fetch cache: miss
- Fetch bytes: 148340
- Fetch sha256: 2a3f8ffddad2b525b71798919b509ff9a5d97a105062a7ce2ae056a0bb06ce14

## [3]
- URL: https://www.wikidata.org/wiki/Property:P239
- Accessed: 2026-01-17
- Summary: Wikidata 的 ICAO 机场代码属性（P239），用于交叉验证。
- Supports: Steps 1, 5, 8
- License: CC0-1.0
- Fetch cache: miss
- Fetch bytes: 157486
- Fetch sha256: 84377ed9c297a93cfe767c02dca7b24fba74e71ad0307a9b729814ca769eac9c

## [4]
- URL: https://en.wikipedia.org/wiki/IATA_airport_code
- Accessed: 2026-01-17
- Summary: IATA 机场代码的定义与注意事项（用于提醒城市代码/机场代码混淆与口径差异）。
- Supports: Steps 1, 6-8
- License: CC-BY-SA-4.0
- Fetch cache: miss
- Fetch bytes: 256873
- Fetch sha256: da93fe3b493a405e07e89c802801ed4d2426080b17a3a762a5a0b37d75cd2071
