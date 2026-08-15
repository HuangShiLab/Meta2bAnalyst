import re

# Read file
with open("/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend/app/api/routes/agent.py", "r") as f:
    content = f.read()

# 1. Add question field to InterpretFullRequest
old_request = 'metadata_summary: Optional[Dict[str, Any]] = Field(default=None, description="Optional session metadata (n_samples, groups, etc.)")'
new_request = old_request + '\n    question: Optional[str] = Field(default=None, description="User specific question for targeted interpretation")'
content = content.replace(old_request, new_request)

# 2. Add llm fields to InterpretFullResponse
old_response = '''    disease_relevance: List[Dict[str, Any]]


@router.post("/interpret-full"'''
new_response = '''    disease_relevance: List[Dict[str, Any]]
    llm_enhanced: bool = False
    llm_model: Optional[str] = None


@router.post("/interpret-full"'''
content = content.replace(old_response, new_response)

# 3. Pass question to engine call
old_call = '''        result = engine.interpret_full_results(
            all_results=request.results,
            metadata_summary=request.metadata_summary,
        )'''
new_call = '''        result = engine.interpret_full_results(
            all_results=request.results,
            metadata_summary=request.metadata_summary,
            question=request.question,
        )'''
content = content.replace(old_call, new_call)

# Write back
with open("/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend/app/api/routes/agent.py", "w") as f:
    f.write(content)

print("Agent route modified successfully")
