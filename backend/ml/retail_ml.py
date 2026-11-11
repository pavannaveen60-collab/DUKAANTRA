import json
import math
import pickle
import zlib
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Mapping

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
)

BASE_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = BASE_DIR / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "dukaantra_retail_models.joblib"
METRICS_PATH = ARTIFACT_DIR / "training_metrics.json"
MODEL_SCHEMA_VERSION = 2
MODEL_VERSION = "2.0.0"
FORECAST_HORIZON_DAYS = 7
MIN_TRAINING_DATES = 30

DEMAND_FEATURES = [
    "lag_1",
    "lag_7",
    "rolling_7",
    "price",
    "day_of_week",
    "month",
    "is_weekend",
]
STOCKOUT_FEATURES = [*DEMAND_FEATURES, "stock_on_hand"]
SALES_FEATURES = [
    "lag_1_units",
    "rolling_7_units",
    "lag_1_revenue",
    "rolling_7_revenue",
    "rolling_7_orders",
    "day_of_week",
    "month",
    "is_weekend",
]
ANOMALY_FEATURES = [
    "units_sold",
    "revenue",
    "order_count",
    "average_price",
]

FEATURE_METADATA = {
    "demand": {
        "features": DEMAND_FEATURES,
        "target": "synthetic units demanded during the next 7 days",
        "timestamp": "forecast date; only prior-day demand history is used",
        "horizon_days": FORECAST_HORIZON_DAYS,
    },
    "stockout": {
        "features": STOCKOUT_FEATURES,
        "target": "1 when next-7-day demand exceeds stock on hand at forecast time",
        "timestamp": "forecast date; stock is sampled before the forecast horizon",
        "horizon_days": FORECAST_HORIZON_DAYS,
    },
    "sales": {
        "features": SALES_FEATURES,
        "target": "synthetic revenue on the forecast date (one-day horizon)",
        "timestamp": "forecast date; all sales features end on the prior day",
        "horizon_days": 1,
    },
    "anomaly": {
        "features": ANOMALY_FEATURES,
        "target": "unsupervised outlier score for an already completed sales day",
        "timestamp": "completed sales date; not a forecast",
        "horizon_days": 0,
    },
}


def _calendar_features(forecast_date):
    weekday = forecast_date.day_of_week
    return {
        "day_of_week": weekday,
        "month": forecast_date.month,
        "is_weekend": int(weekday >= 5),
    }


def _demand_target(demand, forecast_day, stock_on_hand):
    horizon_demand = sum(
        demand[forecast_day:forecast_day + FORECAST_HORIZON_DAYS]
    )
    return horizon_demand, int(horizon_demand > stock_on_hand)


def _sales_features(
    daily_units,
    daily_revenue,
    daily_orders,
    forecast_day,
    forecast_date,
):
    return {
        "lag_1_units": daily_units[forecast_day - 1],
        "rolling_7_units": float(
            np.mean(daily_units[forecast_day - 7:forecast_day])
        ),
        "lag_1_revenue": daily_revenue[forecast_day - 1],
        "rolling_7_revenue": float(
            np.mean(daily_revenue[forecast_day - 7:forecast_day])
        ),
        "rolling_7_orders": float(
            np.mean(daily_orders[forecast_day - 7:forecast_day])
        ),
        **_calendar_features(forecast_date),
    }


