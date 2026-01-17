# 机场代码 IATA/ICAO：用公开数据集避免订票/行程混淆

## Goal
- 用公开数据（OurAirports + Wikidata/Wikipedia）查 IATA/ICAO 机场代码，并建立可复核的查询流程，减少行程/订票混淆。

## When to use
- 你需要把“城市/机场名称”转换成 IATA（3 字母）或 ICAO（4 字母）代码
- 你在同城多机场（例如东京/伦敦/纽约）场景下需要确认具体机场

## When NOT to use
- 你需要航司/票务系统的实时规则（代码共享/航站楼变更等）；应以航司与票务系统为准
- 你准备从不可信来源复制机场代码（先做数据集交叉验证）

## Prerequisites
- Environment: 任意可访问互联网的环境（或离线已有数据集）
- Permissions: 可下载公开数据集
- Tools: `curl`（可选）、`python3`（可选，用于快速筛选）
- Inputs needed: 城市/机场名称（中英文都可）、国家/地区（用于消歧）、需要的代码类型（IATA/ICAO）

## Steps (<= 12)
1. 明确要找的代码类型：IATA 常用于旅客/票务，ICAO 常用于航行/管制；先选对口径再查。[[2][3][4]]
2. 选用公开数据集做“第一层查询”：下载 OurAirports 的 `airports.csv`（包含 IATA/ICAO 字段）。`curl -L -o airports.csv https://ourairports.com/data/airports.csv`[[1]]
3. 用多个字段做消歧：优先用城市（municipality）、国家（iso_country）、机场名（name）交叉确认，避免只靠代码猜测。[[1]]
4. 同城多机场时输出候选列表：不要只取第一个匹配；把候选的 IATA/ICAO/城市/国家一起展示再人工确认。[[1]]
5. 需要更强校验时，用 Wikidata 按机场实体检查 IATA（P238）与 ICAO（P239）属性，并与数据集结果对照。[[2][3]]
6. 对“城市代码 vs 机场代码”保持警惕：一些 3 字母代码可能代表城市（多个机场集合）而不是单一机场。[[4]]
7. 把最终映射写入行程模板：例如 `city -> airport -> (IATA, ICAO) -> terminal`，并在订票前再次核对。[[4]]
8. 验收：随机抽样 3 个机场，用 OurAirports 查询结果再在 Wikidata 或 Wikipedia 复核一致性。[[1][2][4]]
9. 维护：定期更新数据集（OurAirports 会更新），不要长期使用旧 CSV。[[1]]

## Verification
- 用同一机场在 OurAirports 与 Wikidata 查询得到的 IATA/ICAO 一致
- 对同城多机场场景（例如伦敦/纽约），能列出多个候选并正确区分
- 输出的行程模板信息能回溯到数据来源（可复核）

## Safety & Risk
- Risk level: **low**
- Irreversible actions: 错误的机场代码可能导致订错城市/机场、误机或额外改签成本
- Privacy/credential handling: 行程文件可能包含个人信息（姓名/证件号/行程）；避免上传到公开仓库或共享群
- Confirmation requirement: 关键行程（跨国/转机）至少用两处独立来源交叉验证代码与机场名称

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] OurAirports data: https://ourairports.com/data/
- [2] Wikidata Property P238 (IATA airport code): https://www.wikidata.org/wiki/Property:P238
- [3] Wikidata Property P239 (ICAO airport code): https://www.wikidata.org/wiki/Property:P239
- [4] Wikipedia: IATA airport code: https://en.wikipedia.org/wiki/IATA_airport_code
