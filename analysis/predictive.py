import pandas as pd
import numpy as np
import sqlite3
from analysis.meta_evolution import get_meta_share


def forecast_meta(conn: sqlite3.Connection, top_n: int = 15,
                  periods: int = 3) -> pd.DataFrame:
    """Forecast meta share for top N archetypes using exponential smoothing."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    df = get_meta_share(conn)
    pivot = df.pivot_table(index="month", columns="archetype",
                           values="meta_share_pct", fill_value=0)

    total_share = pivot.sum()
    top_archetypes = total_share.nlargest(top_n).index.tolist()

    forecasts = []
    for arch in top_archetypes:
        series = pivot[arch]
        if len(series) < 6:
            continue

        try:
            model = ExponentialSmoothing(
                series.values,
                trend="add",
                damped_trend=True,
                seasonal=None,
            ).fit(optimized=True)

            pred = model.forecast(periods)
            last_month = series.index[-1]

            for i, val in enumerate(pred):
                forecasts.append({
                    "archetype": arch,
                    "period": i + 1,
                    "forecast_share": max(0, round(val, 2)),
                    "current_share": round(series.values[-1], 2),
                })
        except Exception:
            continue

    return pd.DataFrame(forecasts)


def meta_reaction_model(conn: sqlite3.Connection,
                        target_archetype: str,
                        top_n: int = 15) -> dict:
    """Random Forest model using lagged features of all archetypes."""
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import mean_absolute_error

    df = get_meta_share(conn)
    pivot = df.pivot_table(index="month", columns="archetype",
                           values="meta_share_pct", fill_value=0)

    total_share = pivot.sum()
    top = total_share.nlargest(top_n).index.tolist()
    if target_archetype not in top:
        top.append(target_archetype)

    data = pivot[top].copy()

    for lag in [1, 2, 3]:
        shifted = data.shift(lag)
        shifted.columns = [f"{c}_lag{lag}" for c in shifted.columns]
        data = pd.concat([data, shifted], axis=1)

    data = data.dropna()
    if len(data) < 10:
        return {"error": "Not enough data"}

    y = data[target_archetype]
    X = data.drop(columns=top)

    tscv = TimeSeriesSplit(n_splits=3)
    scores = []

    for train_idx, test_idx in tscv.split(X):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        scores.append(mean_absolute_error(y_test, pred))

    final_model = RandomForestRegressor(n_estimators=100, random_state=42)
    final_model.fit(X, y)

    feature_importance = pd.Series(
        final_model.feature_importances_, index=X.columns
    ).sort_values(ascending=False).head(10)

    return {
        "mae": round(np.mean(scores), 3),
        "feature_importance": feature_importance.to_dict(),
        "last_prediction": round(final_model.predict(X.iloc[[-1]])[0], 2),
    }
