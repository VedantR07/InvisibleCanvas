import json
from pathlib import Path

p = Path("data/reports/cursor-20261012-204701.json")
if not p.exists():
    print("Report not found:", p)
    raise SystemExit(1)

d = json.loads(p.read_text(encoding="utf-8"))

for name in ("accuracy", "scene_check", "acquisition_stats", "motion", "options"):
    print(f"\n--- {name.upper()} ---")
    print(json.dumps(d.get(name), indent=2))

print("\n--- FRAME DIRECTORY ---")
print(d.get("frames_dir"))

records = d.get("records", [])
print("\n--- RECORD SUMMARY ---")
print("Total records:", len(records))
if records:
    print("First record:")
    print(json.dumps(records[0], indent=2))

accuracy = d.get("accuracy")
if isinstance(accuracy, dict):
    print("\n--- ACCURACY KEYS ---")
    print(list(accuracy.keys()))
