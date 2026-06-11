"""Tests for the constraint-priority engine (Phase 5 — pure logic)."""

from app.core.constraint_priority import build_constraint_priority_block


def test_full_ladder_is_ordered_mandatory_first():
    block = build_constraint_priority_block(
        mandatory=True, weather=True, occasion=True, style=True
    )
    assert block.startswith("[CONSTRAINT PRIORITY]")
    assert block.endswith("[END CONSTRAINT PRIORITY]")
    assert "1. MANDATORY rules" in block
    assert "2. Weather safety" in block
    assert "3. Festival / occasion styling" in block
    assert "4. Personal style" in block


def test_inactive_tiers_are_omitted_and_renumbered():
    block = build_constraint_priority_block(weather=True, occasion=True, style=True)
    assert "MANDATORY" not in block
    assert "1. Weather safety" in block
    assert "2. Festival / occasion styling" in block
    assert "3. Personal style" in block


def test_single_layer_needs_no_arbitration():
    assert build_constraint_priority_block(weather=True) == ""
    assert build_constraint_priority_block(mandatory=True) == ""
    assert build_constraint_priority_block() == ""


def test_two_layers_produce_a_block():
    block = build_constraint_priority_block(mandatory=True, style=True)
    assert "1. MANDATORY rules" in block
    assert "2. Personal style" in block


def test_trousers_example_only_when_mandatory_and_weather():
    with_both = build_constraint_priority_block(mandatory=True, weather=True)
    assert "lightweight breathable trousers" in with_both
    without_weather = build_constraint_priority_block(mandatory=True, style=True)
    assert "trousers" not in without_weather


def test_cross_tier_satisfaction_instruction_present():
    block = build_constraint_priority_block(weather=True, style=True)
    assert "satisfy a higher tier while still honouring the lower" in block
