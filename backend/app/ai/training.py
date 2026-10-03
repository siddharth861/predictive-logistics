from __future__ import annotations

import pandas as pd


FEATURE_COLUMNS = [
    "day_of_week",
    "lag_1",
    "lag_7",
    "rolling_mean_7",
    "rolling_std_7",
    "rolling_mean_14",
    "rolling_mean_30",
]


def prepare_training_data(
    features: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Convert engineered consumption features into ML training data.

    The target is the observed consumption quantity for each date.
    Rows that cannot provide lag features are removed.
    """

    if features.empty:
        raise ValueError("No feature data available for training.")

    missing_columns = [
        column
        for column in FEATURE_COLUMNS + ["quantity"]
        if column not in features.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {', '.join(missing_columns)}"
        )

    training = features.dropna(
        subset=[
            "lag_1",
            "lag_7",
        ]
    ).copy()

    if training.empty:
        raise ValueError(
            "Not enough historical data to create training samples."
        )

    X = training[FEATURE_COLUMNS].copy()
    y = training["quantity"].copy()

    return X, y