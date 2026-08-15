import json, sys
d = json.load(sys.stdin)
paths = list(d['paths'].keys())
for p in paths:
    if 'analysis' in p:
        print(p)
