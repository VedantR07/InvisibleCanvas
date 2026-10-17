import json
from pathlib import Path

p = Path("data/reports/cursor-20261012-201357.json")
d = json.loads(p.read_text(encoding="utf-8"))

print("TOP-LEVEL KEYS:", list(d.keys()))

def find_rows(obj):
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and "pipeline_ms" in obj[0]:
            return obj
        for item in obj:
            found = find_rows(item)
            if found:
                return found
    elif isinstance(obj, dict):
        for value in obj.values():
            found = find_rows(value)
            if found:
                return found
    return []

rows = find_rows(d)
print("TIMING ROWS:", len(rows))

for key in ("pipeline_ms", "inference_ms", "queue_ms"):
    values = sorted(float(r[key]) for r in rows if r.get(key) is not None)
    if values:
        def pct(q):
            return values[int((len(values) - 1) * q)]
        print(key, "p50:", round(pct(.50), 2),
              "p95:", round(pct(.95), 2),
              "p99:", round(pct(.99), 2),
              "max:", round(values[-1], 2))

print("\nSLOWEST FRAMES:")
slow = sorted(rows, key=lambda r: float(r.get("pipeline_ms") or 0), reverse=True)[:12]
for r in slow:
    print({k: r.get(k) for k in (
        "t", "pipeline_ms", "inference_ms", "queue_ms",
        "hand", "status", "source", "reason", "tip_valid"
    )})