def generate_training_data(product_count=120, days=180, random_state=42):
    """Create reproducible synthetic records with features available at forecast time."""
    if product_count < 1 or days < MIN_TRAINING_DATES + 14:
        raise ValueError(
            f"Training data requires at least one product and "
            f"{MIN_TRAINING_DATES + 14} days."
        )

    rng = np.random.default_rng(random_state)
    start_date = pd.Timestamp("2026-01-01")
    demand_records = []
    sales_records = []

    for product_id in range(product_count):
        base_demand = rng.uniform(2, 30)
        price = rng.uniform(10, 500)
        trend = rng.uniform(-0.015, 0.02)
        demand = []

        for day in range(days + FORECAST_HORIZON_DAYS):
            forecast_date = start_date + pd.Timedelta(days=day)
            weekday = forecast_date.day_of_week
            weekly_factor = 1.25 if weekday >= 5 else 0.90
            trend_factor = max(0.5, 1 + trend * day)
            demand.append(
                int(rng.poisson(max(base_demand * weekly_factor * trend_factor, 0.5)))
            )

        for day in range(7, days):
            forecast_date = start_date + pd.Timedelta(days=day)
            stock_on_hand = int(rng.integers(0, max(2, int(base_demand * 28))))
            next_week_demand, stockout = _demand_target(
                demand, day, stock_on_hand
            )
            demand_records.append({
                "product_id": product_id,
                "date": forecast_date,
                "lag_1": demand[day - 1],
                "lag_7": demand[day - 7],
                "rolling_7": float(np.mean(demand[day - 7:day])),
                "price": price,
                **_calendar_features(forecast_date),
                "stock_on_hand": stock_on_hand,
                "demand_7_day": next_week_demand,
                "stockout_7_day": stockout,
            })

    daily_units = []
    daily_orders = []
    daily_revenue = []
    unit_price = float(rng.uniform(20, 250))
    for day in range(days):
        forecast_date = start_date + pd.Timedelta(days=day)
        weekday = forecast_date.day_of_week
        expected_units = product_count * 5 * (1.2 if weekday >= 5 else 0.9)
        units = int(rng.poisson(expected_units))
        orders = max(1, int(units / rng.uniform(2, 5)))
        revenue = units * unit_price
        daily_units.append(units)
        daily_orders.append(orders)
        daily_revenue.append(revenue)
        sales_records.append({
            "date": forecast_date,
            "units_sold": units,
            "revenue": revenue,
            "order_count": orders,
            "average_price": unit_price if units else 0.0,
        })

    sales_df = pd.DataFrame(sales_records)
    for day in range(7, days):
        forecast_date = start_date + pd.Timedelta(days=day)
        for feature, value in _sales_features(
            daily_units, daily_revenue, daily_orders, day, forecast_date
        ).items():
            sales_df.loc[day, feature] = value
        sales_df.loc[day, "forecast_date"] = forecast_date

    sales_df = sales_df.iloc[7:].copy()
    sales_df["forecast_date"] = pd.to_datetime(sales_df["forecast_date"])
    demand_df = pd.DataFrame(demand_records)
    return demand_df, sales_df


def _chronological_split(frame, timestamp_column):
    dates = np.array(sorted(pd.to_datetime(frame[timestamp_column]).unique()))
    if len(dates) < MIN_TRAINING_DATES:
        raise ValueError(
            f"At least {MIN_TRAINING_DATES} distinct dates are required "
            "for chronological train/validation/test evaluation."
        )

    train_end = max(1, int(len(dates) * 0.6))
    validation_end = max(train_end + 1, int(len(dates) * 0.8))
    validation_end = min(validation_end, len(dates) - 1)
    train_dates = dates[:train_end]
    validation_dates = dates[train_end:validation_end]
    test_dates = dates[validation_end:]
    date_values = pd.to_datetime(frame[timestamp_column])
    return {
        "train": frame.loc[date_values.isin(train_dates)].copy(),
        "validation": frame.loc[date_values.isin(validation_dates)].copy(),
        "test": frame.loc[date_values.isin(test_dates)].copy(),
        "periods": {
            "train": [str(train_dates[0])[:10], str(train_dates[-1])[:10]],
            "validation": [
                str(validation_dates[0])[:10],
                str(validation_dates[-1])[:10],
            ],
            "test": [str(test_dates[0])[:10], str(test_dates[-1])[:10]],
        },
    }


