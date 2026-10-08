from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    @abstractmethod
    def generate_json(self, prompt: str, *, response_schema: Any = None) -> Any:
        """Generate and parse a JSON response for the supplied prompt."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return whether this provider has the configuration it needs."""
