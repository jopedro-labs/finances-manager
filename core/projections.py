"""
Projection calculation engine for long-term portfolio growth.
"""

from __future__ import annotations

from datetime import datetime

from core.models import GrowthMilestone, GrowthProjectionScenario
from infra.database.finance_sql_extraction import FinanceSQLExtractor


class ProjectionEngine:
    """Calculates compound interest projections with periodic contributions."""

    @staticmethod
    def calculate_future_value(
        initial_value: float,
        monthly_contribution: float,
        annual_rate: float,
        years: int,
    ) -> float:
        """Calculates the future portfolio value using compound interest with periodic contributions.

        Uses the standard future value formula:
        ``FV = PV × (1 + r)^t + PMT × [((1 + r)^t - 1) / r]``
        where ``r`` is the monthly rate (derived from annual_rate) and ``t`` is
        total months. Contributions are assumed to be made at the end of each month.

        Args:
            initial_value: Current portfolio value in EUR (present value, PV).
            monthly_contribution: Fixed monthly investment in EUR (PMT).
            annual_rate: Expected annual return as a decimal fraction (e.g. 0.07 for 7%).
            years: Investment horizon in whole years. Returns initial_value if ≤ 0.

        Returns:
            Projected nominal portfolio value in EUR at the end of the horizon.
        """
        if years <= 0:
            return initial_value

        months = years * 12
        monthly_rate = (1 + annual_rate) ** (1 / 12) - 1

        if monthly_rate == 0:
            return float(initial_value + (monthly_contribution * months))

        fv_principal = initial_value * ((1 + monthly_rate) ** months)
        fv_contributions = monthly_contribution * (
            ((1 + monthly_rate) ** months - 1) / monthly_rate
        )

        return float(fv_principal + fv_contributions)

    def generate_scenario(
        self,
        name: str,
        initial_value: float,
        monthly_contribution: float,
        annual_rate: float,
        horizons: list[int] | None = None,
        inflation_rate: float = 0.02,
    ) -> GrowthProjectionScenario:
        """Generates a complete growth projection scenario across yearly progression.

        Computes year-by-year milestones up to the longest requested horizon,
        deriving nominal projected value, total invested capital, compound
        interest earned, and inflation-adjusted real value for every year.
        Subset milestones are also indexed by exact horizon year for quick lookup.

        Args:
            name: Human-readable scenario label (e.g. 'Conservative', 'Optimistic').
            initial_value: Starting portfolio value in EUR.
            monthly_contribution: Fixed monthly investment in EUR.
            annual_rate: Expected annual return as a decimal fraction (e.g. 0.07 for 7%).
            horizons: List of horizon years to mark as named milestones. Defaults to
                [10, 20, 30] if not provided.
            inflation_rate: Annual inflation rate as a decimal fraction. Defaults to 0.02.
                Used to compute inflation-adjusted values: nominal / (1 + i)^t.

        Returns:
            A GrowthProjectionScenario containing yearly progression and a
            milestones dict keyed by each value in horizons.
        """
        if horizons is None:
            horizons = [10, 20, 30]

        progression: list[GrowthMilestone] = []
        milestones: dict[int, GrowthMilestone] = {}

        # Generate yearly progression
        max_horizon = max(horizons)
        for year in range(max_horizon + 1):
            projected_val = self.calculate_future_value(
                initial_value, monthly_contribution, annual_rate, year
            )
            total_invested = initial_value + (monthly_contribution * 12 * year)
            compound_interest = projected_val - total_invested

            # Discount for inflation: Real Value = Nominal / (1 + i)^t
            inflation_adjusted = projected_val / ((1 + inflation_rate) ** year)

            milestone = GrowthMilestone(
                year=year,
                total_invested=total_invested,
                compound_interest=compound_interest,
                projected_value=projected_val,
                inflation_adjusted_value=inflation_adjusted,
            )
            progression.append(milestone)

            if year in horizons:
                milestones[year] = milestone

        return GrowthProjectionScenario(
            name=name,
            annual_return_pct=annual_rate * 100,
            monthly_contribution=monthly_contribution,
            progression=progression,
            milestones=milestones,
        )

    def calculate_historical_cagr(self, extractor: FinanceSQLExtractor) -> float:
        """Estimates the historical Compound Annual Growth Rate (CAGR) from database snapshots.

        Fetches the full portfolio history and derives CAGR from the earliest and
        latest valid (non-zero) snapshots. For periods under 1 year, returns the
        absolute (non-annualised) return instead.

        Args:
            extractor: FinanceSQLExtractor instance used to fetch portfolio history
                from the SQLite database.

        Returns:
            CAGR as a decimal fraction (e.g. 0.12 for 12%) for periods ≥ 1 year,
            or absolute return for periods < 1 year. Returns 0.0 if fewer than two
            valid snapshots are available or if dates cannot be parsed.
        """
        history = extractor.fetch_portfolio_history()

        # Filter out snapshots with zero value to avoid division by zero
        valid_history = [h for h in history if h.total_value_eur > 0]

        if len(valid_history) < 2:
            return 0.0

        start_val = valid_history[0].total_value_eur
        end_val = valid_history[-1].total_value_eur

        try:
            # Parse dates to calculate real duration in years (as a fraction)
            start_date = datetime.fromisoformat(valid_history[0].snapshot_date.replace(" ", "T"))
            end_date = datetime.fromisoformat(valid_history[-1].snapshot_date.replace(" ", "T"))

            duration_seconds = (end_date - start_date).total_seconds()
            # If duration is less than 1 hour, return 0
            if duration_seconds < 3600:
                return 0.0

            years = duration_seconds / (365.25 * 24 * 3600)

            if years < 1.0:
                # Periods < 1 year: absolute return (not annualised)
                return float((end_val / start_val) - 1)

            # Periods >= 1 year: CAGR (geometric mean)
            return float(pow(end_val / start_val, 1 / years) - 1)
        except (ValueError, ZeroDivisionError, OverflowError):
            return 0.0