def _regression_metrics(actual, predicted, baseline):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    baseline = np.asarray(baseline, dtype=float)
    denominator = float(np.abs(actual).sum())
    return {
        "model": {
            "mae": round(float(mean_absolute_error(actual, predicted)), 3),
            "rmse": round(float(np.sqrt(mean_squared_error(actual, predicted))), 3),
            "wape": round(float(np.abs(actual - predicted).sum() / denominator), 4)
            if denominator
            else None,
        },
        "baseline": {
            "mae": round(float(mean_absolute_error(actual, baseline)), 3),
            "rmse": round(float(np.sqrt(mean_squared_error(actual, baseline))), 3),
            "wape": round(float(np.abs(actual - baseline).sum() / denominator), 4)
            if denominator
            else None,
        },
    }


def _binary_metrics(actual, predicted, probabilities, baseline_label):
    actual = np.asarray(actual, dtype=int)
    predicted = np.asarray(predicted, dtype=int)
    positive = len(np.unique(actual)) > 1
    baseline_predictions = np.full(len(actual), baseline_label)
    return {
        "model": {
            "precision": round(float(precision_score(actual, predicted, zero_division=0)), 4),
            "recall": round(float(recall_score(actual, predicted, zero_division=0)), 4),
            "f1": round(float(f1_score(actual, predicted, zero_division=0)), 4),
            "accuracy": round(float(accuracy_score(actual, predicted)), 4),
            "confusion_matrix": confusion_matrix(actual, predicted, labels=[0, 1]).tolist(),
            "pr_auc": round(float(average_precision_score(actual, probabilities)), 4)
            if positive
            else None,
            "pr_auc_status": "measured" if positive else "undefined; test partition has one class",
        },
        "baseline": {
            "strategy": "majority class from training partition",
            "label": int(baseline_label),
            "precision": round(float(precision_score(
                actual, baseline_predictions, zero_division=0
            )), 4),
            "recall": round(float(recall_score(
                actual, baseline_predictions, zero_division=0
            )), 4),
            "f1": round(float(f1_score(
                actual, baseline_predictions, zero_division=0
            )), 4),
            "accuracy": round(float(accuracy_score(actual, baseline_predictions)), 4),
            "confusion_matrix": confusion_matrix(
                actual, baseline_predictions, labels=[0, 1]
            ).tolist(),
            "pr_auc": round(float(actual.mean()), 4) if positive else None,
        },
        "test_positive_rate": round(float(actual.mean()), 4),
        "test_has_both_classes": positive,
        "test_probability_samples": len(probabilities),
    }


def _rolling_origin_regression(
    frame,
    timestamp_column,
    feature_columns,
    target_column,
    baseline_column,
    baseline_multiplier=1,
    random_state=42,
):
    dates = np.array(sorted(pd.to_datetime(frame[timestamp_column]).unique()))
    if len(dates) < 60:
        return {
            "status": "not_run",
            "reason": "At least 60 pre-test dates are required.",
            "folds": [],
        }
    date_values = pd.to_datetime(frame[timestamp_column])
    fold_size = max(1, int(len(dates) * 0.1))
    folds = []
    for fold_number, origin in enumerate(
        (int(len(dates) * 0.6), int(len(dates) * 0.75)), start=1
    ):
        origin = min(origin, len(dates) - fold_size)
        train_dates = dates[:origin]
        validation_dates = dates[origin:origin + fold_size]
        train = frame.loc[date_values.isin(train_dates)]
        validation = frame.loc[date_values.isin(validation_dates)]
        if train.empty or validation.empty:
            continue
        model = RandomForestRegressor(
            n_estimators=50,
            max_depth=14,
            min_samples_leaf=2,
            random_state=random_state + fold_number,
            n_jobs=-1,
        )
        model.fit(train[feature_columns], train[target_column])
        predicted = model.predict(validation[feature_columns])
        baseline = validation[baseline_column].to_numpy() * baseline_multiplier
        folds.append({
            "fold": fold_number,
            "train_end": str(train_dates[-1])[:10],
            "validation_period": [
                str(validation_dates[0])[:10],
                str(validation_dates[-1])[:10],
            ],
            "sample_count": len(validation),
            **_regression_metrics(validation[target_column], predicted, baseline),
        })
    return {"status": "completed" if folds else "not_run", "folds": folds}


