"""
state_machine_generator.py  —  CLI entry point

Usage:
    python state_machine_generator.py <model.qea/.eap> <DiagramName>

The CLI detects the file extension, picks the right parser, and delegates
all work to it. It also handles the Windows 32-bit relaunch for .eap files.
"""

from __future__ import annotations

import os
import sys

from ea_db_repository import IS_WINDOWS, find_python32
from exceptions import DiagramNotFoundError, InvalidDiagramError, RepositoryConnectionError
from iparser import IStateMachineParser

def get_parser(ext: str) -> IStateMachineParser:
    """Returns the appropriate parser class for the given file extension."""
    if ext in ('.qea', '.qeax'):
        from eparser17 import E17Parser
        return E17Parser()
    elif ext in ('.eap', '.eapx'):
        from eparser13 import E13Parser
        return E13Parser()
    else:
        print(f"Error: Extension '{ext}' not supported. Use .qea or .eap")
        sys.exit(1)


def maybe_relaunch_32bit(model_path: str, ext: str) -> None:
    """
    On 64-bit Windows, .eap files require pyodbc with the 32-bit Jet driver.
    If we are running as 64-bit, relaunch the whole process with Python 32-bit.
    """
    if not IS_WINDOWS:
        return
    if ext not in ('.eap', '.eapx'):
        return

    import struct
    if struct.calcsize("P") * 8 != 64:
        return  # already 32-bit, nothing to do

    python32 = find_python32()
    if python32:
        import subprocess
        print(f"[INFO] .EAP file detected. Relaunching with Python 32-bit: {python32}")
        result = subprocess.run([python32] + sys.argv)
        sys.exit(result.returncode)
    else:
        print("[ERROR] Python 32-bit not found.")
        print("[ERROR] Install it from https://www.python.org/downloads/windows/")
        sys.exit(1)


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python state_machine_generator.py <model.qea/.eap> <DiagramName>")
        sys.exit(1)

    model_path:   str = os.path.abspath(sys.argv[1])
    diagram_name: str = sys.argv[2]
    ext:          str = os.path.splitext(model_path)[1].lower()

    maybe_relaunch_32bit(model_path, ext)

    parser = get_parser(ext)

    try:
        if not parser.check(model_path, diagram_name):
            print("Some errors found. Could NOT generate the code.")
            sys.exit(1)

        sm = parser.parse(model_path, diagram_name)
        print("-" * 50)
        print(f"StateMachine '{sm.name}' parsed successfully.")
        print(f"  States:   {len(sm.states)}")
        print(f"  Triggers: {len(sm.triggers)}")

    except DiagramNotFoundError as e:
        print(f"State Machine NOT found!! {e}")
        sys.exit(1)
    except InvalidDiagramError as e:
        print(f"Invalid diagram: {e}")
        sys.exit(1)
    except RepositoryConnectionError as e:
        print(f"Database connection error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        if parser.repository is not None:
            parser.repository.close()


if __name__ == "__main__":
    main()