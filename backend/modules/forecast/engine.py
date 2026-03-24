import json
import math
import re
import unicodedata
import calendar
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing, Holt
from statsmodels.tsa.statespace.sarimax import SARIMAX

try:
    from prophet import Prophet
except Exception:  # pragma: no cover - optionnel
    Prophet = None

from database import db


BASE_AGGREGATES: Dict[str, Dict[str, object]] = {
    "ca_brut": {"label": "CA Brut", "nature": "produit", "is_derived": False},
    "retrocessions": {"label": "Retrocessions", "nature": "charge", "is_derived": False},
    "autres_produits": {"label": "Autres Produits Exploitation", "nature": "produit", "is_derived": False},
    "frais_personnel": {"label": "Frais Personnel", "nature": "charge", "is_derived": False},
    "honoraires": {"label": "Honoraires Sous-traitance", "nature": "charge", "is_derived": False},
    "frais_commerciaux": {"label": "Frais Commerciaux", "nature": "charge", "is_derived": False},
    "impots_taxes": {"label": "Impots Taxes", "nature": "charge", "is_derived": False},
    "fonctionnement": {"label": "Fonctionnement Courant", "nature": "charge", "is_derived": False},
    "autres_charges": {"label": "Autres Charges", "nature": "charge", "is_derived": False},
    "produits_financiers": {"label": "Produits Financiers", "nature": "produit", "is_derived": False},
    "charges_financieres": {"label": "Charges Financieres", "nature": "charge", "is_derived": False},
    "dotations": {"label": "Dotations Amortissements", "nature": "charge", "is_derived": False},
    "impot_societes": {"label": "Impot Societes", "nature": "charge", "is_derived": False},
    "produits_exceptionnels": {"label": "Produits Exceptionnels", "nature": "produit", "is_derived": False},
    "charges_exceptionnelles": {"label": "Charges Exceptionnelles", "nature": "charge", "is_derived": False},
}

DERIVED_AGGREGATES: Dict[str, Dict[str, object]] = {
    "ca_net": {"label": "CA Net", "nature": "produit", "is_derived": True},
    "total_produits": {"label": "Total Produits Exploitation", "nature": "produit", "is_derived": True},
    "total_charges": {"label": "Total Charges Courantes", "nature": "charge", "is_derived": True},
    "ebitda": {"label": "EBITDA", "nature": "produit", "is_derived": True},
    "ebitda_pct": {"label": "EBITDA %", "nature": "produit", "is_derived": True},
    "resultat_financier": {"label": "Resultat Financier", "nature": "produit", "is_derived": True},
    "resultat_exceptionnel": {"label": "Resultat Exceptionnel", "nature": "produit", "is_derived": True},
    "resultat_avant_impot": {"label": "Profit avant Impot", "nature": "produit", "is_derived": True},
    "resultat_net": {"label": "Resultat Net", "nature": "produit", "is_derived": True},
    "resultat_net_pct": {"label": "Resultat Net %", "nature": "produit", "is_derived": True},
}

ALL_AGGREGATES: Dict[str, Dict[str, object]] = {**BASE_AGGREGATES, **DERIVED_AGGREGATES}

CYCLE_CONFIG = {
    "M03": {"label": "Ajustement fin Mars", "cycle_month": 3},
    "M06": {"label": "Ajustement fin Juin", "cycle_month": 6},
    "M08": {"label": "Ajustement fin Août", "cycle_month": 8},
}

MONTH_COLUMNS = [
    "Janvier",
    "Fevrier",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Aout",
    "Septembre",
    "Octobre",
    "Novembre",
    "Decembre",
]

CSV_LABEL_TO_KEY = {
    "ca brut": "ca_brut",
    "retrocessions": "retrocessions",
    "autres produits d exploitation": "autres_produits",
    "autres produits exploitation": "autres_produits",
    "frais de personnel": "frais_personnel",
    "honoraires sous traitance": "honoraires",
    "honoraires  sous traitance": "honoraires",
    "frais commerciaux": "frais_commerciaux",
    "impots et taxes": "impots_taxes",
    "fonctionnement courant": "fonctionnement",
    "autres charges": "autres_charges",
    "produits financiers": "produits_financiers",
    "charges financieres": "charges_financieres",
    "dotations amortissements  provisions": "dotations",
    "dotations amortissements et provisions": "dotations",
    "impot sur les societes": "impot_societes",
    "produits exceptionnels": "produits_exceptionnels",
    "charges exceptionnelles": "charges_exceptionnelles",
}


@dataclass
class ModelForecast:
    model_name: str
    forecast: List[float]
    lower: List[Optional[float]]
    upper: List[Optional[float]]
    score: float


