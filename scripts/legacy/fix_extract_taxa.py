import re

# Read file
with open("/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend/app/services/interpretation_engine.py", "r") as f:
    content = f.read()

# Replace _extract_significant_taxa to handle significant_features
old_method = '''    def _extract_significant_taxa(self, results: Dict) -> List[str]:
        """Extract all significant taxa names from differential results."""
        taxa = []
        for aname in ["differential", "lefse", "ancom", "deseq2", "aldex2", "maaslin2"]:
            r = results.get(aname, {}).get("result_data", {})
            if not r:
                continue
            top = r.get("top_feature") or r.get("top_taxa")
            if isinstance(top, str):
                taxa.append(top)
            elif isinstance(top, list):
                taxa.extend(top)
        # Also check taxonomy-bar top taxa
        tb = self._get_nested(results, "taxonomy-bar", "result_data", "statistics", "top_taxa")
        if isinstance(tb, list):
            taxa.extend(tb)
        # Deduplicate while preserving order
        seen = set()
        return [t for t in taxa if not (t in seen or seen.add(t))]'''

new_method = '''    def _extract_significant_taxa(self, results: Dict) -> List[str]:
        """Extract all significant taxa names from differential results."""
        taxa = []
        for aname in ["differential", "lefse", "ancom", "deseq2", "aldex2", "maaslin2"]:
            r = results.get(aname, {}).get("result_data", {})
            if not r:
                continue
            # Check top_feature / top_taxa
            top = r.get("top_feature") or r.get("top_taxa")
            if isinstance(top, str):
                taxa.append(top)
            elif isinstance(top, list):
                taxa.extend(top)
            # Check significant_features (LEfSe style: list of dicts with 'feature' key)
            sig_features = r.get("significant_features")
            if isinstance(sig_features, list):
                for feat in sig_features:
                    if isinstance(feat, dict):
                        fname = feat.get("feature")
                        if fname:
                            taxa.append(fname)
                    elif isinstance(feat, str):
                        taxa.append(feat)
        # Also check taxonomy-bar top taxa
        tb = self._get_nested(results, "taxonomy-bar", "result_data", "statistics", "top_taxa")
        if isinstance(tb, list):
            taxa.extend(tb)
        # Deduplicate while preserving order
        seen = set()
        return [t for t in taxa if not (t in seen or seen.add(t))]'''

if old_method in content:
    content = content.replace(old_method, new_method)
    print("Successfully patched _extract_significant_taxa")
else:
    print("ERROR: Could not find _extract_significant_taxa")

# Write back
with open("/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend/app/services/interpretation_engine.py", "w") as f:
    f.write(content)
