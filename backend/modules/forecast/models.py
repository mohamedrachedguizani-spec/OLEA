from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class ForecastAggregateValue(BaseModel):
    agregat_key: str
    agregat_label: str
    mois: int
    forecast_value: float
    lower_value: Optional[float] = None
    upper_value: Optional[float] = None
    actual_value: Optional[float] = None
    ecart_value: Optional[float] = None
    ecart_pct: Optional[float] = None
    alert_level: Optional[str] = None
    model_name: Optional[str] = None
    is_derived: bool = False


class ForecastGenerateRequest(BaseModel):
    target_year: int = Field(..., ge=2000, le=2100)
    cycle_code: str = Field(default="INITIAL")
    cycle_month: Optional[int] = Field(default=None, ge=1, le=12)


class ForecastRunResponse(BaseModel):
    run_id: int
    target_year: int
    cycle_code: str
    cycle_month: Optional[int] = None
    rows_written: int


class ForecastComparisonRow(BaseModel):
    agregat_key: str
    agregat_label: str
    nature: str
    forecast_value: Optional[float] = None
    actual_value: Optional[float] = None
    ecart_value: Optional[float] = None
    ecart_pct: Optional[float] = None
    alert_level: Optional[str] = None
    model_name: Optional[str] = None


class ForecastComparisonResponse(BaseModel):
    target_year: int
    cycle_code: str
    mois: int
    rows: List[ForecastComparisonRow]


class HistoricalImportResponse(BaseModel):
    files: List[str]
    rows_written: int
    years: List[int]


class ForecastCatalogItem(BaseModel):
    agregat_key: str
    agregat_label: str
    nature: str
    is_derived: bool = False


class ForecastCatalogResponse(BaseModel):
    items: List[ForecastCatalogItem]


class ForecastYearValues(BaseModel):
    target_year: int
    cycle_code: str
    agregat_key: str
    agregat_label: str
    nature: str
    values: Dict[int, float]


class ForecastCycleStatusItem(BaseModel):
    cycle_code: str
    cycle_label: str
    cycle_month: int
    required_months: List[int]
    uploaded_months: List[int]
    missing_months: List[int]
    is_period_reached: bool
    is_data_ready: bool
    is_executed: bool
    can_trigger: bool
    last_run_id: Optional[int] = None
    last_run_at: Optional[str] = None
    reason: Optional[str] = None


class ForecastCycleStatusResponse(BaseModel):
    target_year: int
    as_of: str
    cycles: List[ForecastCycleStatusItem]


class ForecastCycleRunResponse(BaseModel):
    target_year: int
    cycle_code: str
    cycle_month: int
    run_id: int
    rows_written: int
    status: str


class ForecastAnnualComparisonRow(BaseModel):
    agregat_key: str
    agregat_label: str
    nature: str
    forecast_annual: float
    forecast_to_date: float
    actual_total: float
    ecart_to_date_value: Optional[float] = None
    ecart_to_date_pct: Optional[float] = None
    taux_realisation_annuel_pct: Optional[float] = None
    remaining_budget: Optional[float] = None
    alert_level: Optional[str] = None
    indicator_label: Optional[str] = None
    indicator_value: Optional[float] = None


class ForecastAnnualComparisonResponse(BaseModel):
    target_year: int
    cycle_code: str
    cycle_phase: str
    uploaded_months: List[int]
    cycle_cutoff_month: Optional[int] = None
    rows: List[ForecastAnnualComparisonRow]