def _to_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if text == "" or text.lower() in {"nan", "none"}:
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9 ]+", " ", text).lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _nature_normalize(key: str, value: float) -> float:
    nature = ALL_AGGREGATES[key]["nature"]
    if nature == "charge":
        return abs(value)
    return value


def _build_derived_month(base_month: Dict[str, float]) -> Dict[str, float]:
    ca_brut = base_month.get("ca_brut", 0.0)
    retro = base_month.get("retrocessions", 0.0)
    autres_produits = base_month.get("autres_produits", 0.0)
    frais_personnel = base_month.get("frais_personnel", 0.0)
    honoraires = base_month.get("honoraires", 0.0)
    frais_commerciaux = base_month.get("frais_commerciaux", 0.0)
    impots_taxes = base_month.get("impots_taxes", 0.0)
    fonctionnement = base_month.get("fonctionnement", 0.0)
    autres_charges = base_month.get("autres_charges", 0.0)
    produits_financiers = base_month.get("produits_financiers", 0.0)
    charges_financieres = base_month.get("charges_financieres", 0.0)
    dotations = base_month.get("dotations", 0.0)
    produits_exceptionnels = base_month.get("produits_exceptionnels", 0.0)
    charges_exceptionnelles = base_month.get("charges_exceptionnelles", 0.0)
    impot_societes = base_month.get("impot_societes", 0.0)

    ca_net = ca_brut - retro
    total_produits = ca_net + autres_produits
    total_charges = (
        frais_personnel
        + honoraires
        + frais_commerciaux
        + impots_taxes
        + fonctionnement
        + autres_charges
    )
    ebitda = total_produits - total_charges
    ebitda_pct = (ebitda / ca_net * 100.0) if abs(ca_net) > 1e-9 else 0.0

    resultat_financier = produits_financiers - charges_financieres
    resultat_exceptionnel = produits_exceptionnels - charges_exceptionnelles
    resultat_avant_impot = ebitda + resultat_financier - dotations + resultat_exceptionnel
    resultat_net = resultat_avant_impot - impot_societes
    resultat_net_pct = (resultat_net / ca_net * 100.0) if abs(ca_net) > 1e-9 else 0.0

    return {
        "ca_net": ca_net,
        "total_produits": total_produits,
        "total_charges": total_charges,
        "ebitda": ebitda,
        "ebitda_pct": ebitda_pct,
        "resultat_financier": resultat_financier,
        "resultat_exceptionnel": resultat_exceptionnel,
        "resultat_avant_impot": resultat_avant_impot,
        "resultat_net": resultat_net,
        "resultat_net_pct": resultat_net_pct,
    }


def _load_history_from_db() -> Dict[str, List[Tuple[int, int, float]]]:
    history: Dict[str, List[Tuple[int, int, float]]] = {k: [] for k in BASE_AGGREGATES.keys()}
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT year, month, agregat_key, value
            FROM bfc_budget_history
            ORDER BY year ASC, month ASC
            """
        )
        rows = cursor.fetchall()

    for row in rows:
        key = row["agregat_key"]
        if key not in history:
            continue
        history[key].append((int(row["year"]), int(row["month"]), _nature_normalize(key, _to_float(row["value"]))))

    return history


def _load_actuals_for_year(target_year: int) -> Dict[int, Dict[str, float]]:
    actuals: Dict[int, Dict[str, float]] = {}
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT periode, resume
            FROM sage_bfc_monthly
            WHERE YEAR(periode) = %s
            ORDER BY periode ASC
            """,
            (target_year,),
        )
        rows = cursor.fetchall()

    for row in rows:
        period_date = row["periode"]
        month = int(period_date.month)
        resume_raw = row["resume"]
        resume = resume_raw if isinstance(resume_raw, dict) else json.loads(resume_raw)
        monthly = actuals.setdefault(month, {})
        for key in BASE_AGGREGATES.keys():
            value = _extract_resume_value(resume, key)
            monthly[key] = _nature_normalize(key, value)
    return actuals


def _extract_resume_value(resume: Dict[str, float], key: str) -> float:
    return _to_float(resume.get(key, 0.0))


def _metrics(y_true: List[float], y_pred: List[float]) -> Tuple[float, float, float]:
    arr_true = np.array(y_true, dtype=float)
    arr_pred = np.array(y_pred, dtype=float)
    mae = float(np.mean(np.abs(arr_true - arr_pred)))
    rmse = float(np.sqrt(np.mean((arr_true - arr_pred) ** 2)))

    denom = np.where(np.abs(arr_true) < 1e-9, 1.0, np.abs(arr_true))
    mape = float(np.mean(np.abs((arr_true - arr_pred) / denom)) * 100.0)
    return mae, rmse, mape


