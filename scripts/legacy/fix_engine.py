import sys

path = sys.argv[1]
with open(path, 'r') as f:
    content = f.read()

# Fix 1: run_pcoa 'coordinates' -> 'samples' (2 occurrences)
content = content.replace(
    "pcoa_result['coordinates'].to_dict(orient='index')",
    "pcoa_result['samples'].to_dict(orient='index')"
)
content = content.replace(
    "pcoa_result['coordinates'].index",
    "pcoa_result['samples'].index"
)

# Fix 2: Add wrapper functions at end if not present
wrapper = '''

def run_network_analysis(df, metadata_df=None, parameters=None):
    from app.services.network_analysis import run_network_analysis as _run
    return _run(df, **(parameters or {}))


def run_correlation_analysis(df, metadata_df=None, parameters=None):
    from app.services.correlation_analysis import run_correlation_analysis as _run
    return _run(df, metadata_df, parameters)


def run_pathway_analysis(df, metadata_df=None, parameters=None):
    from app.services.functional_analysis import run_pathway_analysis as _run
    return _run(df, metadata_df, parameters)
'''

if 'def run_network_analysis(' not in content:
    content = content.rstrip() + '\n' + wrapper

with open(path, 'w') as f:
    f.write(content)

print('Done')
