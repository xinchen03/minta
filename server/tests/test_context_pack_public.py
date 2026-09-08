"""Regression coverage for the Community context-pack path."""


def test_basic_context_pack_does_not_require_optional_v2_synthesis_module():
    from services.brief_builder import build_context_pack

    class Slot:
        label = "preferences"
        content = "先给结论"

    assert "先给结论" in build_context_pack([Slot()], scene="research")
