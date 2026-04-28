from pydantic import BaseModel


class CompteConfigurationBase(BaseModel):
    code_compte: str
    libelle_compte: str


class CompteConfigurationCreate(CompteConfigurationBase):
    pass


class CompteConfiguration(CompteConfigurationBase):
    class Config:
        from_attributes = True
