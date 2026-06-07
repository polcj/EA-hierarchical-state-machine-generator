class VirtualException(Exception):
    """Raised when a virtual method is called without being overridden in a subclass."""
    def __init__(self, type_name: str = "", func_name: str = ""):
        msg = f"Virtual method not implemented"
        if type_name:
            msg += f" in '{type_name}'"
        if func_name:
            msg += f": {func_name}()"
        super().__init__(msg)
        self.type_name: str = type_name
        self.func_name: str = func_name

class RepositoryConnectionError(Exception):
    """Raised when a database connection cannot be established."""
    pass

class DiagramNotFoundError(Exception):
    """Raised when the requested state machine diagram does not exist."""
    pass

class InvalidDiagramError(Exception):
    """Raised when the diagram is structurally invalid (e.g. no initial state)."""
    pass