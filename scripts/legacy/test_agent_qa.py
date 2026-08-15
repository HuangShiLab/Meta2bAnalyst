#!/usr/bin/env python3
"""Test Agent interpret-full endpoint with multiple questions."""
import json
import sys
import requests

BASE_URL = "http://localhost:8000/api/v1"

def call_interpret_full(results, metadata=None):
    payload = {"results": results, "metadata_summary": metadata or {}}
    r = requests.post(f"{BASE_URL}/agent/interpret-full", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def q1_overview(interp):
    """Q1: 综合分析我的数据"""
    print("=" * 60)
    print("Q1: 综合分析我的数据")
    print("=" * 60)
    print(interp["integrated_narrative"])
    print()

def q2_contradiction(interp):
    """Q2: 为什么Alpha不显著但LEfSe找到了差异？"""
    print("=" * 60)
    print("Q2: 为什么Alpha不显著但LEfSe找到了差异？")
    print("=" * 60)
    if interp["contradictions"]:
        print("检测到的矛盾：")
        for c in interp["contradictions"]:
            print(f"  ⚠️ {c}")
    else:
        print("未检测到矛盾。")
        print()
        print("📚 知识库解读：")
        print("  Alpha diversity衡量的是'样本内有多少物种、分布多均匀'。")
        print("  LEfSe检测的是特定物种的丰度偏移。")
        print("  两者完全可能同时发生：整体复杂度不变，但具体物种替换了。")
        print("  这叫做「taxonomic substitution with functional redundancy」——")
        print("  功能冗余性：不同物种执行相似功能，维持整体生态功能。")
    print()

def q3_disease(interp):
    """Q3: 这些物种和什么疾病有关？"""
    print("=" * 60)
    print("Q3: 这些物种和什么疾病有关？")
    print("=" * 60)
    if interp["disease_relevance"]:
        for dr in interp["disease_relevance"][:5]:
            print(f"🏥 {dr['disease'].replace('_', ' ').upper()}")
            print(f"   匹配物种: {', '.join(dr['matched_taxa'])}")
            print(f"   描述: {dr['description'][:100]}...")
            print()
    else:
        print("未检测到显著的疾病关联。")
    print()

def q4_taxon(interp):
    """Q4: Faecalibacterium 是什么？"""
    print("=" * 60)
    print("Q4: Faecalibacterium 是什么？")
    print("=" * 60)
    for ctx in interp["biological_context"]:
        if "Faecalibacterium" in ctx:
            print(ctx)
            break
    print()

def q5_next_steps(interp):
    """Q5: 我应该下一步做什么？"""
    print("=" * 60)
    print("Q5: 我应该下一步做什么？")
    print("=" * 60)
    print("方法学注意事项：")
    for c in interp["caveats"][:5]:
        print(f"  ⚠️ {c}")
    print()
    print("后续建议：")
    for s in interp["follow_up_suggestions"]:
        print(f"  💡 {s}")
    print()

def main():
    with open("/Users/shihuang/Documents/kimi/workspace/meta2banalyst/demo_results.json", "r") as f:
        results = json.load(f)
    
    print("🧪 正在调用 /agent/interpret-full 端点...")
    interp = call_interpret_full(results, {"n_samples": 20, "data_type": "metagenomics"})
    print("✅ 成功获取知识库解读\n")
    
    q1_overview(interp)
    q2_contradiction(interp)
    q3_disease(interp)
    q4_taxon(interp)
    q5_next_steps(interp)

if __name__ == "__main__":
    main()
