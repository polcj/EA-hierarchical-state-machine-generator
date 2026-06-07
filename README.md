# GeneratorStateMachine

GeneratorStateMachine is a Python tool that reads Hierarchical State Machine (HSM) diagrams from Enterprise Architect (`.qea` / `.eap` files) and generates a portable Python model file that can then be fed to any backend to produce code for embedded systems.

## What it does

The tool works in two independent steps:

1. **Parse**: reads an Enterprise Architect state machine diagram and serialises the entire model into a self-contained `*_model.py` file (human-readable Python).
2. **Generate**: loads any `*_model.py` file and runs the requested backend to produce output code (e.g. a C verification harness).

Splitting the pipeline at the model file means you can inspect, version-control, and diff the extracted model before generating any code, and you can re-run the backend step independently of the EA tool.

---

## Project Structure

- `generator.py` — Entry point for Step 1: parse EA file → `*_model.py`
- `backend.py` — Entry point for Step 2: `*_model.py` → generated code
- `parser/` — Parsing layer
  - `state_machine_generator.py` — Step 1 CLI logic and entry point
  - `iparser.py` — Abstract parser interface (`IStateMachineParser`)
  - `eparser.py` — Base parser class with all common parsing logic (`EParser`)
  - `eparser13.py` — Concrete parser for `.eap` files (EA v13, Access databases)
  - `eparser17.py` — Concrete parser for `.qea` files (EA v17, SQLite databases)
  - `ea_db_repository.py` — Database abstraction layer (`BaseRepository`, `MockEAObject`, `DictRow`)
  - `template.py` — In-memory model (`StateMachine`, `State`, `Transition`, `Trigger`, `DiagramConfig`)
  - `exceptions.py` — Custom domain exceptions
  - `jars/` — UCanAccess JAR files required for `.eap` support on Linux
- `backends/` — Code generation layer
  - `igenerator.py` — Abstract generator interface (`IGenerator`)
  - `backend_runner.py` — Step 2 CLI logic: loads model and backend dynamically
  - `backend_c_verify_generator.py` — C verification backend (`.h` + `.c`)

---

## Requirements

- Python 3.8+
- For `.qea` files: no additional dependencies (`sqlite3` is built-in)
- For `.eap` files on Windows: `pyodbc` + Python 32-bit
- For `.eap` files on Linux: `jpype1` + UCanAccess JARs (included in `parser/jars/`)

### Installation

```bash
pip install pyodbc                  # For .eap support on Windows
sudo apt install default-jdk        # For .eap support on Linux
sudo apt install python3-jpype      # For .eap support on Linux
```

> **Windows 64-bit + .eap**: the tool automatically relaunches itself using Python 32-bit when needed. Install Python 32-bit from https://www.python.org/downloads/windows/

> **Linux + .eap**: UCanAccess JARs are already included in `parser/jars/`. No manual download required.

---

## Usage

The pipeline has two separate commands.

### Step 1 — Parse an EA file into a model

```bash
python generator.py <model.qea/.eap> <DiagramName>
```

| Argument | Description |
|----------|-------------|
| `model` | Path to the Enterprise Architect file (`.qea` or `.eap`) |
| `DiagramName` | Exact name of the state machine diagram inside EA |

```bash
# Generate a model file from a .qea file
python generator.py models/my_model.qea "Linear Axis Controller SM"

# Generate a model file from a .eap file, output path set in diagram Notes
python generator.py models/my_model.eap "Motor Controller SM"
```

The parser writes a `<model_name>_model.py` file to the output path configured in the diagram Notes (see **DiagramConfig** below), or to the same directory as the EA file if no path is set.

### Step 2 — Generate code from a model file

```bash
python backend.py <model_file.py> <backend_file.py>
```

| Argument | Description |
|----------|-------------|
| `model_file.py` | Path to a `*_model.py` file produced by Step 1 |
| `backend_file.py` | Path to the backend generator module |

```bash
# Run the C verification backend
python backend.py dg522_model.py backends/backend_c_verify_generator.py
```

---

## DiagramConfig — configuration via diagram Notes

The parser reads the EA diagram's **Notes** field for optional `KEY = value` pairs that configure the output.

| Key | Description |
|-----|-------------|
| `PATH` | Output directory for the model file |
| `LOOP_TIME` | HSM loop period in milliseconds |
| `EVENT_PREFIX` | Prefix prepended to generated event names |
| `STATE_PREFIX` | Prefix prepended to generated state names |
| `ACTION_PREFIX` | Prefix prepended to generated action functions |
| `GUARD_PREFIX` | Prefix prepended to generated guard functions |

Example Notes content in EA:

```
PATH=./generated
LOOP_TIME=10
EVENT_PREFIX=EVT_DG522_
STATE_PREFIX=STA_DG522_
```

---

## How it works

1. `generator.py` delegates to `state_machine_generator.main()`, which detects the file extension and selects the appropriate concrete parser (`E17Parser` for `.qea`, `E13Parser` for `.eap`). On 64-bit Windows with a `.eap` file, the process relaunches automatically with Python 32-bit.
2. The parser validates the diagram (`check()`) and then builds an in-memory model of the state machine — states, hierarchy, transitions, guards, actions, and triggers (`parse()`).
3. `parse()` serialises the model by writing a `*_model.py` file that embeds the class definitions from `template.py` followed by the constructor calls that recreate every state, transition, and trigger.
4. `backend.py` delegates to `backend_runner.main()`, which dynamically imports the `*_model.py` file, finds the `StateMachine` instance inside it, then loads the requested backend class and calls `generate()`.

---

## Backends

All backends inherit from `IGenerator` (`backends/igenerator.py`), which defines the common interface: a constructor that receives the `StateMachine` model and a `generate()` method that writes all output files.

New backends are discovered automatically by `backend_runner` — any class whose name contains `Generator` (excluding `IGenerator`) qualifies. No registration step is needed.

### C Verification Backend (`backend_c_verify_generator.py`)

Generates two files:
- `.h` — `verify_<hsm>()` function prototype
- `.c` — Implementation that prints the complete model (config, states, transitions, triggers) to stdout for manual inspection

---

## Parsers

All parsers inherit from `IStateMachineParser` (`parser/iparser.py`). The only built-in parser is the `EParser` family, which supports both `.qea` (via `E17Parser` + SQLite) and `.eap` (via `E13Parser` + pyodbc/UCanAccess) by selecting the correct concrete parser based on the file extension.

---

## Limitations

- `.eap` files on 64-bit Windows require Python 32-bit. The relaunch is automatic but Python 32-bit must be installed.
- `.eap` files on Linux require `jpype1` and the UCanAccess JARs in `parser/jars/`.
- Diagrams must have an `Initial` pseudo-state at root level. The parser rejects diagrams without one.
- Triggers must be marked as `Time`, `Call`, or `Signal` in EA CustomProperties. Triggers without a recognised type emit a warning and are stored with type `NULL`.
- Choice nodes (decision diamonds) are not supported. Model conditional transitions as parallel transitions with guards directly on the source state.
- The `*_model.py` file embeds a copy of `template.py`. If `template.py` changes, existing model files need to be regenerated.