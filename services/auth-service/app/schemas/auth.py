from pydantic import BaseModel


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenOnly(BaseModel):
    access_token: str
    expires_in: int
    token_type: str = "bearer"
