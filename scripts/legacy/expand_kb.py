#!/usr/bin/env python3
"""Expand knowledge base with additional species and diseases."""
import json, os

KB_DIR = "/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend/app/knowledge"

def load_json(fname):
    with open(os.path.join(KB_DIR, fname), "r") as f:
        return json.load(f)

def save_json(fname, data):
    with open(os.path.join(KB_DIR, fname), "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def expand_taxon_db():
    db = load_json("taxon_db.json")
    new_entries = {
        "Alistipes_putredinis": {
            "gram_stain": "Gram-negative",
            "oxygen": "strictly_anaerobic",
            "main_products": ["acetate", "succinate"],
            "known_functions": ["amino_acid_fermentation", "bile_acid_transformation", "anti_inflammatory"],
            "disease_associations": {
                "colorectal_cancer": "depleted",
                "appendicitis": "depleted"
            },
            "health_markers": ["colon_health", "protein_metabolism"],
            "notes": "Bile acid 7alpha-dehydroxylating bacterium. Converts primary to secondary bile acids."
        },
        "Bacteroides_caccae": {
            "gram_stain": "Gram-negative",
            "oxygen": "anaerobic",
            "main_products": ["acetate", "succinate"],
            "known_functions": ["polysaccharide_degradation", "mucin_utilization", "cross_feeding"],
            "disease_associations": {
                "Crohn_disease": "depleted",
                "obesity": "mixed"
            },
            "health_markers": ["carbohydrate_metabolism", "community_stability"],
            "notes": "Abundant gut commensal. Degrades complex carbohydrates and mucin oligosaccharides."
        },
        "Eggerthella_lenta": {
            "gram_stain": "Gram-positive",
            "oxygen": "strictly_anaerobic",
            "main_products": ["acetate", "formate"],
            "known_functions": ["cardiac_glycoside_metabolism", "bile_acid_modification", "drug_metabolism"],
            "disease_associations": {
                "inflammatory_bowel_disease": "associated",
                "bacteremia": "associated"
            },
            "health_markers": ["drug_metabolism", "bile_acid_profile"],
            "notes": "Metabolizes cardiac glycosides (digoxin). Bile acid 7alpha-dehydroxylator. Opportunistic pathogen in immunocompromised."
        },
        "Flavonifractor_plautii": {
            "gram_stain": "Gram-positive",
            "oxygen": "strictly_anaerobic",
            "main_products": ["butyrate"],
            "known_functions": ["SCFA_production", "flavonoid_metabolism", "anti_inflammatory"],
            "disease_associations": {
                "Crohn_disease": "depleted",
                "ulcerative_colitis": "depleted"
            },
            "health_markers": ["colon_health", "polyphenol_metabolism"],
            "notes": "Butyrate producer that metabolizes dietary flavonoids. Anti-inflammatory effects via SCFA signaling."
        },
        "Gordonibacter_pamelaeae": {
            "gram_stain": "Gram-positive",
            "oxygen": "strictly_anaerobic",
            "main_products": ["acetate", "formate"],
            "known_functions": ["polyphenol_metabolism", "flavonoid_conversion", "anti_oxidant"],
            "disease_associations": {
                "colorectal_cancer": "depleted"
            },
            "health_markers": ["polyphenol_bioavailability", "antioxidant_capacity"],
            "notes": "Converts dietary ellagitannins to urolithins. Linked to colon cancer protection."
        },
        "Intestinibacter_bartlettii": {
            "gram_stain": "Gram-positive",
            "oxygen": "strictly_anaerobic",
            "main_products": ["butyrate", "formate"],
            "known_functions": ["SCFA_production", "spore_formation", "bile_acid_resistance"],
            "disease_associations": {
                "Crohn_disease": "mixed",
                "antibiotic_associated_diarrhea": "associated"
            },
            "health_markers": ["colon_health", "spore_former"],
            "notes": "Spore-forming butyrate producer. Resistant to bile acids. Common after antibiotic treatment."
        },
        "Odoribacter_splanchnicus": {
            "gram_stain": "Gram-negative",
            "oxygen": "strictly_anaerobic",
            "main_products": ["acetate", "succinate"],
            "known_functions": ["polysaccharide_degradation", "bile_acid_transformation", "anti_inflammatory"],
            "disease_associations": {
                "colorectal_cancer": "depleted",
                "ulcerative_colitis": "depleted"
            },
            "health_markers": ["colon_health", "bile_acid_metabolism"],
            "notes": "Bile acid-transforming bacterium. Depleted in CRC and IBD. Anti-inflammatory via secondary bile acids."
        },
        "Paraprevotella_clara": {
            "gram_stain": "Gram-negative",
            "oxygen": "anaerobic",
            "main_products": ["succinate", "acetate"],
            "known_functions": ["xylan_degradation", "complex_carbohydrate_utilization"],
            "disease_associations": {
                "obesity": "mixed"
            },
            "health_markers": ["fiber_response", "carbohydrate_metabolism"],
            "notes": "Xylan-degrading specialist. Responds to high-fiber diets. Prevotella-related genus."
        },
        "Pseudobutyrivibrio_ruminis": {
            "gram_stain": "Gram-negative",
            "oxygen": "strictly_anaerobic",
            "main_products": ["butyrate", "formate"],
            "known_functions": ["SCFA_production", "hemicellulose_degradation", "cross_feeding"],
            "disease_associations": {
                "obesity": "depleted"
            },
            "health_markers": ["fiber_fermentation", "SCFA_status"],
            "notes": "Butyrate producer from hemicellulose. Important for fiber fermentation in the colon."
        },
        "Sutterella_wadsworthensis": {
            "gram_stain": "Gram-negative",
            "oxygen": "strictly_anaerobic",
            "main_products": ["acetate", "succinate"],
            "known_functions": ["mucin_degradation", "immune_modulation", "autism_associated"],
            "disease_associations": {
                "autism_spectrum_disorder": "enriched",
                "Crohn_disease": "associated"
            },
            "health_markers": ["gut_brain_axis", "mucin_degrader"],
            "notes": "Proteobacteria family. Enriched in autism and some IBD cohorts. Mucin degrader."
        },
    }
    db.update(new_entries)
    save_json("taxon_db.json", db)
    print(f"Taxon DB expanded: {len(db)} total entries (+{len(new_entries)} new)")
    return len(new_entries)

def expand_disease_db():
    db = load_json("disease_db.json")
    new_entries = {
        "non_alcoholic_fatty_liver_disease": {
            "indicators": [
                "Enterobacteriaceae_expansion",
                "Streptococcus_spp_increased",
                "Eubacterium_rectale_depleted",
                "ethanol_producers_enriched",
                "endotoxemia_markers"
            ],
            "key_genera": [
                "Escherichia",
                "Klebsiella",
                "Streptococcus",
                "Eubacterium",
                "Faecalibacterium",
                "Akkermansia"
            ],
            "functional_shift": [
                "endotoxin_translocation_increased",
                "ethanol_production_increased",
                "bile_acid_metabolism_disrupted",
                "SCFA_cardioprotection_reduced",
                "lipopolysaccharide_signaling_chronic"
            ],
            "description": "NAFLD/NASH microbiome shows increased ethanol-producing bacteria, Enterobacteriaceae expansion, and decreased butyrate producers. Endotoxemia drives hepatic inflammation and steatosis progression."
        },
        "alzheimers_disease": {
            "indicators": [
                "Bacteroides_depleted",
                "Firmicutes_Bacteroidetes_ratio_increased",
                "anti_inflammatory_species_reduced",
                "pro_inflammatory_taxa_enriched",
                "gut_barrier_dysfunction"
            ],
            "key_genera": [
                "Bacteroides",
                "Faecalibacterium",
                "Prevotella",
                "Escherichia",
                "Klebsiella",
                "Desulfovibrio"
            ],
            "functional_shift": [
                "amyloid_secretion_by_bacteria",
                "LPS_inflammation_chronic",
                "butyrate_neuroprotection_decreased",
                "gut_brain_axis_dysregulated",
                "short_chain_fatty_acids_reduced"
            ],
            "description": "AD microbiome shows reduced Bacteroides and butyrate producers, increased pro-inflammatory taxa. Bacterial amyloid and LPS may contribute to neuroinflammation via gut-brain axis."
        },
        "parkinsons_disease": {
            "indicators": [
                "Prevotella_depleted",
                "Enterobacteriaceae_expansion",
                "anti_inflammatory_species_reduced",
                "alpha_synuclein_fibril_formation",
                "constipation_associated_changes"
            ],
            "key_genera": [
                "Prevotella",
                "Faecalibacterium",
                "Roseburia",
                "Escherichia",
                "Klebsiella",
                "Akkermansia"
            ],
            "functional_shift": [
                "gut_motility_slowed",
                "LPS_inflammation_chronic",
                "SCFA_production_decreased",
                "alpha_synuclein_aggregation",
                "dopamine_metabolism_altered"
            ],
            "description": "PD is associated with reduced Prevotella and butyrate producers, Enterobacteriaceae expansion. Gut dysfunction precedes motor symptoms. Alpha-synuclein pathology may originate in the gut."
        },
        "rheumatoid_arthritis": {
            "indicators": [
                "Prevotella_copri_enriched",
                "Collinsella_aerofaciens_enriched",
                "Faecalibacterium_depleted",
                "oral_bacteria_translocated",
                "citullinating_bacteria_present"
            ],
            "key_genera": [
                "Prevotella",
                "Collinsella",
                "Faecalibacterium",
                "Lactobacillus",
                "Porphyromonas",
                "Streptococcus"
            ],
            "functional_shift": [
                "citullination_by_bacteria",
                "T_cell_activation_increased",
                "anti_inflammatory_SCFA_reduced",
                "oral_gut_axis_dysregulated",
                "autoantibody_production_triggered"
            ],
            "description": "RA shows enrichment of Prevotella copri and Collinsella aerofaciens. Bacterial citrullination may trigger anti-CCP autoantibodies. Oral-gut axis involvement is increasingly recognized."
        },
        "chronic_kidney_disease": {
            "indicators": [
                "uremic_toxin_producers_enriched",
                "p_cresol_producers_increased",
                "indoxyl_sulfate_producers_increased",
                "beneficial_species_depleted",
                "gut_barrier_dysfunction"
            ],
            "key_genera": [
                "Escherichia",
                "Klebsiella",
                "Enterococcus",
                "Faecalibacterium",
                "Roseburia",
                "Akkermansia"
            ],
            "functional_shift": [
                "uremic_toxin_production_increased",
                "p_cresol_sulfate_increased",
                "indoxyl_sulfate_increased",
                "trimethylamine_oxide_increased",
                "gut_barrier_disrupted"
            ],
            "description": "CKD microbiome produces uremic toxins (p-cresol sulfate, indoxyl sulfate, TMAO) that the failing kidneys cannot clear. Beneficial SCFA producers are depleted."
        },
    }
    db.update(new_entries)
    save_json("disease_db.json", db)
    print(f"Disease DB expanded: {len(db)} total entries (+{len(new_entries)} new)")
    return len(new_entries)

def main():
    print("=" * 60)
    print("Expanding Meta2bAnalyst Knowledge Base")
    print("=" * 60)
    taxon_added = expand_taxon_db()
    disease_added = expand_disease_db()
    print(f"\nDone! Added {taxon_added} species + {disease_added} diseases.")

if __name__ == "__main__":
    main()
