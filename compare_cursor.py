import json
from pathlib import Path
from statistics import median

d = json.loads(Path("data/reports/cursor-20261012-201357.json").read_text(encoding="utf-8"))
rows = d["records"]
print("Records:", len(rows))

for label, subset in [
    ("HAND DETECTED", [r for r in rows if r.get("hand")]),
    ("HAND NOT DETECTED", [r for r in rows if not r.get("hand")]),
    ("ALL FRAMES", rows),
]:
    print("\n" + label, "count =", len(subset))
    for key in ("pipeline_ms", "inference_ms", "queue_ms"):
        vals = sorted(float(r[key]) for r in subset if r.get(key) is not None)
        if vals:
            print(
                key,
                "median =", round(median(vals), 2),
                "p95 =", round(vals[int((len(vals)-1)*.95)], 2),
                "max =", round(max(vals), 2)
            )

print("\nAcquisition statistics:")
print(json.dumps(d.get("acquisition_stats"), indent=2))
