"""Expand taxon_db.json and disease_db.json with literature-established entries.

Merges only NEW keys; existing entries are never overwritten.
Associations follow well-replicated human microbiome literature (GMrepo,
Disbiome, curated review consensus); direction is stated conservatively.
"""
import json
from pathlib import Path

KB = Path(__file__).resolve().parent.parent / "app" / "knowledge"

NEW_TAXA = {
    # ── Additional beneficial / commensal gut taxa ──────────────
    "Bifidobacterium_breve": {
        "gram_stain": "Gram-positive", "oxygen": "anaerobic",
        "main_products": ["acetate", "lactate"],
        "known_functions": ["SCFA_production", "infant_gut_colonization", "immune_modulation"],
        "disease_associations": {
            "allergic_diseases": "depleted", "irritable_bowel_syndrome": "depleted",
            "obesity": "depleted", "antibiotic_associated_diarrhea": "depleted",
        },
        "health_markers": ["infant_health", "anti_inflammation"],
        "notes": "Dominant in the infant gut; consumes human milk oligosaccharides and supports early immune education.",
    },
    "Bifidobacterium_bifidum": {
        "gram_stain": "Gram-positive", "oxygen": "anaerobic",
        "main_products": ["acetate", "lactate"],
        "known_functions": ["mucin_degradation", "cross_feeding", "immune_modulation"],
        "disease_associations": {
            "irritable_bowel_syndrome": "depleted", "allergic_diseases": "depleted",
        },
        "health_markers": ["gut_barrier_integrity"],
        "notes": "Mucin degrader whose acetate cross-feeds butyrate producers; common probiotic ingredient.",
    },
    "Lactiplantibacillus_plantarum": {
        "gram_stain": "Gram-positive", "oxygen": "facultatively_anaerobic",
        "main_products": ["lactate"],
        "known_functions": ["fermentation", "bacteriocin_production", "gut_barrier_support"],
        "disease_associations": {
            "irritable_bowel_syndrome": "depleted", "inflammatory_bowel_disease": "depleted",
        },
        "health_markers": ["anti_inflammation", "pathogen_exclusion"],
        "notes": "Formerly Lactobacillus plantarum; widely used probiotic with evidence in IBS symptom relief.",
    },
    "Lacticaseibacillus_casei": {
        "gram_stain": "Gram-positive", "oxygen": "facultatively_anaerobic",
        "main_products": ["lactate"],
        "known_functions": ["fermentation", "immune_modulation"],
        "disease_associations": {
            "antibiotic_associated_diarrhea": "depleted",
        },
        "health_markers": ["pathogen_exclusion"],
        "notes": "Formerly Lactobacillus casei; probiotic with trial evidence for preventing antibiotic-associated diarrhea.",
    },
    "Bacteroides_vulgatus": {
        "gram_stain": "Gram-negative", "oxygen": "strictly_anaerobic",
        "main_products": ["succinate", "propionate", "acetate"],
        "known_functions": ["polysaccharide_degradation", "LPS_weak_endotoxin"],
        "disease_associations": {
            "inflammatory_bowel_disease": "enriched", "type_2_diabetes": "mixed",
        },
        "health_markers": [],
        "notes": "Common commensal; reported enriched in IBD and associated with insulin resistance in some cohorts.",
    },
    "Bacteroides_dorei": {
        "gram_stain": "Gram-negative", "oxygen": "strictly_anaerobic",
        "main_products": ["succinate", "acetate"],
        "known_functions": ["polysaccharide_degradation", "LPS_weak_endotoxin"],
        "disease_associations": {
            "type_1_diabetes_autoimmunity": "enriched", "atherosclerosis": "enriched",
        },
        "health_markers": [],
        "notes": "Produces a weakly inflammatory LPS; linked to type 1 diabetes autoimmunity in longitudinal infant cohorts.",
    },
    "Dorea_formicigenerans": {
        "gram_stain": "Gram-positive", "oxygen": "strictly_anaerobic",
        "main_products": ["formate", "acetate", "lactate"],
        "known_functions": ["SCFA_production"],
        "disease_associations": {
            "irritable_bowel_syndrome": "enriched", "inflammatory_bowel_disease": "mixed",
        },
        "health_markers": [],
        "notes": "Gas-producing commensal repeatedly reported enriched in IBS cohorts.",
    },
    "Butyricicoccus_pullicaecorum": {
        "gram_stain": "Gram-positive", "oxygen": "strictly_anaerobic",
        "main_products": ["butyrate"],
        "known_functions": ["SCFA_production", "anti_inflammatory"],
        "disease_associations": {
            "inflammatory_bowel_disease": "depleted", "colorectal_cancer": "depleted",
        },
        "health_markers": ["butyrate_production", "anti_inflammation"],
        "notes": "Butyrate producer depleted in IBD; investigated as a live biotherapeutic.",
    },
    "Lachnospira_multipara": {
        "gram_stain": "Gram-positive", "oxygen": "strictly_anaerobic",
        "main_products": ["acetate", "butyrate"],
        "known_functions": ["pectin_degradation", "SCFA_production"],
        "disease_associations": {
            "allergic_diseases": "depleted", "asthma": "depleted",
        },
        "health_markers": ["fibre_fermentation"],
        "notes": "Pectin-degrading SCFA producer; early-life abundance inversely associated with asthma risk.",
    },
    "Adlercreutzia_equolifaciens": {
        "gram_stain": "Gram-positive", "oxygen": "strictly_anaerobic",
        "main_products": ["equol"],
        "known_functions": ["isoflavone_metabolism", "equol_production"],
        "disease_associations": {
            "cardiovascular_disease": "depleted", "metabolic_syndrome": "depleted",
        },
        "health_markers": ["equol_production"],
        "notes": "Converts soy daidzein to equol; carrier status linked to cardiometabolic benefit of soy.",
    },
    "Ruminococcus_torques": {
        "gram_stain": "Gram-positive", "oxygen": "strictly_anaerobic",
        "main_products": ["acetate", "formate"],
        "known_functions": ["mucin_degradation"],
        "disease_associations": {
            "inflammatory_bowel_disease": "enriched", "irritable_bowel_syndrome": "enriched",
        },
        "health_markers": [],
        "notes": "Mucin degrader reported enriched in IBD; may erode the mucus layer when fibre is scarce.",
    },
    "Clostridium_perfringens": {
        "gram_stain": "Gram-positive", "oxygen": "anaerobic",
        "main_products": ["acetate", "butyrate", "toxins"],
        "known_functions": ["toxin_production", "food_poisoning"],
        "disease_associations": {
            "antibiotic_associated_diarrhea": "enriched", "necrotizing_enterocolitis": "enriched",
        },
        "health_markers": [],
        "notes": "Toxigenic pathobiont; high abundance signals food-borne gastroenteritis or neonatal risk.",
    },
    # ── Oral / skin / vaginal niches ────────────────────────────
    "Streptococcus_mutans": {
        "gram_stain": "Gram-positive", "oxygen": "facultatively_anaerobic",
        "main_products": ["lactate"],
        "known_functions": ["acid_production", "biofilm_formation", "dental_caries"],
        "disease_associations": {
            "dental_caries": "enriched",
        },
        "health_markers": [],
        "notes": "Primary cariogenic species; acidifies dental plaque biofilms and demineralises enamel.",
    },
    "Porphyromonas_gingivalis": {
        "gram_stain": "Gram-negative", "oxygen": "strictly_anaerobic",
        "main_products": ["butyrate", "propionate", "gingipains"],
        "known_functions": ["proteolysis", "immune_evasion", "biofilm_formation"],
        "disease_associations": {
            "periodontal_disease": "enriched", "alzheimers_disease": "enriched",
        },
        "health_markers": [],
        "notes": "Keystone periodontal pathogen; gingipains detected in Alzheimer's brain tissue in some studies.",
    },
    "Cutibacterium_acnes": {
        "gram_stain": "Gram-positive", "oxygen": "aerotolerant_anaerobic",
        "main_products": ["propionate"],
        "known_functions": ["sebum_metabolism", "skin_barrier"],
        "disease_associations": {
            "acne_vulgaris": "mixed",
        },
        "health_markers": ["skin_health"],
        "notes": "Dominant skin commensal; specific phylotypes, not overall abundance, associate with acne.",
    },
    "Lactobacillus_crispatus": {
        "gram_stain": "Gram-positive", "oxygen": "facultatively_anaerobic",
        "main_products": ["lactate"],
        "known_functions": ["vaginal_acidification", "pathogen_exclusion"],
        "disease_associations": {
            "bacterial_vaginosis": "depleted",
        },
        "health_markers": ["vaginal_health"],
        "notes": "Hallmark of the healthy vaginal community (CST I); displaced by anaerobes in bacterial vaginosis.",
    },
    "Gardnerella_vaginalis": {
        "gram_stain": "Gram-variable", "oxygen": "facultatively_anaerobic",
        "main_products": ["acetate", "succinate"],
        "known_functions": ["biofilm_formation", "sialidase_activity"],
        "disease_associations": {
            "bacterial_vaginosis": "enriched",
        },
        "health_markers": [],
        "notes": "Core member of BV biofilms; sialidase activity degrades protective mucins.",
    },
    # ── Additional gut commensals / biomarkers ──────────────────
    "Blautia_obeum": {
        "gram_stain": "Gram-positive", "oxygen": "strictly_anaerobic",
        "main_products": ["acetate", "lactate"],
        "known_functions": ["SCFA_production", "bacteriocin_production"],
        "disease_associations": {
            "obesity": "mixed", "colorectal_cancer": "depleted",
        },
        "health_markers": ["anti_inflammation"],
        "notes": "Acetate producer with context-dependent associations; often inversely linked to visceral fat.",
    },
    "Coprobacter_fastidiosus": {
        "gram_stain": "Gram-negative", "oxygen": "strictly_anaerobic",
        "main_products": ["acetate", "succinate"],
        "known_functions": ["polysaccharide_degradation"],
        "disease_associations": {
            "type_2_diabetes": "depleted",
        },
        "health_markers": ["metabolic_health"],
        "notes": "Emerging commensal inversely associated with type 2 diabetes in metagenomic cohorts.",
    },
    "Oscillospira_guillermondii": {
        "gram_stain": "Gram-positive", "oxygen": "strictly_anaerobic",
        "main_products": ["butyrate"],
        "known_functions": ["fibre_fermentation", "SCFA_production"],
        "disease_associations": {
            "inflammatory_bowel_disease": "depleted", "obesity": "depleted",
        },
        "health_markers": ["leanness", "fibre_fermentation"],
        "notes": "Heritable, fibre-associated genus repeatedly linked to leanness; difficult to culture.",
    },
}

