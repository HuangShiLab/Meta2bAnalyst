import json, sys
d = json.load(sys.stdin)
paths = d['paths']
for k in paths:
    if 'functional' in k.lower():
        print(k)
