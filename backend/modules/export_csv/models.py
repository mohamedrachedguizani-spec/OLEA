# modules/export_csv/models.py
from pydantic import BaseModel
from datetime import date
from typing import Optional


class ExportRequest(BaseModel):
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
