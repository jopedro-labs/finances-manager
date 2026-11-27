from __future__ import annotations

from core.models import GrowthProjectionScenario
from core.projections import ProjectionEngine


def test_calculate_future_value_zero_years() -> None:
    """Verify 0 years horizon returns initial value."""
    engine: ProjectionEngine = ProjectionEngine()
    fv: float = engine.calculate_future_value(
        initial_value=1000.0, monthly_contribution=300.0, annual_rate=0.08, years=0
    )
    assert fv == 1000.0


def test_calculate_future_value_growth() -> None:
    """Verify compound interest calculation over 10 years."""
    engine: ProjectionEngine = ProjectionEngine()
    fv: float = engine.calculate_future_value(
        initial_value=1000.0, monthly_contribution=300.0, annual_rate=0.08, years=10
    )
    assert fv > 50000.0


def test_calculate_future_value_zero_rate() -> None:
    """Verify zero growth rate behaves as linear sum of contributions."""
    engine: ProjectionEngine = ProjectionEngine()
    fv: float = engine.calculate_future_value(
        initial_value=1000.0, monthly_contribution=100.0, annual_rate=0.0, years=1
    )
    assert fv == 2200.0


def test_generate_scenario_milestones() -> None:
    """Verify scenario generation structures milestones for 10, 20, 30 years."""
    engine: ProjectionEngine = ProjectionEngine()
    scenario: GrowthProjectionScenario = engine.generate_scenario(
        name="Realistic",
        initial_value=3000.0,
        monthly_contribution=300.0,
        annual_rate=0.08,
        horizons=[10, 20, 30],
        inflation_rate=0.02,
    )
    assert scenario.name == "Realistic"
    assert set(scenario.milestones.keys()) == {10, 20, 30}
    assert (
        scenario.milestones[10].projected_value > scenario.milestones[10].inflation_adjusted_value
    )