def _score_candidates(metrics_map: Dict[str, Tuple[float, float, float]]) -> Dict[str, float]:
    names = list(metrics_map.keys())
    mae_values = np.array([metrics_map[n][0] for n in names], dtype=float)
    rmse_values = np.array([metrics_map[n][1] for n in names], dtype=float)
    mape_values = np.array([metrics_map[n][2] for n in names], dtype=float)

    mae_rank = mae_values.argsort().argsort() + 1
    rmse_rank = rmse_values.argsort().argsort() + 1
    mape_rank = mape_values.argsort().argsort() + 1

    scores = {}
    for idx, name in enumerate(names):
        scores[name] = float(0.3 * mae_rank[idx] + 0.4 * rmse_rank[idx] + 0.3 * mape_rank[idx])
    return scores


def _forecast_prophet(series: List[float], horizon: int) -> Optional[List[float]]:
    if Prophet is None or len(series) < 12:
        return None
    try:
        start = pd.Timestamp("2000-01-01")
        idx = pd.date_range(start=start, periods=len(series), freq="MS")
        df = pd.DataFrame({"ds": idx, "y": np.array(series, dtype=float)})
        model = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False)
        model.fit(df)
        future = model.make_future_dataframe(periods=horizon, freq="MS")
        forecast = model.predict(future)["yhat"].tail(horizon).tolist()
        return [float(v) for v in forecast]
    except Exception:
        return None


def _candidate_models(train: List[float], horizon: int) -> Dict[str, List[float]]:
    arr = np.array(train, dtype=float)
    candidates: Dict[str, List[float]] = {}

    # Naive
    last_val = float(arr[-1]) if len(arr) else 0.0
    candidates["naive_last"] = [last_val] * horizon

    # Mean
    mean_val = float(np.mean(arr)) if len(arr) else 0.0
    candidates["mean"] = [mean_val] * horizon

    # Holt
    if len(arr) >= 6:
        try:
            holt_model = Holt(arr, exponential=False, damped_trend=True).fit(optimized=True)
            candidates["holt"] = [float(v) for v in holt_model.forecast(horizon)]
        except Exception:
            pass

    # ETS
    if len(arr) >= 8:
        try:
            ets_model = ExponentialSmoothing(arr, trend="add", seasonal=None).fit(optimized=True)
            candidates["ets"] = [float(v) for v in ets_model.forecast(horizon)]
        except Exception:
            pass

    # ARIMA
    if len(arr) >= 8:
        try:
            arima_model = ARIMA(arr, order=(1, 1, 1)).fit()
            candidates["arima_111"] = [float(v) for v in arima_model.forecast(horizon)]
        except Exception:
            pass

    # SARIMA
    if len(arr) >= 24:
        try:
            sarima_model = SARIMAX(
                arr,
                order=(1, 1, 1),
                seasonal_order=(1, 1, 1, 12),
                enforce_stationarity=False,
                enforce_invertibility=False,
            ).fit(disp=False)
            candidates["sarima_111x111_12"] = [float(v) for v in sarima_model.forecast(horizon)]
        except Exception:
            pass

    prophet_values = _forecast_prophet(train, horizon)
    if prophet_values is not None:
        candidates["prophet"] = prophet_values

    return candidates


