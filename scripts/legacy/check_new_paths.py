import json, sys
d = json.load(sys.stdin)
paths = list(d['paths'].keys())
for p in paths:
    if 'network' in p.lower() or 'correlation' in p.lower() or 'pathway' in p.lower():
        print(p)
