import re

# Read file
with open("/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend/app/services/agent_engine.py", "r") as f:
    content = f.read()

# Replace interpret_full_results method
old_method = '''    def interpret_full_results(
        self,
        all_results: Dict[str, Any],
        metadata_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Cross-analysis integrated interpretation using knowledge base.
        """
        interp = self.enhanced_interpreter.interpret_full(
            all_results=all_results,
            metadata_summary=metadata_summary,
        )
        return {
            "integrated_narrative": interp.integrated_narrative,
            "biological_context": interp.biological_context,
            "caveats": interp.caveats,
            "follow_up_suggestions": interp.follow_up_suggestions,
            "contradictions": interp.contradictions,
            "disease_relevance": interp.disease_relevance,
        }'''

new_method = '''    def interpret_full_results(
        self,
        all_results: Dict[str, Any],
        metadata_summary: Optional[Dict[str, Any]] = None,
        question: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cross-analysis integrated interpretation using knowledge base.
        Optional LLM enhancement for narrative quality.
        """
        interp = self.enhanced_interpreter.interpret_full(
            all_results=all_results,
            metadata_summary=metadata_summary,
            question=question,
        )
        return {
            "integrated_narrative": interp.integrated_narrative,
            "biological_context": interp.biological_context,
            "caveats": interp.caveats,
            "follow_up_suggestions": interp.follow_up_suggestions,
            "contradictions": interp.contradictions,
            "disease_relevance": interp.disease_relevance,
            "llm_enhanced": interp.llm_enhanced,
            "llm_model": interp.llm_model,
        }'''

if old_method in content:
    content = content.replace(old_method, new_method)
    print("Successfully modified interpret_full_results")
else:
    print("ERROR: Could not find interpret_full_results method")
    # Try to find it
    idx = content.find("def interpret_full_results")
    if idx >= 0:
        print(f"Found at index {idx}")
        print(content[idx:idx+500])

# Write back
with open("/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend/app/services/agent_engine.py", "w") as f:
    f.write(content)
