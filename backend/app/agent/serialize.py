"""Turn service results into JSON the model can read.

Money stays exact ("42500.00") and every money field also gets a sibling `<name>_inr` with Indian digit
grouping ("₹42,500"), so the model quotes numbers verbatim instead of re-formatting or recomputing them.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.services.savings import inr

_SKIP_INR = {"confidence", "percent", "percent_used", "percent_of_previous", "change_percent"}


def jsonable(value: Any) -> Any:
    tz = ZoneInfo(get_settings().app_timezone)

    def conv(v: Any) -> Any:
        if isinstance(v, Decimal):
            return f"{v:.2f}"
        if isinstance(v, datetime):
            return v.astimezone(tz).isoformat(timespec="seconds")
        if isinstance(v, date):
            return v.isoformat()
        if isinstance(v, dict):
            out: dict[str, Any] = {}
            for k, x in v.items():
                out[str(k)] = conv(x)
                if isinstance(x, Decimal) and not any(s in str(k) for s in _SKIP_INR):
                    out[f"{k}_inr"] = inr(x)
            return out
        if isinstance(v, (list, tuple)):
            return [conv(x) for x in v]
        if hasattr(v, "hex") and v.__class__.__name__ == "UUID":
            return str(v)
        return v

    return conv(value)