def _rolling_origin_classifier(
    frame, timestamp_column, feature_columns, target_column, random_state=42
):
    dates = np.array(sorted(pd.to_datetime(frame[timestamp_column]).unique()))
    if len(dates) < 60:
        return {
            "status": "not_run",
            "reason": "At least 60 pre-test dates are required.",
            "folds": [],
        }
    date_values = pd.to_datetime(frame[timestamp_column])
    fold_size = max(1, int(len(dates) * 0.1))
    folds = []
    for fold_number, origin in enumerate(
        (int(len(dates) * 0.6), int(len(dates) * 0.75)), start=1
    ):
        origin = min(origin, len(dates) - fold_size)
        train_dates = dates[:origin]
        validation_dates = dates[origin:origin + fold_size]
        train = frame.loc[date_values.isin(train_dates)]
        validation = frame.loc[date_values.isin(validation_dates)]
        if train.empty or validation.empty:
            continue
        model = RandomForestClassifier(
            n_estimators=50,
            max_depth=14,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=random_state + fold_number,
            n_jobs=-1,
        )
        model.fit(train[feature_columns], train[target_column])
        predicted = model.predict(validation[feature_columns])
        folds.append({
            "fold": fold_number,
            "train_end": str(train_dates[-1])[:10],
            "validation_period": [
                str(validation_dates[0])[:10],
                str(validation_dates[-1])[:10],
            ],
            "sample_count": len(validation),
            "precision": round(float(precision_score(
                validation[target_column], predicted, zero_division=0
            )), 4),
            "recall": round(float(recall_score(
                validation[target_column], predicted, zero_division=0
            )), 4),
            "f1": round(float(f1_score(
                validation[target_column], predicted, zero_division=0
            )), 4),
        })
    return {"status": "completed" if folds else "not_run", "folds": folds}


