import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Category = Literal["remark", "observation", "followup"]
RiskTag = Literal["fall", "medication", "pain"]

ShortName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]


class SignupIn(BaseModel):
    login_id: str = Field(pattern=r"^[a-z0-9_]{4,20}$")
    password: str = Field(min_length=8, max_length=128)
    display_name: ShortName


class LoginIn(BaseModel):
    login_id: str = Field(max_length=20)
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    login_id: str
    display_name: str
