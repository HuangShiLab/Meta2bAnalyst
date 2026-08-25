import json
from collections import Counter

# 读取 associations
associations = []
with open('knowledge_staging/associations.jsonl') as f:
    for line in f:
        if line.strip():
            associations.append(json.loads(line))

# 定义合并脚本中的黑名单
CONDITION_BLOCKLIST = {
    "healthy", "control", "female", "male", "elderly", "children",
    "chimpanzee", "mouse", "rat", "monkey", "human",
    "dry_food_diet", "wet_food_diet", "high_sugar_diet",
    "high_sugar_beverage_consumption", "high_sugar_high_fat_diet",
    "western_diet", "diet", "grana_padano_cheese_consumption",
    "high_carbohydrate_intake", "high_sugar_intake",
    "gingival_bleeding", "high_bleeding_on_probing", "tooth_pain",
    "dental_calculus", "plaque_index", "pocket_depth",
    "high_s_cristatus_p_gingivalis_ratio", "low_s_cristatus_p_gingivalis_ratio",
    "high_streptococcus_cristatus_to_porphyromonas_gingivalis_ratio",
    "low_streptococcus_cristatus_to_porphyromonas_gingivalis_ratio",
    "cigarette_smoking", "smoking",
    "captivity",
    "elderly_individuals", "elderly_non_diabetic", "old_age", "young_individuals", "females",
    "high_body_mass_index", "high_bacterial_count", "high_salivary_flow_rate",
    "low_socioeconomic_status", "low_water_intake", "low_salivary_ph",
    "stimulated_saliva", "unstimulated_saliva",
    "ro_water", "underground_water",
    "non_vegetarian", "vegetarian",
    "highly_trained_athlete",
    "post_bariatric_surgery",
    "post_fluoride_varnish_treatment", "post_chlorhexidine_recovery",
    "post_routine_oral_care", "post_oral_health_promotion_program",
    "post_sucrose_rinse", "post_disinfection",
    "edta_treatment", "uv_treatment", "uv_and_sodium_hypochlorite_treatment",
    "sodium_hypochlorite_treatment", "chlorhexidine_treatment",
    "fixed_orthodontic_appliance_treatment", "orthodontic_treatment",
    "endotracheal_intubation",
    "myelosuppressive_chemotherapy",
    "elane_associated_neutropenia",
    "untreated",
    "caries_free", "healthy_periodontal_conditions", "poor_oral_health", "poor_health",
    "ancient_calculus",
    "black_stain_caries_free", "severe_early_childhood_caries_with_black_stain",
    "periodontal_treatment", "periodontal_health", "periodontal_pocket_depth",
    "subgingival_plaque",
    "cerebral_palsy_severe_dental_caries", "cerebral_palsy_dental_caries",
    "cerebral_palsy_dental_health",
    "overweight_irritable_bowel_syndrome",
    "chlorhexidine_resistance", "triclosan_resistance",
    "sodium_hypochlorite_resistance", "erythromycin_resistance", "tetracycline_resistance",
}

def normalize_condition(cond):
    key = str(cond or "").strip().lower().replace(" ", "_").replace("-", "_")
    return key

blocked = Counter()
for assoc in associations:
    cond = normalize_condition(assoc.get('condition'))
    if cond in CONDITION_BLOCKLIST:
        blocked[cond] += 1

print("=== 被过滤的非疾病条件 (top 30) ===")
for cond, count in blocked.most_common(30):
    print(f"  {cond}: {count}")

print(f"\nTotal blocked: {sum(blocked.values())}")

# 检查不在黑名单中的条件
all_conditions = Counter()
for assoc in associations:
    cond = normalize_condition(assoc.get('condition'))
    all_conditions[cond] += 1

unmatched = [(c, n) for c, n in all_conditions.items() if c not in CONDITION_BLOCKLIST]
print(f"\n=== 不在黑名单中的条件 ({len(unmatched)} 个) ===")
for cond, count in sorted(unmatched, key=lambda x: -x[1])[:30]:
    print(f"  {cond}: {count}")
