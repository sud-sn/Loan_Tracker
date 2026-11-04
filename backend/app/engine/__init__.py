"""Pure interest, schedule, allocation, penalty and status engine.

This package has no database or web imports on purpose (PRD section 14) so it can be
unit-tested on its own against the fixtures in PRD section 4. All money is ``Decimal``;
nothing in here ever touches a float.
"""

from app.engine.errors import EngineError
from app.engine.money import from_paise, q2, to_paise
from app.engine.schedule import ScheduleResult, ScheduleRow, build_schedule
from app.engine.types import FixedStyle, Frequency, LoanTerms, Method, RateBasis, TermUnit

__all__ = [
    "EngineError",
    "FixedStyle",
    "Frequency",
    "LoanTerms",
    "Method",
    "RateBasis",
    "ScheduleResult",
    "ScheduleRow",
    "TermUnit",
    "build_schedule",
    "from_paise",
    "q2",
    "to_paise",
]
