"""Time-aware 92-day EBITDA forecasts from graph-linked historical effects."""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZON = 92
HOLDOUT_ORIGIN = pd.Timestamp("2026-06-30")
FUTURE_ORIGIN = pd.Timestamp("2026-09-30")
VALIDATION_ORIGIN = pd.Timestamp("2026-03-30")
FIRST_ORIGIN = pd.Timestamp("2025-10-28")
GRAPH_FEATURES = ["graph_amount_28", "graph_amount_91", "graph_paths_28", "graph_paths_91"]


def prepare_features(metrics, effects, links, paths):
    """Verify graph/source paths, then construct features using only past rows."""
    m = metrics.loc[
        (metrics["metric_code"] == "EBITDA") & (metrics["scenario_tag"] == "actual"),
        ["metric_id", "metric_date", "entity_id", "amount_group"],
    ].copy()
    m["metric_date"] = pd.to_datetime(m["metric_date"]).dt.normalize()
    if m["metric_id"].duplicated().any() or m.duplicated(["entity_id", "metric_date"]).any():
        raise ValueError("Duplicate actual EBITDA metric")
    m["amount_oku"] = pd.to_numeric(m["amount_group"]) / 100_000_000
    if m["amount_oku"].isna().any():
        raise ValueError("Missing EBITDA amount")

    e = effects[["effect_id", "event_id", "entity_id", "effect_date", "delta_ebitda_full_jpy"]].copy()
    e["effect_date"] = pd.to_datetime(e["effect_date"]).dt.normalize()
    if e["effect_id"].duplicated().any() or links["effect_id"].duplicated().any():
        raise ValueError("Duplicate effect or effect-to-metric link")
    source = e.merge(links[["effect_id", "metric_id"]], on="effect_id", validate="one_to_one")
    source = source.merge(
        m[["metric_id", "entity_id", "metric_date"]],
        on="metric_id", suffixes=("", "_metric"), validate="many_to_one",
    )
    if len(source) != len(e):
        raise ValueError("Some effects have no actual EBITDA metric")
    if not ((source["entity_id"] == source["entity_id_metric"]) &
            (source["effect_date"] == source["metric_date"])).all():
        raise ValueError("Effect and metric entity/date do not match")

    p = paths[["effect_id", "event_id", "entity_id", "metric_id", "event_start_date"]].copy()
    p["event_start_date"] = pd.to_datetime(p["event_start_date"]).dt.normalize()
    if p["effect_id"].duplicated().any() or set(p["effect_id"]) != set(source["effect_id"]):
        raise ValueError("Graph and Lakehouse effect membership differ")
    verified = source.merge(
        p, on=["effect_id", "event_id", "entity_id", "metric_id"], validate="one_to_one",
    )
    if len(verified) != len(source) or not (verified["event_start_date"] <= verified["effect_date"]).all():
        raise ValueError("Graph path mapping or event dates differ from Lakehouse")
    verified["effect_oku"] = pd.to_numeric(verified["delta_ebitda_full_jpy"]) / 100_000_000
    daily_effects = verified.groupby(["entity_id", "effect_date"], as_index=False).agg(
        effect_oku=("effect_oku", "sum"), graph_paths=("effect_id", "size"),
    ).rename(columns={"effect_date": "metric_date"})
    m = m.merge(daily_effects, on=["entity_id", "metric_date"], how="left", validate="one_to_one")
    m[["effect_oku", "graph_paths"]] = m[["effect_oku", "graph_paths"]].fillna(0)

    companies = sorted(m["entity_id"].unique())
    if len(companies) != 8:
        raise ValueError(f"Expected eight subsidiaries, got {len(companies)}")
    frames = []
    for company, group in m.groupby("entity_id", sort=True):
        group = group.sort_values("metric_date").reset_index(drop=True)
        expected = pd.date_range("2025-10-01", "2026-09-30", freq="D")
        if not pd.DatetimeIndex(group["metric_date"]).equals(expected):
            raise ValueError(f"Missing, duplicate, or unexpected daily dates for {company}")
        values = group["amount_oku"].to_numpy(dtype=float)
        cumulative = np.r_[0.0, values.cumsum()]
        labels = np.full(len(group), np.nan)
        labels[:-HORIZON] = cumulative[HORIZON + 1:] - cumulative[1:-HORIZON]
        group["target_oku"] = labels
        group["target_end"] = group["metric_date"] + pd.Timedelta(days=HORIZON)
        for days in (7, 28, 91):
            group[f"mean_{days}"] = group["amount_oku"].rolling(days, min_periods=days).mean()
        group["std_28"] = group["amount_oku"].rolling(28, min_periods=28).std()
        # Early training examples have 28–90 days of history; expose the window length.
        group["mean_91"] = group["amount_oku"].rolling(91, min_periods=28).mean()
        group["history_91"] = np.minimum(np.arange(1, len(group) + 1), 91)
        for days in (28, 91):
            group[f"graph_amount_{days}"] = group["effect_oku"].rolling(days, min_periods=1).sum()
            group[f"graph_paths_{days}"] = group["graph_paths"].rolling(days, min_periods=1).sum()
        for name in companies:
            group[f"company_{name}"] = int(company == name)
        frames.append(group)
    frame = pd.concat(frames, ignore_index=True)
    base = ["mean_7", "mean_28", "mean_91", "std_28", "history_91"]
    base += [f"company_{name}" for name in companies]
    return frame, base, {
        "graph_paths": len(verified),
        "companies": len(companies),
        "first_date": str(m["metric_date"].min().date()),
        "last_date": str(m["metric_date"].max().date()),
    }


