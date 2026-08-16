"""Interpretation engine narrative correctness (module counting, key aliases)."""
from app.services.interpretation_engine import EnhancedInterpreter


class TestIntegratedNarrative:
    def test_counts_frontend_style_results_without_status(self):
        """Frontend sends bare {"result_data": ...} entries; the narrative must
        not report '0 analytical modules'."""
        interp = EnhancedInterpreter().interpret_full(
            all_results={
                "alpha": {"result_data": {"significant": False}},
                "permanova": {"result_data": {"pvalue": 0.02, "significant": True}},
                "lefse": {"result_data": {"n_significant": 2}},
            },
            use_llm=False,
        )
        assert "3 analytical modules" in interp.integrated_narrative

    def test_alpha_key_alias(self):
        """The 'alpha' analysis-type key must feed the alpha-diversity story."""
        interp = EnhancedInterpreter().interpret_full(
            all_results={
                "alpha": {"result_data": {
                    "group_statistics": {"shannon": {"statistical_test": {
                        "pvalue": 0.31, "significant": False}}},
                }},
            },
            use_llm=False,
        )
        assert "Shannon" in interp.integrated_narrative

    def test_llm_off_is_never_enhanced(self):
        interp = EnhancedInterpreter().interpret_full(
            all_results={"permanova": {"result_data": {"pvalue": 0.02}}},
            use_llm=False,
        )
        assert interp.llm_enhanced is False
        assert interp.llm_model is None
