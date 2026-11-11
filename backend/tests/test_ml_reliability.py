import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
from sqlalchemy.dialects import postgresql

from ml import retail_ml
from services import ml_integration_service


class TrainingDataTests(unittest.TestCase):
    def test_seed_reproduces_synthetic_records(self):
        first_demand, first_sales = retail_ml.generate_training_data(
            product_count=2, days=50, random_state=17
        )
        second_demand, second_sales = retail_ml.generate_training_data(
            product_count=2, days=50, random_state=17
        )
        pd.testing.assert_frame_equal(first_demand, second_demand)
        pd.testing.assert_frame_equal(first_sales, second_sales)

    def test_demand_target_covers_only_the_future_seven_days(self):
        demand = list(range(1, 21))
        target, stockout = retail_ml._demand_target(
            demand, forecast_day=5, stock_on_hand=50
        )
        self.assertEqual(target, sum(demand[5:12]))
        self.assertEqual(stockout, int(target > 50))

    def test_sales_features_end_before_the_forecast_date(self):
        units = list(range(1, 21))
        revenue = [value * 10 for value in units]
        orders = [max(value // 2, 1) for value in units]
        day = 10
        forecast_date = pd.Timestamp("2026-01-11")
        features = retail_ml._sales_features(
            units, revenue, orders, day, forecast_date
        )

        self.assertEqual(features["lag_1_units"], units[day - 1])
        self.assertEqual(features["rolling_7_revenue"], np.mean(revenue[day - 7:day]))
        altered_target_day = units.copy()
        altered_target_day[day] = 100000
        self.assertEqual(
            features,
            retail_ml._sales_features(
                altered_target_day, revenue, orders, day, forecast_date
            ),
        )
        self.assertNotIn("revenue", retail_ml.SALES_FEATURES)
        self.assertNotIn("units_sold", retail_ml.SALES_FEATURES)
        self.assertNotIn("average_price", retail_ml.SALES_FEATURES)

    def test_chronological_partitions_do_not_overlap(self):
        frame = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=40).repeat(2),
            "value": range(80),
        })
        split = retail_ml._chronological_split(frame, "date")
        dates = {
            key: set(pd.to_datetime(part["date"]).dt.date)
            for key, part in split.items()
            if key != "periods"
        }
        self.assertFalse(dates["train"] & dates["validation"])
        self.assertFalse(dates["validation"] & dates["test"])
        self.assertFalse(dates["train"] & dates["test"])
        self.assertLess(max(dates["train"]), min(dates["validation"]))
        self.assertLess(max(dates["validation"]), min(dates["test"]))

    def test_rolling_origin_folds_train_only_on_earlier_dates(self):
        frame = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=80),
            "feature": np.arange(80, dtype=float),
            "target": np.arange(80, dtype=float) * 2,
            "baseline": np.arange(80, dtype=float),
        })
        result = retail_ml._rolling_origin_regression(
            frame,
            "date",
            ["feature"],
            "target",
            "baseline",
            random_state=5,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["folds"]), 2)
        for fold in result["folds"]:
            self.assertLess(fold["train_end"], fold["validation_period"][0])
            self.assertGreater(fold["sample_count"], 0)

    def test_training_saves_versioned_metrics_without_touching_test_period(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "models.joblib"
            metrics_path = Path(directory) / "metrics.json"
            with (
                patch.object(retail_ml, "MODEL_PATH", model_path),
                patch.object(retail_ml, "METRICS_PATH", metrics_path),
            ):
                metrics = retail_ml.train_models(
                    product_count=3, days=50, random_state=3
                )
                retail_ml.load_models.cache_clear()
                bundle = retail_ml.load_models()
                retail_ml.load_models.cache_clear()

            self.assertEqual(bundle["model_version"], retail_ml.MODEL_VERSION)
            self.assertEqual(metrics["validation_status"], "experimental_synthetic")
            self.assertIn("mae", metrics["sales_forecasting"]["test"]["model"])
            self.assertIn("mae", metrics["sales_forecasting"]["test"]["baseline"])
            self.assertIn(
                "confusion_matrix",
                metrics["stockout_prediction"]["test"]["model"],
            )
            self.assertEqual(metrics["training_source"], "synthetic_retail_data")
            self.assertEqual(metrics["sample_counts"]["sales"]["test"] > 0, True)


class PredictionValidationTests(unittest.TestCase):
    def test_feature_input_rejects_missing_extra_and_nonfinite_values(self):
        valid = {feature: 1 for feature in retail_ml.DEMAND_FEATURES}
        retail_ml._feature_frame(valid, retail_ml.DEMAND_FEATURES)

        with self.assertRaisesRegex(ValueError, "feature mismatch"):
            retail_ml._feature_frame(
                {"lag_1": 1}, retail_ml.DEMAND_FEATURES
            )
        with self.assertRaisesRegex(ValueError, "unexpected"):
            retail_ml._feature_frame(
                {**valid, "target": 99}, retail_ml.DEMAND_FEATURES
            )
        with self.assertRaisesRegex(ValueError, "finite"):
            retail_ml._feature_frame(
                {**valid, "price": float("nan")}, retail_ml.DEMAND_FEATURES
            )
        with self.assertRaisesRegex(ValueError, "day_of_week"):
            retail_ml._feature_frame(
                {**valid, "day_of_week": 7}, retail_ml.DEMAND_FEATURES
            )

    def test_old_artifact_schema_is_rejected(self):
        self.assertFalse(retail_ml._artifact_is_valid({
            "model_version": "1.0.0",
            "demand_features": retail_ml.DEMAND_FEATURES,
        }))


class ShopIsolationTests(unittest.TestCase):
    def test_shop_lookup_is_scoped_to_the_authenticated_owner(self):
        db = Mock()
        db.scalar.return_value = None
        user = type("User", (), {"id": "merchant-a"})()
        shop_id = "shop-b"

        with self.assertRaisesRegex(ValueError, "access denied"):
            ml_integration_service.verify_shop(db, user, shop_id)

        statement = db.scalar.call_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("shops.owner_id", sql)
        self.assertIn("shops.id", sql)


if __name__ == "__main__":
    unittest.main()