def _forecast_series(series: List[float], horizon: int) -> ModelForecast:
    arr = np.array(series, dtype=float)
    arr = np.where(np.isfinite(arr), arr, 0.0)

    if len(arr) == 0:
        return ModelForecast("zeros", [0.0] * horizon, [0.0] * horizon, [0.0] * horizon, 0.0)

    if np.all(np.abs(arr) < 1e-9):
        return ModelForecast("zeros", [0.0] * horizon, [0.0] * horizon, [0.0] * horizon, 0.0)

    mean_val = float(np.mean(arr))
    std_val = float(np.std(arr))
    cv = abs(std_val / mean_val) if abs(mean_val) > 1e-9 else std_val
    if cv < 0.01 or std_val < 1.0:
        base = [mean_val] * horizon
        band = std_val if std_val > 0 else abs(mean_val) * 0.02
        return ModelForecast(
            "constant_mean",
            base,
            [v - band for v in base],
            [v + band for v in base],
            0.0,
        )

    holdout = max(1, min(4, len(arr) // 5))
    train = arr[:-holdout].tolist()
    test = arr[-holdout:].tolist()

    candidates = _candidate_models(train, holdout)
    if not candidates:
        base = [mean_val] * horizon
        return ModelForecast("fallback_mean", base, [None] * horizon, [None] * horizon, 99.0)

    metrics_map: Dict[str, Tuple[float, float, float]] = {}
    for name, pred in candidates.items():
        mae, rmse, mape = _metrics(test, pred)
        metrics_map[name] = (mae, rmse, mape)

    scores = _score_candidates(metrics_map)
    best_name = sorted(scores.items(), key=lambda x: x[1])[0][0]

    # Refit best model on full series
    full_candidates = _candidate_models(arr.tolist(), horizon)
    best_pred = full_candidates.get(best_name)
    if best_pred is None:
        best_name = "mean"
        best_pred = [mean_val] * horizon

    # Uncertainty proxy
    residual_std = float(np.std(arr[-min(12, len(arr)):])) if len(arr) else 0.0
    if residual_std < 1e-9:
        residual_std = abs(float(np.mean(arr))) * 0.05

    lower = [float(v - 1.96 * residual_std) for v in best_pred]
    upper = [float(v + 1.96 * residual_std) for v in best_pred]

    return ModelForecast(
        model_name=best_name,
        forecast=[float(v) for v in best_pred],
        lower=lower,
        upper=upper,
        score=float(scores.get(best_name, 0.0)),
    )


def _compute_alert(nature: str, actual: Optional[float], forecast: Optional[float]) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    if actual is None or forecast is None:
        return None, None, None

    diff = float(actual - forecast)
    pct = (diff / forecast * 100.0) if abs(forecast) > 1e-9 else None

    neutral_threshold = 2.0
    if pct is not None and abs(pct) <= neutral_threshold:
        level = "neutral"
    else:
        if nature == "produit":
            level = "positive" if diff >= 0 else "negative"
        else:
            level = "negative" if diff > 0 else "positive"

    return diff, pct, level


def _insert_forecast_run(target_year: int, cycle_code: str, cycle_month: Optional[int], meta: Dict[str, object]) -> int:
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO bfc_forecast_runs (forecast_year, cycle_code, cycle_month, status, metadata)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (target_year, cycle_code, cycle_month, "done", json.dumps(meta)),
        )
        return int(cursor.lastrowid)


def _upsert_forecast_value(
    run_id: int,
    target_year: int,
    cycle_code: str,
    key: str,
    month: int,
    forecast_value: float,
    lower_value: Optional[float],
    upper_value: Optional[float],
    model_name: str,
):
    meta = ALL_AGGREGATES[key]
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO bfc_forecast_values (
                run_id, forecast_year, cycle_code, agregat_key, agregat_label, nature, is_derived,
                month, forecast_value, lower_value, upper_value, model_name
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                run_id = VALUES(run_id),
                forecast_value = VALUES(forecast_value),
                lower_value = VALUES(lower_value),
                upper_value = VALUES(upper_value),
                model_name = VALUES(model_name),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                run_id,
                target_year,
                cycle_code,
                key,
                str(meta["label"]),
                str(meta["nature"]),
                bool(meta["is_derived"]),
                month,
                float(forecast_value),
                None if lower_value is None else float(lower_value),
                None if upper_value is None else float(upper_value),
                model_name,
            ),
        )


def _load_csv_budget(file_path: str, forced_year: Optional[int] = None) -> Tuple[int, Dict[str, Dict[int, float]]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {file_path}")

    year = forced_year
    if year is None:
        m = re.search(r"(20\d{2})", path.name)
        if not m:
            raise ValueError(f"Année non détectable depuis le nom de fichier: {path.name}")
        year = int(m.group(1))

    df = None
    for enc in ("utf-8", "latin-1", "cp1252", "iso-8859-1"):
        try:
            df = pd.read_csv(path, sep=";", encoding=enc, engine="python")
            break
        except Exception:
            continue
    if df is None:
        raise ValueError(f"Impossible de lire le CSV: {file_path}")
    result = {k: {} for k in BASE_AGGREGATES.keys()}

    for _, row in df.iterrows():
        label = _normalize_text(row.get("Libelle_SAGE", "") or row.get("Agregat_Budget", ""))
        key = CSV_LABEL_TO_KEY.get(label)
        if not key:
            # fallback sur Agregat_Budget
            label2 = _normalize_text(row.get("Agregat_Budget", ""))
            key = CSV_LABEL_TO_KEY.get(label2)
        if not key:
            continue

        for idx, month_name in enumerate(MONTH_COLUMNS, start=1):
            raw_value = row.get(month_name, 0.0)
            value = _nature_normalize(key, _to_float(raw_value))
            result[key][idx] = value

    return year, result


def _upsert_history_value(year: int, month: int, key: str, value: float, source_file: str):
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO bfc_budget_history (year, month, agregat_key, agregat_label, value, source_file)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                agregat_label = VALUES(agregat_label),
                value = VALUES(value),
                source_file = VALUES(source_file),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                year,
                month,
                key,
                str(ALL_AGGREGATES[key]["label"]),
                float(value),
                source_file,
            ),
        )


