#!/usr/bin/env python3
import json
import sys
sys.path.insert(0, '/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend')

from app.services.interpretation_engine import EnhancedInterpreter

with open('/Users/shihuang/Documents/kimi/workspace/meta2banalyst/demo_results.json', 'r') as f:
    results = json.load(f)

interp = EnhancedInterpreter()
out = interp.interpret_full(results, metadata_summary={"n_samples": 20})

print("=" * 60)
print("INTEGRATED NARRATIVE")
print("=" * 60)
print(out.integrated_narrative)

print("\n" + "=" * 60)
print("CONTRADICTIONS")
print("=" * 60)
for c in out.contradictions:
    print(f"- {c}")

print("\n" + "=" * 60)
print("BIOLOGICAL CONTEXT")
print("=" * 60)
for b in out.biological_context:
    print(f"- {b}\n")

print("\n" + "=" * 60)
print("DISEASE RELEVANCE")
print("=" * 60)
for d in out.disease_relevance:
    print(f"- {d['disease']}: matched {d['matched_taxa']}")

print("\n" + "=" * 60)
print("CAVEATS")
print("=" * 60)
for c in out.caveats:
    print(f"- {c}")

print("\n" + "=" * 60)
print("FOLLOW-UP SUGGESTIONS")
print("=" * 60)
for s in out.follow_up_suggestions:
    print(f"- {s}")
