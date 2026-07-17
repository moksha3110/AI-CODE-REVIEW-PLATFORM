import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    default_branch: str
    is_private: bool
    updated_at: datetime


class InstallUrlOut(BaseModel):
    install_url: str
