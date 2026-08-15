import sys

path = sys.argv[1]
with open(path, 'r') as f:
    content = f.read()

# Add helper function after logger = logging.getLogger(__name__)
helper = '''

def _sanitize_json(obj):
    """Recursively convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, (np.bool_, np.bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return _sanitize_json(obj.to_dict(orient='records'))
    if isinstance(obj, pd.Series):
        return _sanitize_json(obj.to_dict())
    return obj
'''

# Insert after logger line
old = 'logger = logging.getLogger(__name__)\n\n# '
new = 'logger = logging.getLogger(__name__)' + helper + '\n\n# '
content = content.replace(old, new)

# Now wrap the result return with _sanitize_json
old_return = '''    result = {
        "method": method,
        "quality_metrics": quality_metrics,
        "ko_abundance": ko_abundance.to_dict(orient="split") if not ko_abundance.empty else {},
        "pathway_abundance": pathway_abundance.reset_index().to_dict(orient="records")
        if not pathway_abundance.empty else [],
        "taxon_metadata": taxon_metadata.to_dict(orient="records"),
        "plots": plots,
        "differential": diff_results,
    }

    logger.info("Functional prediction complete")
    return result'''

new_return = '''    result = _sanitize_json({
        "method": method,
        "quality_metrics": quality_metrics,
        "ko_abundance": ko_abundance.to_dict(orient="split") if not ko_abundance.empty else {},
        "pathway_abundance": pathway_abundance.reset_index().to_dict(orient="records")
        if not pathway_abundance.empty else [],
        "taxon_metadata": taxon_metadata.to_dict(orient="records"),
        "plots": plots,
        "differential": diff_results,
    })

    logger.info("Functional prediction complete")
    return result'''

content = content.replace(old_return, new_return)

with open(path, 'w') as f:
    f.write(content)
print('Done')
