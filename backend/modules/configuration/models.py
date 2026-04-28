from pydantic import BaseModel
from typing import List


class CompteConfigurationBase(BaseModel):
    code_compte: str
    libelle_compte: str


class CompteConfigurationCreate(CompteConfigurationBase):
    pass


class CompteConfigurationUpdate(BaseModel):
    code_compte: str
    libelle_compte: str


class CompteConfiguration(CompteConfigurationBase):
    class Config:
        from_attributes = True


class CompteConfigurationPage(BaseModel):
    items: List[CompteConfiguration]
    total: int
    page: int
    page_size: int
    pages: int
