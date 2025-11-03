"""Animal data structures."""

from dataclasses import dataclass


@dataclass
class AnimalAttributes:
    pass


@dataclass
class Animal:
    id: str
    name: str
    attributes: AnimalAttributes
