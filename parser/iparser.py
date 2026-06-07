"""
iparser.py

Abstract interface for all state machine parsers.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from template import StateMachine
from exceptions import VirtualException

class IStateMachineParser(ABC):
    """
    Base interface that every concrete parser must implement.
    The CLI only depends on this interface, never on a concrete parser.
    """
    @abstractmethod
    def parse(self, filename: str, diagram_name: str) -> StateMachine:
        """
        Opens the model file at *filename*, reads the state machine diagram
        and returns a fully populated StateMachine instance.
        """
        if not filename:
            raise ValueError("filename must be a non-empty string")
        if not diagram_name:
            raise ValueError("diagram_name must be a non-empty string")
        raise VirtualException(type(self).__name__, "parse")

    @abstractmethod
    def check(self, filename: str, diagram_name: str) -> bool:
        """
        Validates that *diagram_name* exists in *filename* and is structurally
        correct (has an initial state, etc.) without generating any output.
        """
        raise VirtualException(type(self).__name__, "check")
    
    @abstractmethod
    def close(self) -> None:
        """Closes the database connection."""
        raise VirtualException(type(self).__name__, "close")