def train_models(product_count=120, days=180, random_state=42):
    """Train experimental synthetic models; evaluates with a chronological holdout."""
    demand_df, sales_df = generate_training_data(
        product_count=product_count,
        days=days,
        random_state=random_state,
    )
    demand_split = _chronological_split(demand_df, "date")
    sales_split = _chronological_split(sales_df, "forecast_date")
    training_demand = demand_split["train"]
    training_sales = sales_split["train"]

    demand_model = RandomForestRegressor(
        n_estimators=100, min_samples_leaf=2, random_state=random_state, n_jobs=-1
    )
    demand_model.fit(training_demand[DEMAND_FEATURES], training_demand["demand_7_day"])
    demand_validation = demand_split["validation"]
    demand_validation_predictions = demand_model.predict(
        demand_validation[DEMAND_FEATURES]
    )
    demand_validation_baseline = (
        demand_validation["rolling_7"].to_numpy() * FORECAST_HORIZON_DAYS
    )
    demand_test = demand_split["test"]
    demand_predictions = demand_model.predict(demand_test[DEMAND_FEATURES])
    demand_baseline = demand_test["rolling_7"].to_numpy() * FORECAST_HORIZON_DAYS

    stockout_model = RandomForestClassifier(
        n_estimators=100,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=-1,
    )
    stockout_model.fit(
        training_demand[STOCKOUT_FEATURES], training_demand["stockout_7_day"]
    )
    stockout_validation = demand_validation
    stockout_validation_predictions = stockout_model.predict(
        stockout_validation[STOCKOUT_FEATURES]
    )
    stockout_validation_probabilities = stockout_model.predict_proba(
        stockout_validation[STOCKOUT_FEATURES]
    )[:, list(stockout_model.classes_).index(1)] if 1 in stockout_model.classes_ else np.zeros(len(stockout_validation))
    stockout_test = demand_test
    stockout_predictions = stockout_model.predict(stockout_test[STOCKOUT_FEATURES])
    stockout_probabilities = stockout_model.predict_proba(
        stockout_test[STOCKOUT_FEATURES]
    )[:, list(stockout_model.classes_).index(1)] if 1 in stockout_model.classes_ else np.zeros(len(stockout_test))
    majority_label = int(training_demand["stockout_7_day"].mean() >= 0.5)

    sales_model = RandomForestRegressor(
        n_estimators=100, min_samples_leaf=2, random_state=random_state, n_jobs=-1
    )
    sales_model.fit(training_sales[SALES_FEATURES], training_sales["revenue"])
    sales_validation = sales_split["validation"]
    sales_validation_predictions = sales_model.predict(
        sales_validation[SALES_FEATURES]
    )
    sales_validation_baseline = sales_validation["rolling_7_revenue"].to_numpy()
    sales_test = sales_split["test"]
    sales_predictions = sales_model.predict(sales_test[SALES_FEATURES])
    sales_baseline = sales_test["rolling_7_revenue"].to_numpy()

    anomaly_split = _chronological_split(sales_df, "forecast_date")
    anomaly_model = IsolationForest(
        n_estimators=100, contamination=0.03, random_state=random_state
    )
    anomaly_model.fit(anomaly_split["train"][ANOMALY_FEATURES])

    evaluation = {
        "sample_counts": {
            "demand": {key: len(value) for key, value in demand_split.items() if key != "periods"},
            "sales": {key: len(value) for key, value in sales_split.items() if key != "periods"},
        },
        "periods": {
            "demand": demand_split["periods"],
            "sales": sales_split["periods"],
        },
        "demand_forecasting": {
            "validation": _regression_metrics(
                demand_validation["demand_7_day"],
                demand_validation_predictions,
                demand_validation_baseline,
            ),
            "test": _regression_metrics(
                demand_test["demand_7_day"], demand_predictions, demand_baseline
            ),
            "rolling_origin": _rolling_origin_regression(
                pd.concat([training_demand, demand_validation]),
                "date",
                DEMAND_FEATURES,
                "demand_7_day",
                "rolling_7",
                FORECAST_HORIZON_DAYS,
                random_state,
            ),
        },
        "sales_forecasting": {
            "validation": _regression_metrics(
                sales_validation["revenue"],
                sales_validation_predictions,
                sales_validation_baseline,
            ),
            "test": _regression_metrics(
                sales_test["revenue"], sales_predictions, sales_baseline
            ),
            "rolling_origin": _rolling_origin_regression(
                pd.concat([training_sales, sales_validation]),
                "forecast_date",
                SALES_FEATURES,
                "revenue",
                "rolling_7_revenue",
                random_state=random_state,
            ),
        },
        "stockout_prediction": {
            "validation": _binary_metrics(
                stockout_validation["stockout_7_day"],
                stockout_validation_predictions,
                stockout_validation_probabilities,
                majority_label,
            ),
            "test": _binary_metrics(
                stockout_test["stockout_7_day"],
                stockout_predictions,
                stockout_probabilities,
                majority_label,
            ),
            "rolling_origin": _rolling_origin_classifier(
                pd.concat([training_demand, stockout_validation]),
                "date",
                STOCKOUT_FEATURES,
                "stockout_7_day",
                random_state,
            ),
        },
        "anomaly_detection": {
            "algorithm": "IsolationForest",
            "evaluation": "unsupervised; no synthetic accuracy claim",
            "fit_samples": len(anomaly_split["train"]),
        },
    }

    # Keep the final test period untouched; the deployed artifact only sees earlier dates.
    final_demand = pd.concat([demand_split["train"], demand_split["validation"]])
    final_sales = pd.concat([sales_split["train"], sales_split["validation"]])
    demand_model.fit(final_demand[DEMAND_FEATURES], final_demand["demand_7_day"])
    stockout_model.fit(final_demand[STOCKOUT_FEATURES], final_demand["stockout_7_day"])
    sales_model.fit(final_sales[SALES_FEATURES], final_sales["revenue"])
    anomaly_model.fit(
        pd.concat([anomaly_split["train"], anomaly_split["validation"]])[ANOMALY_FEATURES]
    )

    trained_at = datetime.now(timezone.utc).isoformat()
    bundle = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "demand_model": demand_model,
        "stockout_model": stockout_model,
        "sales_model": sales_model,
        "anomaly_model": anomaly_model,
        "demand_features": DEMAND_FEATURES,
        "stockout_features": STOCKOUT_FEATURES,
        "sales_features": SALES_FEATURES,
        "anomaly_features": ANOMALY_FEATURES,
        "feature_metadata": FEATURE_METADATA,
        "model_version": MODEL_VERSION,
        "trained_at": trained_at,
        "training_source": "synthetic_retail_data",
        "validation_status": "experimental_synthetic",
        "evaluation": evaluation,
        "random_state": random_state,
    }
    metrics = {
        "model_version": MODEL_VERSION,
        "schema_version": MODEL_SCHEMA_VERSION,
        "trained_at": trained_at,
        "training_source": "synthetic_retail_data",
        "validation_status": "experimental_synthetic",
        "validation_limitations": [
            "Synthetic data only; metrics are not evidence of merchant accuracy.",
            "Synthetic demand has no stock censoring, promotion plan, or merchant-specific seasonality.",
            "Anomaly detection is unsupervised and has no ground-truth accuracy metric.",
        ],
        "random_state": random_state,
        "feature_metadata": FEATURE_METADATA,
        **evaluation,
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    load_models.cache_clear()
    return metrics


class ModelArtifactError(FileNotFoundError):
    """Raised when a trained model bundle is missing, stale, or unusable."""


def _artifact_is_valid(bundle):
    if not isinstance(bundle, dict):
        return False
    expected_features = {
        "demand_features": DEMAND_FEATURES,
        "stockout_features": STOCKOUT_FEATURES,
        "sales_features": SALES_FEATURES,
        "anomaly_features": ANOMALY_FEATURES,
    }
    if (
        bundle.get("schema_version") != MODEL_SCHEMA_VERSION
        or bundle.get("model_version") != MODEL_VERSION
        or bundle.get("training_source") != "synthetic_retail_data"
        or bundle.get("validation_status") != "experimental_synthetic"
        or bundle.get("feature_metadata") != FEATURE_METADATA
        or any(bundle.get(key) != value for key, value in expected_features.items())
    ):
        return False
    model_methods = {
        "demand_model": ("predict",),
        "stockout_model": ("predict_proba",),
        "sales_model": ("predict",),
        "anomaly_model": ("predict", "decision_function"),
    }
    feature_lengths = {
        "demand_model": len(DEMAND_FEATURES),
        "stockout_model": len(STOCKOUT_FEATURES),
        "sales_model": len(SALES_FEATURES),
        "anomaly_model": len(ANOMALY_FEATURES),
    }
    return all(
        all(callable(getattr(bundle.get(key), method, None)) for method in methods)
        and getattr(bundle[key], "n_features_in_", None) == feature_lengths[key]
        for key, methods in model_methods.items()
    )


@lru_cache(maxsize=1)
def load_models():
    if not MODEL_PATH.is_file():
        raise ModelArtifactError(
            "ML model artifact is missing. Run the v2 training script before requesting model predictions."
        )
    try:
        bundle = joblib.load(MODEL_PATH)
    except (
        OSError,
        EOFError,
        ValueError,
        ImportError,
        AttributeError,
        KeyError,
        pickle.UnpicklingError,
        zlib.error,
    ):
        raise ModelArtifactError(
            "ML model artifact is unreadable or incompatible. Retrain it with the current v2 pipeline."
        ) from None
    required_keys = {
        "schema_version",
        "demand_model",
        "stockout_model",
        "sales_model",
        "anomaly_model",
        "demand_features",
        "stockout_features",
        "sales_features",
        "anomaly_features",
        "feature_metadata",
        "model_version",
        "training_source",
        "validation_status",
    }
    if not isinstance(bundle, dict) or not required_keys.issubset(bundle):
        raise ModelArtifactError(
            "ML model artifact is incomplete. Retrain it with the current v2 pipeline."
        )
    if not _artifact_is_valid(bundle):
        raise ModelArtifactError(
            "ML model artifact is stale or incompatible with the current feature schema. Retrain it with the current v2 pipeline."
        )
    return bundle


def _feature_frame(features: Mapping, expected_features):
    if not isinstance(features, Mapping):
        raise ValueError("Prediction features must be a mapping of feature names to numbers.")
    missing = set(expected_features) - set(features)
    unexpected = set(features) - set(expected_features)
    if missing or unexpected:
        raise ValueError(
            f"Prediction feature mismatch; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}."
        )
    values = []
    for name in expected_features:
        value = features[name]
        if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
            raise ValueError(f"Prediction feature '{name}' must be numeric.")
        numeric_value = float(value)
        if not math.isfinite(numeric_value) or numeric_value < 0:
            raise ValueError(
                f"Prediction feature '{name}' must be finite and non-negative."
            )
        if name == "day_of_week" and numeric_value > 6:
            raise ValueError("Prediction feature 'day_of_week' must be between 0 and 6.")
        if name == "month" and not 1 <= numeric_value <= 12:
            raise ValueError("Prediction feature 'month' must be between 1 and 12.")
        if name == "is_weekend" and numeric_value not in (0, 1):
            raise ValueError("Prediction feature 'is_weekend' must be 0 or 1.")
        values.append(numeric_value)
    return pd.DataFrame([values], columns=expected_features)


def _model_response():
    return {
        "model_version": MODEL_VERSION,
        "status": "experimental_synthetic",
        "limitations": "Trained on synthetic data; not validated for a specific merchant.",
    }


def predict_demand(features):
    bundle = load_models()
    data = _feature_frame(features, bundle["demand_features"])
    prediction = max(0.0, float(bundle["demand_model"].predict(data)[0]))
    return {"predicted_7_day_demand": round(prediction, 2), **_model_response()}


def predict_stockout_risk(features):
    bundle = load_models()
    data = _feature_frame(features, bundle["stockout_features"])
    model = bundle["stockout_model"]
    probabilities = model.predict_proba(data)[0]
    classes = list(model.classes_)
    risk = float(probabilities[classes.index(1)]) if 1 in classes else 0.0
    return {
        "stockout_probability": round(risk, 4),
        "risk_percentage": round(risk * 100, 2),
        "risk_level": (
            "critical" if risk >= 0.75
            else "high" if risk >= 0.50
            else "moderate" if risk >= 0.25
            else "low"
        ),
        **_model_response(),
    }


def predict_sales(features):
    bundle = load_models()
    data = _feature_frame(features, bundle["sales_features"])
    prediction = max(0.0, float(bundle["sales_model"].predict(data)[0]))
    return {"predicted_revenue": round(prediction, 2), **_model_response()}


def detect_sales_anomaly(features):
    bundle = load_models()
    data = _feature_frame(features, bundle["anomaly_features"])
    model = bundle["anomaly_model"]
    return {
        "is_anomaly": int(model.predict(data)[0]) == -1,
        "anomaly_score": round(float(model.decision_function(data)[0]), 4),
        **_model_response(),
    }
