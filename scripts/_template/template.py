"""Module description: one-line summary of what this module does.

Longer description if needed. Explain purpose and key concepts,
not implementation details.
"""

from __future__ import annotations


def example_function(param: str, count: int = 1) -> list[str]:
    """Do something useful and return a list of strings.

    Args:
        param: A string input describing the thing to process.
        count: Number of times to repeat the operation. Defaults to 1.

    Returns:
        A list of processed strings.

    Raises:
        ValueError: If count is less than 1.
    """
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")
    return [param] * count


class ExampleClass:
    """A template class demonstrating Google-style docstrings.

    Attributes:
        name: The name of the instance.
        value: The numeric value associated with this instance.
    """

    def __init__(self, name: str, value: float) -> None:
        """Initialize ExampleClass.

        Args:
            name: A descriptive name for this instance.
            value: The numeric value to store.
        """
        self.name = name
        self.value = value

    def describe(self) -> str:
        """Return a human-readable description of this instance.

        Returns:
            A formatted string describing the instance.
        """
        return f"{self.name}: {self.value}"