NEW_DISEASES = {
    "irritable_bowel_syndrome": {
        "indicators": [
            "alpha_diversity_mildly_decreased", "Bifidobacterium_depleted",
            "Dorea_enriched", "Ruminococcus_gnavus_enriched", "SCFA_producers_reduced",
        ],
        "key_genera": ["Bifidobacterium", "Faecalibacterium", "Dorea", "Ruminococcus", "Lactobacillus"],
        "functional_shift": ["SCFA_profile_shifted", "bile_acid_pool_altered", "gut_barrier_permeability_increased"],
        "description": "IBS microbiome shows mild diversity loss, depletion of Bifidobacterium and butyrate producers, and enrichment of gas-producing Dorea/Ruminococcus; subtype (IBS-D vs IBS-C) profiles differ.",
    },
    "metabolic_syndrome": {
        "indicators": [
            "Akkermansia_muciniphila_depleted", "gene_richness_decreased",
            "LPS_producers_enriched", "SCFA_production_altered",
        ],
        "key_genera": ["Akkermansia", "Faecalibacterium", "Bacteroides", "Escherichia", "Prevotella"],
        "functional_shift": ["metabolic_endotoxemia", "LPS_translocation_increased", "energy_harvest_enhanced"],
        "description": "Metabolic syndrome associates with low bacterial gene richness, Akkermansia depletion, and a pro-inflammatory LPS-rich community driving metabolic endotoxemia.",
    },
    "hypertension": {
        "indicators": [
            "SCFA_producers_reduced", "Prevotella_enriched", "Klebsiella_enriched",
            "gut_barrier_permeability_increased",
        ],
        "key_genera": ["Prevotella", "Klebsiella", "Faecalibacterium", "Roseburia"],
        "functional_shift": ["SCFA_profile_shifted", "TMAO_pathway_altered", "LPS_translocation_increased"],
        "description": "Hypertension cohorts show reduced SCFA-producing taxa and enrichment of Prevotella/Klebsiella; acetate and butyrate signalling via GPR41/43/109A modulates blood pressure.",
    },
    "autism_spectrum_disorder": {
        "indicators": [
            "alpha_diversity_decreased", "Prevotella_depleted", "Clostridium_enriched",
            "Desulfovibrio_enriched",
        ],
        "key_genera": ["Prevotella", "Clostridium", "Desulfovibrio", "Bifidobacterium", "Bacteroides"],
        "functional_shift": ["SCFA_profile_shifted", "tryptophan_metabolism_altered", "p_cresol_increased"],
        "description": "ASD gut profiles commonly show Prevotella depletion and Clostridium/Desulfovibrio enrichment; associations are confounded by diet selectivity and remain an active research area.",
    },
    "multiple_sclerosis": {
        "indicators": [
            "Prevotella_depleted", "Akkermansia_muciniphila_mixed", "Methanobrevibacter_mixed",
            "SCFA_producers_reduced",
        ],
        "key_genera": ["Prevotella", "Akkermansia", "Faecalibacterium", "Methanobrevibacter"],
        "functional_shift": ["SCFA_profile_shifted", "Th17_Treg_balance_altered"],
        "description": "Multiple sclerosis is linked to reduced SCFA producers and altered Prevotella/Akkermansia balance, with proposed effects on Th17/Treg immune homeostasis.",
    },
    "celiac_disease": {
        "indicators": [
            "Bifidobacterium_depleted", "Bacteroides_fragilis_altered", "Escherichia_enriched",
            "alpha_diversity_mildly_decreased",
        ],
        "key_genera": ["Bifidobacterium", "Bacteroides", "Escherichia", "Lactobacillus"],
        "functional_shift": ["gut_barrier_permeability_increased", "gluten_peptide_metabolism_altered"],
        "description": "Celiac disease shows Bifidobacterium depletion and shifts in gluten-metabolising taxa; a gluten-free diet itself reshapes the community and confounds untreated-disease signatures.",
    },
    "asthma": {
        "indicators": [
            "Lachnospira_depleted", "Faecalibacterium_depleted", "early_life_diversity_decreased",
            "Candida_enriched",
        ],
        "key_genera": ["Lachnospira", "Faecalibacterium", "Veillonella", "Roseburia"],
        "functional_shift": ["SCFA_production_reduced", "Th2_skewing"],
        "description": "Early-life depletion of Lachnospira/Faecalibacterium/Roseburia/Veillonella (the 'LRVF' signature) predicts asthma risk; SCFA-mediated immune regulation is the leading mechanistic hypothesis.",
    },
    "bacterial_vaginosis": {
        "indicators": [
            "Lactobacillus_crispatus_depleted", "Gardnerella_enriched", "Prevotella_enriched",
            "community_diversity_increased",
        ],
        "key_genera": ["Lactobacillus", "Gardnerella", "Prevotella", "Sneathia"],
        "functional_shift": ["lactate_production_reduced", "sialidase_activity_increased", "mucin_degradation_increased"],
        "description": "BV is a shift from Lactobacillus crispatus dominance (CST I) to a diverse anaerobic community with Gardnerella biofilms; vaginal pH rises as lactate falls.",
    },
    "periodontal_disease": {
        "indicators": [
            "Porphyromonas_gingivalis_enriched", "Fusobacterium_nucleatum_enriched",
            "community_diversity_increased",
        ],
        "key_genera": ["Porphyromonas", "Fusobacterium", "Treponema", "Tannerella"],
        "functional_shift": ["proteolysis_increased", "gingival_inflammation", "biofilm_dysbiosis"],
        "description": "Periodontitis features a keystone-pathogen-driven dysbiotic biofilm (red complex: P. gingivalis, T. forsythia, T. denticola) sustained by inflammation-derived nutrients.",
    },
    "dental_caries": {
        "indicators": [
            "Streptococcus_mutans_enriched", "acid_producers_enriched", "community_diversity_decreased",
        ],
        "key_genera": ["Streptococcus", "Lactobacillus", "Scardovia", "Prevotella"],
        "functional_shift": ["acid_production_increased", "enamel_deminineralisation"],
        "description": "Carious lesions are dominated by acidogenic/aciduric taxa (S. mutans, Lactobacillus, Scardovia) whose fermentation acids demineralise enamel.",
    },
}


def merge(db_name: str, new_entries: dict) -> None:
    path = KB / db_name
    db = json.loads(path.read_text())
    added, skipped = [], []
    for key, entry in new_entries.items():
        if key in db:
            skipped.append(key)
        else:
            db[key] = entry
            added.append(key)
    path.write_text(json.dumps(db, ensure_ascii=False, indent=1) + "\n")
    print(f"{db_name}: +{len(added)} (total {len(db)}), skipped existing: {skipped}")


if __name__ == "__main__":
    merge("taxon_db.json", NEW_TAXA)
    merge("disease_db.json", NEW_DISEASES)