def rows_at(frame, origin):
    rows = frame.loc[frame["metric_date"] == origin].sort_values("entity_id").copy()
    if len(rows) != 8:
        raise ValueError(f"Expected eight rows at {origin.date()}")
    return rows


def training_rows(frame, known_through):
    eligible = frame.loc[
        (frame["metric_date"] >= FIRST_ORIGIN) &
        (frame["target_end"] <= known_through) &
        frame["target_oku"].notna()
    ].copy()
    eligible = eligible.loc[((eligible["metric_date"] - FIRST_ORIGIN).dt.days % 7) == 0]
    if eligible.empty or eligible["target_end"].max() > known_through:
        raise ValueError("No training labels available at the requested cutoff")
    return eligible.sort_values(["metric_date", "entity_id"])


def _xy(rows, columns):
    x = rows[columns].to_numpy(dtype=float)
    y = rows["target_oku"].to_numpy(dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Training or validation data contains missing/nonfinite values")
    return x, y


def search_model(frame, columns, time_budget=20):
    from flaml import AutoML

    train = training_rows(frame, VALIDATION_ORIGIN)
    validation = rows_at(frame, VALIDATION_ORIGIN)
    if validation["target_end"].max() > HOLDOUT_ORIGIN:
        raise ValueError("Model selection used Q4 data")
    x_train, y_train = _xy(train, columns)
    x_val, y_val = _xy(validation, columns)
    model = AutoML()
    model.fit(
        X_train=x_train, y_train=y_train, X_val=x_val, y_val=y_val,
        task="regression", metric="mae", eval_method="holdout",
        estimator_list=["rf", "extra_tree"], time_budget=time_budget,
        n_jobs=1, seed=41, sample=False, retrain_full=False,
        mlflow_logging=False, log_file_name="", verbose=0,
    )
    if model.model is None or model.best_estimator is None:
        raise RuntimeError("AutoML did not produce a model")
    return model, {"training_rows": len(train), "validation_rows": len(validation),
                   "validation_mae_company_oku": float(model.best_loss)}


def refit_predict(search, frame, columns, origin):
    train = training_rows(frame, origin)
    x_train, y_train = _xy(train, columns)
    config = dict(search.best_config)
    config.pop("FLAML_sample_size", None)
    config.setdefault("n_jobs", 1)
    model = type(search.model)(task="regression", **config)
    model.fit(x_train, y_train)
    selected = rows_at(frame, origin)
    features = selected[columns].to_numpy(dtype=float)
    if not np.isfinite(features).all():
        raise ValueError("Forecast features contain missing/nonfinite values")
    prediction = np.asarray(model.predict(features), dtype=float)
    if prediction.shape != (8,) or not np.isfinite(prediction).all():
        raise ValueError("Model produced invalid subsidiary predictions")
    return prediction, len(train)


def run_comparison(frame, base_columns, time_budget=20):
    """Compare identical point-in-time inputs, then refit without Q4 tuning."""
    q4 = rows_at(frame, HOLDOUT_ORIGIN)
    actual = q4["target_oku"].to_numpy(dtype=float)
    if not np.isfinite(actual).all():
        raise ValueError("Held-out Q4 actuals are incomplete")
    future = rows_at(frame, FUTURE_ORIGIN)
    entity_ids = future["entity_id"].tolist()
    if entity_ids != q4["entity_id"].tolist() or len(set(entity_ids)) != len(entity_ids):
        raise ValueError("Holdout and forecast rows do not describe the same companies")
    scores = []
    summaries = []
    for name, columns in (
        ("AutoML", base_columns),
        ("AutoML + Graph", base_columns + GRAPH_FEATURES),
    ):
        search, validation = search_model(frame, columns, time_budget)
        q4_prediction, q4_training = refit_predict(search, frame, columns, HOLDOUT_ORIGIN)
        future_prediction, future_training = refit_predict(search, frame, columns, FUTURE_ORIGIN)
        scores.append((name, q4_prediction, future_prediction))
        summaries.append({
            "model": name, "best_estimator": search.best_estimator,
            "validation": validation, "q4_training_rows": q4_training,
            "future_training_rows": future_training,
        })
    scores.insert(0, (
        "直近91日日平均", q4["mean_91"].to_numpy(dtype=float) * HORIZON,
        future["mean_91"].to_numpy(dtype=float) * HORIZON,
    ))
    results = []
    for name, prediction, future_prediction in scores:
        total, actual_total = float(prediction.sum()), float(actual.sum())
        results.append({
            "model": name, "q4_forecast_oku": total, "q4_actual_oku": actual_total,
            "q4_error_oku": total - actual_total,
            "q4_error_percent": (total - actual_total) / actual_total * 100,
            "q4_company_mae_oku": float(np.abs(prediction - actual).mean()),
            "next_q_forecast_oku": float(future_prediction.sum()),
            # 画面の積み上げ棒（業種別）に使う。合計は next_q_forecast_oku と一致する
            "next_q_by_entity_oku": [
                {"entity_id": entity, "amount_oku": float(value)}
                for entity, value in zip(entity_ids, future_prediction)
            ],
        })
    return {"results": results, "models": summaries,
            "validation_origin": str(VALIDATION_ORIGIN.date()),
            "q4_origin": str(HOLDOUT_ORIGIN.date()),
            "future_origin": str(FUTURE_ORIGIN.date()),
            "horizon_days": HORIZON}