def sync_closed_years_into_history(before_year: int) -> Dict[str, object]:
    """
    Synchronise automatiquement les années clôturées (12 mois uploadés)
    depuis sage_bfc_monthly vers bfc_budget_history.
    Cette étape garantit que l'année N+1 utilise TOUT l'historique réel disponible.
    """
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT YEAR(periode) AS y, COUNT(DISTINCT MONTH(periode)) AS mcount
            FROM sage_bfc_monthly
            WHERE YEAR(periode) < %s
            GROUP BY YEAR(periode)
            HAVING COUNT(DISTINCT MONTH(periode)) = 12
            ORDER BY y ASC
            """,
            (before_year,),
        )
        complete_year_rows = cursor.fetchall()

    complete_years = [int(r["y"]) for r in complete_year_rows]
    upsert_count = 0

    for year in complete_years:
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT MONTH(periode) AS m, resume
                FROM sage_bfc_monthly
                WHERE YEAR(periode) = %s
                ORDER BY MONTH(periode) ASC
                """,
                (year,),
            )
            rows = cursor.fetchall()

        for row in rows:
            month = int(row["m"])
            resume_raw = row["resume"]
            resume = resume_raw if isinstance(resume_raw, dict) else json.loads(resume_raw)

            for key in BASE_AGGREGATES.keys():
                value = _nature_normalize(key, _extract_resume_value(resume, key))
                _upsert_history_value(
                    year=year,
                    month=month,
                    key=key,
                    value=value,
                    source_file="sage_bfc_monthly_cloture",
                )
                upsert_count += 1

    return {
        "before_year": before_year,
        "complete_years": complete_years,
        "upsert_count": upsert_count,
    }


def import_historical_csv(files: List[str]) -> Tuple[int, List[int]]:
    total = 0
    years = set()

    for file_path in files:
        year, values = _load_csv_budget(file_path)
        years.add(year)

        for key, month_values in values.items():
            for month in range(1, 13):
                value = _to_float(month_values.get(month, 0.0))
                _upsert_history_value(
                    year=year,
                    month=month,
                    key=key,
                    value=value,
                    source_file=Path(file_path).name,
                )
                total += 1

    return total, sorted(years)


def generate_forecast(target_year: int, cycle_code: str = "INITIAL", cycle_month: Optional[int] = None) -> Tuple[int, int]:
    # 1) Avant toute génération, synchroniser automatiquement toutes les années clôturées
    #    (12 mois réels disponibles) vers l'historique d'entraînement.
    sync_closed_years_into_history(before_year=target_year)

    # 2) Charger l'historique complet (CSV importés + années clôturées depuis monthly)
    history = _load_history_from_db()
    actuals_target = _load_actuals_for_year(target_year)

    run_meta = {"target_year": target_year, "cycle_code": cycle_code, "cycle_month": cycle_month}
    run_id = _insert_forecast_run(target_year, cycle_code, cycle_month, run_meta)

    # base forecasts by month
    base_by_month: Dict[int, Dict[str, float]] = {m: {} for m in range(1, 13)}
    intervals_by_key_month: Dict[str, Dict[int, Tuple[Optional[float], Optional[float]]]] = {
        k: {} for k in BASE_AGGREGATES.keys()
    }
    model_by_key: Dict[str, str] = {}

    for key in BASE_AGGREGATES.keys():
        sorted_vals = [v for (_, _, v) in sorted(history.get(key, []), key=lambda x: (x[0], x[1]))]

        actual_prefix = []
        if cycle_month is not None:
            for m in range(1, cycle_month + 1):
                if m in actuals_target and key in actuals_target[m]:
                    actual_prefix.append(actuals_target[m][key])

        train_series = sorted_vals + actual_prefix
        horizon = max(1, 12 - (cycle_month or 0))

        model_result = _forecast_series(train_series, horizon)
        model_by_key[key] = model_result.model_name

        forecast_iter = iter(model_result.forecast)
        lower_iter = iter(model_result.lower)
        upper_iter = iter(model_result.upper)

        for month in range(1, 13):
            if cycle_month is not None and month <= cycle_month and month in actuals_target and key in actuals_target[month]:
                value = float(actuals_target[month][key])
                low = value
                up = value
                mname = "actual"
            else:
                value = float(next(forecast_iter, model_result.forecast[-1] if model_result.forecast else 0.0))
                low = next(lower_iter, None)
                up = next(upper_iter, None)
                mname = model_result.model_name

            base_by_month[month][key] = value
            intervals_by_key_month[key][month] = (
                None if low is None else float(low),
                None if up is None else float(up),
            )
            _upsert_forecast_value(run_id, target_year, cycle_code, key, month, value, low, up, mname)

    # derived aggregates from formulas
    for month in range(1, 13):
        derived = _build_derived_month(base_by_month[month])
        for dkey, dval in derived.items():
            _upsert_forecast_value(run_id, target_year, cycle_code, dkey, month, float(dval), None, None, "formula")

    # update comparisons with available actuals
    for month, month_values in actuals_target.items():
        update_actuals_for_month(target_year, month, month_values)

    rows_count = len(ALL_AGGREGATES) * 12
    return run_id, rows_count


