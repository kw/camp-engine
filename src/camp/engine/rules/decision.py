from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel


class Decision(BaseModel):
    """
    Attributes:
        success: True if the mutation succeeds or query succeeds.
        needs_option: When returned from a query, will be True
            if the only thing missing from the feature is an option.
        reason: If success=False, explains why.
        amount: If the action is hypothetical, how much can it be done?

    Note that this object's truthiness is tied to its success attribute.
    """

    success: bool = False
    needs_option: bool = False
    reason: str | None = None
    amount: int | None = None
    need_currency: dict[str, int] | None = None

    UNSUPPORTED: ClassVar[Decision]
    SUCCESS: ClassVar[Decision]
    UNKNOWN_FAILURE: ClassVar[Decision]

    def __bool__(self) -> bool:
        return self.success

    class Config:
        allow_mutation = False


Decision.UNSUPPORTED = Decision(success=False, reason="Unsupported")
Decision.SUCCESS = Decision(success=True)
Decision.UNKNOWN_FAILURE = Decision(success=False, reason="Unknown failure.")
