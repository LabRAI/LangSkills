# Library

## Download + quick lookup（Python）

```bash
curl -L -o airports.csv https://ourairports.com/data/airports.csv
```

```bash
python3 - <<'PY'
import csv
import sys

query = (sys.argv[1] if len(sys.argv) > 1 else "Tokyo").lower()
rows = []
with open("airports.csv", newline="", encoding="utf-8") as f:
    r = csv.DictReader(f)
    for row in r:
        name = (row.get("name") or "").lower()
        muni = (row.get("municipality") or "").lower()
        country = (row.get("iso_country") or "")
        iata = (row.get("iata_code") or "")
        icao = (row.get("ident") or "")
        if query in name or query in muni:
            rows.append((country, iata, icao, row.get("name") or "", row.get("municipality") or ""))

for country, iata, icao, name, muni in rows[:20]:
    print(f\"{country}\\t{iata}\\t{icao}\\t{name}\\t{muni}\")
PY
```

## Prompt snippet

```text
You are a travel planner. Given a city/airport name, write a cross-check workflow to find the correct IATA and ICAO codes using public datasets.
Constraints:
- Steps <= 12 with a verification step.
- Emphasize disambiguation for multi-airport cities.
```