def update_actuals_for_month(target_year: int, month: int, base_actual_values: Dict[str, float]):
    normalized_base = {}
    for key in BASE_AGGREGATES.keys():
        normalized_base[key] = _nature_normalize(key, _to_float(base_actual_values.get(key, 0.0)))

    derived = _build_derived_month(normalized_base)
    full_values = {**normalized_base, **derived}

    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, agregat_key, nature, forecast_value
            FROM bfc_forecast_values
            WHERE forecast_year = %s AND month = %s
            """,
            (target_year, month),
        )
        rows = cursor.fetchall()

        for row in rows:
            key = row["agregat_key"]
            nature = row["nature"]
            forecast_value = _to_float(row["forecast_value"])
            actual_value = full_values.get(key)
            diff, pct, level = _compute_alert(nature, actual_value, forecast_value)
            cursor.execute(
                """
                UPDATE bfc_forecast_values
                SET actual_value = %s,
                    ecart_value = %s,
                    ecart_pct = %s,
                    alert_level = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (actual_value, diff, pct, level, row["id"]),
            )


def sync_actuals_from_resume(periode: date, resume: Dict[str, float]):
    base_values = {key: _extract_resume_value(resume, key) for key in BASE_AGGREGATES.keys()}
    update_actuals_for_month(periode.year, periode.month, base_values)


def clear_actuals_for_month(target_year: int, month: int):
    """Efface les valeurs réelles/écarts d'un mois (après suppression d'upload)."""
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE bfc_forecast_values
            SET actual_value = NULL,
                ecart_value = NULL,
                ecart_pct = NULL,
                alert_level = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE forecast_year = %s AND month = %s
            """,
            (target_year, month),
        )


def clear_all_actuals():
    """Efface toutes les valeurs réelles/écarts (après suppression globale)."""
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE bfc_forecast_values
            SET actual_value = NULL,
                ecart_value = NULL,
                ecart_pct = NULL,
                alert_level = NULL,
                updated_at = CURRENT_TIMESTAMP
            """
        )


