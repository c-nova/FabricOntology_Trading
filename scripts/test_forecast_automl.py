import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from forecast_automl_core import (
    GRAPH_FEATURES, HORIZON, HOLDOUT_ORIGIN, VALIDATION_ORIGIN,
    prepare_features, rows_at, run_comparison, training_rows,
)

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    data = json.loads((ROOT / "data/demo_dataset.json").read_text())["LH_Group_SAP"]
    metrics = pd.DataFrame(data["semantic_financial_metrics_daily"])
    effects = pd.DataFrame(data["semantic_event_financial_effects"])
    links = pd.DataFrame(data["semantic_effect_metric_links"])
    events = pd.DataFrame(data["semantic_risk_events"])
    paths = effects[["effect_id", "event_id", "entity_id"]].merge(
        links, on="effect_id", validate="one_to_one"
    ).merge(events[["event_id", "start_date"]], on="event_id", validate="many_to_one")
    return metrics, effects, links, paths.rename(columns={"start_date": "event_start_date"})


class ForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics, cls.effects, cls.links, cls.paths = fixture()
        cls.frame, cls.base, cls.audit = prepare_features(
            cls.metrics, cls.effects, cls.links, cls.paths
        )

    def test_graph_coverage_and_q4_baseline(self):
        self.assertEqual(self.audit["graph_paths"], 1344)
        q4 = rows_at(self.frame, HOLDOUT_ORIGIN)
        self.assertAlmostEqual(q4["target_oku"].sum(), 115.614, places=3)
        self.assertAlmostEqual(q4["mean_91"].sum() * HORIZON, 113.613, places=3)

    def test_no_validation_label_crosses_origin(self):
        rows = training_rows(self.frame, VALIDATION_ORIGIN)
        self.assertLessEqual(rows["target_end"].max(), VALIDATION_ORIGIN)
        self.assertEqual(rows_at(self.frame, VALIDATION_ORIGIN)["target_end"].max(), HOLDOUT_ORIGIN)

    def test_future_changes_do_not_change_as_of_features(self):
        metrics = self.metrics.copy()
        effects = self.effects.copy()
        metrics.loc[pd.to_datetime(metrics["metric_date"]) > HOLDOUT_ORIGIN, "amount_group"] = "999999999"
        effects.loc[pd.to_datetime(effects["effect_date"]) > HOLDOUT_ORIGIN, "delta_ebitda_full_jpy"] = "999999999"
        changed, _, _ = prepare_features(metrics, effects, self.links, self.paths)
        cols = self.base + GRAPH_FEATURES
        np.testing.assert_allclose(
            rows_at(self.frame, HOLDOUT_ORIGIN)[cols],
            rows_at(changed, HOLDOUT_ORIGIN)[cols],
        )

    def test_rejects_missing_graph_path(self):
        with self.assertRaisesRegex(ValueError, "Graph and Lakehouse"):
            prepare_features(self.metrics, self.effects, self.links, self.paths.iloc[1:])

    def test_automl_comparison_runs(self):
        result = run_comparison(self.frame, self.base, time_budget=3)
        self.assertEqual([x["model"] for x in result["results"]],
                         ["直近91日日平均", "AutoML", "AutoML + Graph"])
        self.assertTrue(all(np.isfinite(x["next_q_forecast_oku"]) for x in result["results"]))
        expected_ids = sorted(self.frame["entity_id"].unique())
        for row in result["results"]:
            parts = row["next_q_by_entity_oku"]
            self.assertEqual([p["entity_id"] for p in parts], expected_ids)
            self.assertTrue(all(np.isfinite(p["amount_oku"]) for p in parts))
            self.assertAlmostEqual(sum(p["amount_oku"] for p in parts), row["next_q_forecast_oku"], places=9)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
