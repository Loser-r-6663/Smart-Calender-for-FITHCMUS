from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=50, pattern=r"\S")
    email: str = Field(
        min_length=3,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    full_name: str | None = None


def validate_user_data(user_data: Mapping[str, Any]) -> dict[str, Any]:
    validated = UserData.model_validate(dict(user_data))
    return validated.model_dump(exclude_unset=True)