def get_comparison(target_year: int, cycle_code: str, month: int):
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT agregat_key, agregat_label, nature, forecast_value, actual_value,
                   ecart_value, ecart_pct, alert_level, model_name
            FROM bfc_forecast_values
            WHERE forecast_year = %s AND cycle_code = %s AND month = %s
            ORDER BY is_derived ASC, agregat_label ASC
            """,
            (target_year, cycle_code, month),
        )
        return cursor.fetchall()


def _resolve_cycle_phase(uploaded_months: List[int]) -> str:
    if not uploaded_months:
        return "INITIAL"
    max_month = max(uploaded_months)
    if max_month >= 8:
        return "M08"
    if max_month >= 6:
        return "M06"
    if max_month >= 3:
        return "M03"
    return "INITIAL"


def _get_cycle_cutoff_month(cycle_code: str) -> Optional[int]:
    code = (cycle_code or "").upper().strip()
    if code == "INITIAL":
        return None
    meta = CYCLE_CONFIG.get(code)
    if not meta:
        return None
    return int(meta["cycle_month"])


def _annual_indicator(
    agregat_key: str,
    nature: str,
    forecast_annual: float,
    actual_total: float,
    ecart_to_date_pct: Optional[float],
) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    if abs(forecast_annual) < 1e-9:
        return None, None, None

    remaining_budget = float(forecast_annual - actual_total)

    if nature == "charge":
        vigilance_ratio = 0.15 if agregat_key == "frais_personnel" else 0.10
        vigilance_floor = abs(forecast_annual) * vigilance_ratio

        if remaining_budget < 0:
            return "Surplus de budget fixé", remaining_budget, "negative"
        if remaining_budget <= vigilance_floor:
            return "Reste à consommer (vigilance)", remaining_budget, "neutral"
        return "Reste à consommer", remaining_budget, "positive"

    # Produits
    if remaining_budget <= 0:
        return "Objectif atteint / dépassé", remaining_budget, "positive"
    if ecart_to_date_pct is not None and ecart_to_date_pct < -5.0:
        return "Retard de réalisation", remaining_budget, "negative"
    return "Reste à réaliser", remaining_budget, "neutral"


def get_annual_comparison(target_year: int, cycle_code: str) -> Dict[str, object]:
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT agregat_key, agregat_label, nature, is_derived, month, forecast_value, actual_value
            FROM bfc_forecast_values
            WHERE forecast_year = %s AND cycle_code = %s
            ORDER BY is_derived ASC, agregat_label ASC, month ASC
            """,
            (target_year, cycle_code),
        )
        rows = cursor.fetchall()

    grouped: Dict[str, Dict[str, object]] = {}
    uploaded_months_set = set()

    for row in rows:
        key = str(row["agregat_key"])
        item = grouped.setdefault(
            key,
            {
                "agregat_key": key,
                "agregat_label": str(row["agregat_label"]),
                "nature": str(row["nature"]),
                "is_derived": bool(row.get("is_derived", False)),
                "monthly": [],
            },
        )
        month = int(row["month"])
        forecast_val = _to_float(row.get("forecast_value"))
        actual_raw = row.get("actual_value")
        actual_val = None if actual_raw is None else _to_float(actual_raw)
        if actual_val is not None:
            uploaded_months_set.add(month)

        item["monthly"].append(
            {
                "month": month,
                "forecast_value": forecast_val,
                "actual_value": actual_val,
            }
        )

    uploaded_months = sorted(uploaded_months_set)
    uploaded_set = set(uploaded_months)

    response_rows: List[Dict[str, object]] = []
    for key, item in grouped.items():
        monthly = sorted(item["monthly"], key=lambda x: int(x["month"]))
        forecast_annual = float(sum(_to_float(m["forecast_value"]) for m in monthly))
        actual_total = float(sum(_to_float(m["actual_value"]) for m in monthly if m["actual_value"] is not None))
        forecast_to_date = float(
            sum(_to_float(m["forecast_value"]) for m in monthly if int(m["month"]) in uploaded_set)
        )

        ecart_to_date_value, ecart_to_date_pct, alert_level = _compute_alert(
            str(item["nature"]),
            actual_total if uploaded_months else None,
            forecast_to_date if uploaded_months else None,
        )

        taux_realisation_annuel_pct = (
            (actual_total / forecast_annual * 100.0) if abs(forecast_annual) > 1e-9 else None
        )
        remaining_budget = float(forecast_annual - actual_total)

        indicator_label, indicator_value, indicator_alert = _annual_indicator(
            agregat_key=key,
            nature=str(item["nature"]),
            forecast_annual=forecast_annual,
            actual_total=actual_total,
            ecart_to_date_pct=ecart_to_date_pct,
        )
        if indicator_alert is not None:
            alert_level = indicator_alert

        response_rows.append(
            {
                "agregat_key": key,
                "agregat_label": str(item["agregat_label"]),
                "nature": str(item["nature"]),
                "forecast_annual": forecast_annual,
                "forecast_to_date": forecast_to_date,
                "actual_total": actual_total,
                "ecart_to_date_value": ecart_to_date_value,
                "ecart_to_date_pct": ecart_to_date_pct,
                "taux_realisation_annuel_pct": taux_realisation_annuel_pct,
                "remaining_budget": remaining_budget,
                "alert_level": alert_level,
                "indicator_label": indicator_label,
                "indicator_value": indicator_value,
                "is_derived": bool(item.get("is_derived", False)),
            }
        )

    response_rows.sort(key=lambda r: (bool(r.get("is_derived", False)), str(r["agregat_label"])))
    clean_rows = [{k: v for k, v in row.items() if k != "is_derived"} for row in response_rows]

    return {
        "target_year": target_year,
        "cycle_code": cycle_code,
        "cycle_phase": _resolve_cycle_phase(uploaded_months),
        "uploaded_months": uploaded_months,
        "cycle_cutoff_month": _get_cycle_cutoff_month(cycle_code),
        "rows": clean_rows,
    }


def get_catalog_items():
    items = []
    for key, meta in ALL_AGGREGATES.items():
        items.append(
            {
                "agregat_key": key,
                "agregat_label": str(meta["label"]),
                "nature": str(meta["nature"]),
                "is_derived": bool(meta["is_derived"]),
            }
        )
    return items


