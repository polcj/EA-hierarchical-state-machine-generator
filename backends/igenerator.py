from abc import ABC, abstractmethod

class IGenerator(ABC):
    """
    Interface base for all code generators (Backends).
    Ensures that all backends implement the same methods.
    """

    def __init__(self, sm: object) -> None:
        # The model is passed in the constructor and stored as a protected member variable.
        self._sm = sm

    @abstractmethod
    def generate(self) -> None:
        """
        Generates the source code files.
        Any backend that inherits from IGenerator MUST implement this method.
        """
        pass