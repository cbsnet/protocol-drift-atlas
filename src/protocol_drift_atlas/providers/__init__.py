"""Provider adapters for judge execution.

Each provider implements the ``JudgeProvider`` protocol defined in
``base.py``. Providers are responsible for issuing a single judge call and
returning a ``JudgmentResult``. They are not responsible for scoring,
manifest construction, or reporting.
"""

from .base import JudgeProvider
from .mock import MockProvider
from .openai_responses import OpenAIProvider

__all__ = [
    "JudgeProvider",
    "MockProvider",
    "OpenAIProvider",
]