def get_year_values(target_year: int, cycle_code: str, agregat_key: str):
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT month, forecast_value
            FROM bfc_forecast_values
            WHERE forecast_year = %s AND cycle_code = %s AND agregat_key = %s
            ORDER BY month ASC
            """,
            (target_year, cycle_code, agregat_key),
        )
        rows = cursor.fetchall()

    values = {int(r["month"]): float(r["forecast_value"]) for r in rows}
    meta = ALL_AGGREGATES.get(agregat_key)
    if not meta:
        raise ValueError(f"Agrégat inconnu: {agregat_key}")

    return {
        "target_year": target_year,
        "cycle_code": cycle_code,
        "agregat_key": agregat_key,
        "agregat_label": str(meta["label"]),
        "nature": str(meta["nature"]),
        "values": values,
    }


def _get_uploaded_months(target_year: int) -> List[int]:
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT MONTH(periode) AS m
            FROM sage_bfc_monthly
            WHERE YEAR(periode) = %s
            ORDER BY m ASC
            """,
            (target_year,),
        )
        rows = cursor.fetchall()
    return [int(r["m"]) for r in rows]


def _get_last_cycle_run(target_year: int, cycle_code: str):
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, created_at
            FROM bfc_forecast_runs
            WHERE forecast_year = %s AND cycle_code = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (target_year, cycle_code),
        )
        return cursor.fetchone()


def _is_cycle_period_reached(target_year: int, cycle_month: int, as_of: date, uploaded_months: List[int]) -> bool:
    last_day = calendar.monthrange(target_year, cycle_month)[1]
    cycle_end_date = date(target_year, cycle_month, last_day)
    # Un cycle est considéré atteint si:
    # 1) la date calendrier a dépassé la fin du mois de cycle, OU
    # 2) les données réelles du mois de cycle sont déjà uploadées (clôture opérationnelle anticipée)
    return (as_of >= cycle_end_date) or (cycle_month in set(uploaded_months))


def get_cycle_status(target_year: int, as_of: Optional[date] = None):
    as_of = as_of or date.today()
    uploaded_months = _get_uploaded_months(target_year)
    uploaded_set = set(uploaded_months)

    cycles = []
    for cycle_code, meta in CYCLE_CONFIG.items():
        cycle_month = int(meta["cycle_month"])
        required_months = list(range(1, cycle_month + 1))
        missing_months = [m for m in required_months if m not in uploaded_set]
        is_data_ready = len(missing_months) == 0
        is_period_reached = _is_cycle_period_reached(target_year, cycle_month, as_of, uploaded_months)

        run = _get_last_cycle_run(target_year, cycle_code)
        is_executed = run is not None
        last_run_id = int(run["id"]) if run else None
        last_run_at = str(run["created_at"]) if run and run.get("created_at") else None

        can_trigger = is_period_reached and is_data_ready and (not is_executed)
        reason = None
        if not is_period_reached:
            reason = f"Cycle non atteint (fin mois {cycle_month})"
        elif not is_data_ready:
            reason = f"Mois réels manquants: {missing_months}"
        elif is_executed:
            reason = "Cycle déjà exécuté"

        cycles.append(
            {
                "cycle_code": cycle_code,
                "cycle_label": str(meta["label"]),
                "cycle_month": cycle_month,
                "required_months": required_months,
                "uploaded_months": uploaded_months,
                "missing_months": missing_months,
                "is_period_reached": is_period_reached,
                "is_data_ready": is_data_ready,
                "is_executed": is_executed,
                "can_trigger": can_trigger,
                "last_run_id": last_run_id,
                "last_run_at": last_run_at,
                "reason": reason,
            }
        )

    return {
        "target_year": target_year,
        "as_of": as_of.isoformat(),
        "cycles": cycles,
    }


def run_cycle_adjustment(target_year: int, cycle_code: str, force: bool = False):
    cycle_code = (cycle_code or "").upper().strip()
    if cycle_code not in CYCLE_CONFIG:
        raise ValueError(f"Cycle inconnu: {cycle_code}. Autorisés: {list(CYCLE_CONFIG.keys())}")

    status = get_cycle_status(target_year)
    cycle_info = next((c for c in status["cycles"] if c["cycle_code"] == cycle_code), None)
    if cycle_info is None:
        raise ValueError("Cycle non trouvé")

    if not force and not cycle_info["can_trigger"]:
        raise ValueError(cycle_info.get("reason") or "Cycle non exécutable")

    cycle_month = int(CYCLE_CONFIG[cycle_code]["cycle_month"])
    run_id, rows_written = generate_forecast(
        target_year=target_year,
        cycle_code=cycle_code,
        cycle_month=cycle_month,
    )

    return {
        "target_year": target_year,
        "cycle_code": cycle_code,
        "cycle_month": cycle_month,
        "run_id": run_id,
        "rows_written": rows_written,
        "status": "done",
    }
