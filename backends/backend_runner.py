import sys
import os
import importlib.util
import inspect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def load_model(filepath: str):
    """Loads the model.py file and returns the StateMachine instance defined within it."""
    module_name = os.path.splitext(os.path.basename(filepath))[0]
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        for _, obj in inspect.getmembers(module):
            if type(obj).__name__ == "StateMachine":
                return obj
    raise ImportError(f"No StateMachine instance found in {filepath}")


def load_backend_class(backend_name: str):
    """Loads the backend generator class from the specified file."""
    backends_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(backends_dir, os.path.basename(backend_name))
    if not os.path.exists(candidate):
        candidate = os.path.abspath(backend_name)
    if not os.path.exists(candidate):
        print(f"[!] Backend not found: {backend_name}")
        sys.exit(1)

    module_name = os.path.splitext(os.path.basename(candidate))[0]
    spec = importlib.util.spec_from_file_location(module_name, candidate)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for name, obj in inspect.getmembers(module, inspect.isclass):
        if "Generator" in name and not name.startswith("I"):
            return obj

    print(f"[!] No Generator class found in {candidate}")
    sys.exit(1)


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python backend.py <example_model.py> <backend_file_generator.py>")
        sys.exit(1)

    model_path   = sys.argv[1]
    backend_name = sys.argv[2]

    print(f"[*] Loading model:   {model_path}")
    sm = load_model(model_path)

    print(f"[*] Loading backend: {backend_name}")
    BackendClass = load_backend_class(backend_name)

    generator = BackendClass(sm)
    generator.generate()