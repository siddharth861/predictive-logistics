from __future__ import annotations

from typing import Any


def explain_supply_risk(
    risk_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert supply-risk components into human-readable,
    structured explanations.

    This does not change the underlying risk score.
    It explains the existing calculation.
    """

    components = risk_result.get(
        "components",
        {},
    )

    metrics = risk_result.get(
        "supporting_metrics",
        {},
    )

    reasons: list[dict[str, Any]] = []

    inventory_risk = float(
        components.get(
            "inventory_risk",
            0,
        )
    )

    demand_pressure = float(
        components.get(
            "demand_pressure",
            0,
        )
    )

    variability_risk = float(
        components.get(
            "variability_risk",
            0,
        )
    )

    uncertainty_risk = float(
        components.get(
            "uncertainty_risk",
            0,
        )
    )

    days_of_cover = metrics.get(
        "days_of_cover"
    )

    current_stock = metrics.get(
        "current_stock"
    )

    minimum_stock = metrics.get(
        "minimum_stock"
    )

    forecast_confidence = metrics.get(
        "forecast_confidence"
    )

    stockout_risk_level = metrics.get(
        "stockout_risk_level"
    )

    # ---------------------------------------------------------
    # Inventory explanation
    # ---------------------------------------------------------

    if inventory_risk > 0:
        reasons.append(
            {
                "factor": "Inventory coverage",
                "impact": "INCREASES_RISK",
                "severity": (
                    "HIGH"
                    if inventory_risk >= 30
                    else "MEDIUM"
                ),
                "message": (
                    f"Current inventory provides approximately "
                    f"{days_of_cover:.1f} days of forecasted "
                    f"consumption."
                    if days_of_cover is not None
                    else (
                        "Inventory coverage could not be "
                        "calculated."
                    )
                ),
                "score_contribution": round(
                    inventory_risk,
                    2,
                ),
            }
        )
    else:
        reasons.append(
            {
                "factor": "Inventory coverage",
                "impact": "STABLE",
                "severity": "LOW",
                "message": (
                    "Current inventory provides sufficient "
                    "forecasted coverage."
                ),
                "score_contribution": 0.0,
            }
        )

    # ---------------------------------------------------------
    # Demand pressure explanation
    # ---------------------------------------------------------

    if demand_pressure > 0:
        reasons.append(
            {
                "factor": "Demand pressure",
                "impact": "INCREASES_RISK",
                "severity": (
                    "HIGH"
                    if demand_pressure >= 20
                    else "MEDIUM"
                ),
                "message": (
                    "Current stock is relatively close to "
                    "the configured minimum-stock threshold."
                ),
                "score_contribution": round(
                    demand_pressure,
                    2,
                ),
            }
        )
    else:
        reasons.append(
            {
                "factor": "Demand pressure",
                "impact": "STABLE",
                "severity": "LOW",
                "message": (
                    "Current stock is comfortably above "
                    "the minimum-stock threshold."
                ),
                "score_contribution": 0.0,
            }
        )

    # ---------------------------------------------------------
    # Consumption variability explanation
    # ---------------------------------------------------------

    if variability_risk > 0:
        reasons.append(
            {
                "factor": "Consumption variability",
                "impact": "INCREASES_RISK",
                "severity": (
                    "HIGH"
                    if variability_risk >= 15
                    else "MEDIUM"
                ),
                "message": (
                    "Recent consumption has shown elevated "
                    "variation, increasing forecast uncertainty."
                ),
                "score_contribution": round(
                    variability_risk,
                    2,
                ),
            }
        )
    else:
        reasons.append(
            {
                "factor": "Consumption variability",
                "impact": "STABLE",
                "severity": "LOW",
                "message": (
                    "Recent consumption variability is "
                    "relatively low."
                ),
                "score_contribution": 0.0,
            }
        )

    # ---------------------------------------------------------
    # Forecast uncertainty explanation
    # ---------------------------------------------------------

    if uncertainty_risk > 0:
        reasons.append(
            {
                "factor": "Forecast uncertainty",
                "impact": "INCREASES_RISK",
                "severity": (
                    "MEDIUM"
                    if uncertainty_risk >= 7.5
                    else "LOW"
                ),
                "message": (
                    f"Forecast confidence is "
                    f"{forecast_confidence:.1f}%."
                    if forecast_confidence is not None
                    else (
                        "Forecast confidence is "
                        "not available."
                    )
                ),
                "score_contribution": round(
                    uncertainty_risk,
                    2,
                ),
            }
        )
    else:
        reasons.append(
            {
                "factor": "Forecast uncertainty",
                "impact": "STABLE",
                "severity": "LOW",
                "message": (
                    "Forecast uncertainty is currently low."
                ),
                "score_contribution": 0.0,
            }
        )

    # ---------------------------------------------------------
    # Overall explanation
    # ---------------------------------------------------------

    risk_level = risk_result.get(
        "risk_level",
        "UNKNOWN",
    )

    risk_score = float(
        risk_result.get(
            "risk_score",
            0,
        )
    )

    contributing_factors = [
        reason
        for reason in reasons
        if reason["impact"] == "INCREASES_RISK"
    ]

    if contributing_factors:
        primary_factor = max(
            contributing_factors,
            key=lambda reason: reason[
                "score_contribution"
            ],
        )

        summary = (
            f"Supply risk is {risk_level} "
            f"with a score of {risk_score:.1f}/100. "
            f"The largest contributing factor is "
            f"{primary_factor['factor'].lower()}."
        )
    else:
        summary = (
            f"Supply risk is {risk_level} "
            f"with a score of {risk_score:.1f}/100. "
            f"No major risk drivers are currently detected."
        )

    recommendations: list[str] = []

    if days_of_cover is not None and days_of_cover <= 7:
        recommendations.append(
            "Review replenishment requirements because "
            "forecasted stock coverage is below 7 days."
        )

    if (
        current_stock is not None
        and minimum_stock is not None
        and current_stock <= minimum_stock
    ):
        recommendations.append(
            "Review immediate replenishment because "
            "current stock is at or below the minimum threshold."
        )

    if stockout_risk_level in {
        "HIGH",
        "CRITICAL",
    }:
        recommendations.append(
            "Prioritize the item for supply planning "
            "because stockout risk is elevated."
        )

    if variability_risk > 0:
        recommendations.append(
            "Review recent consumption changes before "
            "finalizing replenishment quantities."
        )

    if not recommendations:
        recommendations.append(
            "Continue monitoring inventory and consumption "
            "through the normal planning cycle."
        )

    return {
        "risk_score": round(
            risk_score,
            2,
        ),
        "risk_level": risk_level,
        "summary": summary,
        "reasons": reasons,
        "recommendations": recommendations,
    }