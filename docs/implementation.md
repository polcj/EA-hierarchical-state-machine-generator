# Implementation — GeneratorStateMachine

---

## Architecture overview

The project is organised as a **two-step pipeline**. The **parser layer** reads the EA file and builds the in-memory model. The **model** (`parser/template.py`) is the contract between both layers — it is the only data structure that crosses the boundary. The **backend layer** receives the model and emits code. Neither layer knows anything about the other.

The key feature of this architecture is that the model is not passed in-memory from one step to the other. Instead, `parse()` **serialises the model to a Python source file** (`*_model.py`). This file embeds the `template.py` class definitions followed by the constructor calls that recreate every state, transition, and trigger. `backend_runner` then imports that file as a normal Python module to retrieve the `StateMachine` instance.

This separation makes it possible to inspect and version-control the extracted model independently of any backend, and to develop or run backends without access to the EA tool.

---

## Full execution flow

```
generator.py
  │
  └─ state_machine_generator.main()
       ├─ detect extension (.qea / .eap)
       ├─ maybe_relaunch_32bit()            — Windows 64-bit + .eap only
       ├─ get_parser(ext)                   — returns E17Parser or E13Parser
       │
       ├─ parser.check(model_path, diagram_name)
       │     ├─ parser.connect(filename) → BaseRepository  (opens DB)
       │     ├─ repository.diagram_exists()
       │     └─ _has_initial_state()
       │
       ├─ parser.parse(model_path, diagram_name)
       │     ├─ extract_model(diagram_name)
       │     │     ├─ _extract_config()      → DiagramConfig
       │     │     ├─ _recursive_extract()   → populates sm.states
       │     │     └─ _extract_triggers()    → populates sm.triggers
       │     └─ _write_model(sm, filename)   → writes *_model.py
       │
       └─ parser.repository.close()


backend.py
  │
  └─ backend_runner.main()
       ├─ load_model(model_path)
       │     ├─ importlib loads *_model.py as a module
       │     └─ inspect finds the StateMachine instance
       │
       ├─ load_backend_class(backend_name)
       │     ├─ importlib loads the backend module
       │     └─ inspect finds the class whose name contains "Generator"
       │
       └─ BackendClass(sm).generate()
```

---

## Model file serialisation (`template.py`, `StateMachine.to_code()`)

This is the central feature that distinguishes this project. Instead of passing the in-memory model directly to a backend in the same process, the model is **serialised to Python source code**.

`_write_model()` writes the output file in three sections:

1. An auto-generated header comment.
2. The complete source of `template.py` (the class definitions for `StateMachine`, `State`, `Transition`, `Trigger`, `DiagramConfig`).
3. The output of `sm.to_code()` — a sequence of Python constructor calls that, when executed, rebuild the exact same model in memory.

The result is a file that is both importable by `backend_runner.load_model()` and readable by a human developer. Example fragment of a generated model file:

```python
# State: HomingMoving
state_homingmoving = State(element_id='1234', name='HomingMoving', parent_id='Homing', ...)
state_homingmoving.entry = 'startMotor'
state_homingmoving.add_transition(Transition(connector_id=99, source_id='HomingMoving',
    target_id='HomingHomed', events=['EVT_SENSOR'], guard='isAtHome', action='stopMotor'))
```

### `StateMachine.to_code()`

Iterates over all states twice:
1. First pass: counts name collisions. States whose name (after sanitising non-alphanumeric characters) appears more than once in the list get a `_<ParentName>` suffix to produce a unique name (`_unique_name`). The variable name in the generated code is `state_<unique_name_lowercase>` (`_var_name`).
2. Second pass: calls `state.to_code(id_to_state)` for each state, then emits the `StateMachine` constructor, `sm.config` assignments, `sm.add_state()` calls, and `sm.add_trigger()` calls.

---

## In-memory model (`parser/template.py`)

The model is a **flat list of `State` objects**, not a tree. Hierarchy is represented by `parent_id` references between states. This differs from tree-based approaches: the parser does not build parent–child containment objects; it stores every element in `sm.states` and links them by ID.

### Class hierarchy

```
StateMachine
  .name:     str
  .states:   list[State]     ← flat list, all types mixed
  .triggers: list[Trigger]
  .config:   DiagramConfig

State
  .element_id:  str
  .name:        str
  .parent_id:   Optional[str]   ← ID of parent State, or None for root states
  .state_type:  str             ← "State", "StateMachine", "StateNode", "ExitPoint"
  .ntype:       int             ← 0=StateMachine, 3=Initial, 4=Final, 8=State, 13=EntryPoint
  .transitions: list[Transition]
  .entry:       Optional[str]
  .exit:        Optional[str]
  .do:          Optional[str]

  Properties:
    .is_final        → state_type == "StateNode" and ntype == 4
    .is_initial      → state_type == "StateNode" and ntype == 3
    .is_entry_point  → state_type == "StateNode" and ntype == 13

Transition
  .connector_id:  str
  .source_id:     str
  .target_id:     str           ← already resolved to a real state (no pseudo-states)
  .events:        list[str]
  .guard:         str
  .action:        str

Trigger
  .name:         str
  .trigger_type: str   ← "HSM_TIMING", "HSM_CALLBACK", "HSM_SIGNAL", "NULL"
  .value:        int   ← milliseconds for HSM_TIMING, 0 otherwise

DiagramConfig
  .path:          str   ← output directory for generated files
  .loop_time:     str
  .event_prefix:  str
  .state_prefix:  str
  .action_prefix: str
  .guard_prefix:  str
  .author:        str
  .modified_date: str
```

### NType reference

| NType | `state_type` | Meaning |
|-------|-------------|---------|
| 0 | `StateMachine` | Composite state with its own sub-diagram |
| 3 | `StateNode` | Initial pseudo-state |
| 4 | `StateNode` | Final pseudo-state |
| 8 | `State` | Regular state (leaf or composite via `State` children) |
| 13 | `StateNode` | Entry point (border of composite state) |

Exit points are `state_type = "ExitPoint"` rather than a distinct NType.

---

## Parser layer

### `IStateMachineParser` (`parser/iparser.py`)

Abstract interface with three methods:

- `check(filename, diagram_name) -> bool`: validates that the diagram exists and is structurally correct (has a root `Initial`). Does not build the model.
- `parse(filename, diagram_name) -> StateMachine`: builds and returns the model, and writes the `*_model.py` file as a side effect.
- `close()`: closes the database connection.

`check()` and `parse()` are separate so the connection is not opened twice. `EParser.check()` opens the connection and stores it in `self.repository`. `EParser.parse()` reuses it via a `if self.repository is None` guard. The `finally` block in `state_machine_generator.main()` closes it via `parser.repository.close()`.

### `EParser` (`parser/eparser.py`)

Abstract base class implementing all common EA parsing logic. The only method left abstract for subclasses is `connect(filename) -> BaseRepository`.

#### `check()` and `parse()` connection management

`check()` calls `self.connect(filename)` and stores the result in `self.repository`. On exception it closes and clears `self.repository` before re-raising. `parse()` checks `if self.repository is None` before calling `connect()` again — this is the reuse guard.

#### `_write_model(sm, filename)`

Constructs the output path from `sm.config.path` and the base name of the EA file. Reads `template.py` from disk (same directory as `eparser.py`) and writes the three-section output file described above.

#### `_extract_config(diagram_name)`

Reads the `Notes`, `Author`, and `ModifiedDate` fields of the diagram row via `repository.get_diagram_by_name()`. Parses `Notes` with a case-insensitive regex for `KEY = value` pairs. If `PATH` is missing or is a relative placeholder (`./`, `.\`), it defaults to the directory that contains the EA file.

#### `extract_model(diagram_name)`

Entry point for the recursive extraction. Builds the `StateMachine` in two phases:

**Phase 1 — State tree:**
```
extract_model()
  └─ _recursive_extract(diagram_name, sql_root_states, parent_id=None, sm)
       for each ea_el:
         creates State(element_id, name, parent_id, state_type, ntype)
         _fill_operations(element_id, state_obj)
         _fill_transitions(element_id, state_obj, diagram_name)
         sm.add_state(state_obj)
         if ea_el.Type == "StateMachine":
           recurse with children-of-sub-diagram SQL
         elif ea_el.Type == "State":
           add ExitPoint border states
           recurse with children-of-state SQL
```

**Phase 2 — Triggers:**
```
_extract_triggers(diagram_name) → sm.triggers
```

#### `_recursive_extract(hsm_name, query, parent_id, sm_obj)`

Two distinct recursive cases for children:

- **Children of a `StateMachine`**: the sub-states live in a separate EA diagram. The query uses `d.parentId = ea_el.ElementID` to find the diagram whose parent is that element, then fetches its members. The filter `AND act.Object_id <> d.parentId` excludes the diagram root element itself.

- **Children of a `State`**: the sub-states live in the same diagram, linked by `act.parentId = ea_el.ElementID`. Additionally, `ExitPoint` elements are queried separately from `t_object` (not through `t_diagramobjects`) because exit points are children of the state but not shown in `t_diagramobjects`.

Both cases filter by `NType IN (0,3,4,8,13)` and `object_type IN ('StateMachine','State','StateNode')` to include only state machine elements.

#### `STATE_ORDER_BY`

```python
STATE_ORDER_BY = (
    "IIF(act.object_type IN ('State', 'StateMachine'), 0, 1) ASC, "
    "d.parentID ASC, "
    "(rectTop*rectTop + rectLeft*rectLeft) ASC, "
    "rectLeft ASC"
)
```

Container states (`State` or `StateMachine`, priority 0) come before pseudo-states (priority 1). Within each group, states are ordered by geometric distance from the top-left corner of the diagram (`rectTop² + rectLeft²`), then by horizontal position. This determines the order of states in the generated model file.

#### `_fill_operations(element_id, state_obj)`

Reads UML operations from `t_operation`. EA stores `entry`, `do`, and `exit` as operations whose `ReturnType` field is literally `"entry"`, `"exit"`, or `"do"`. The operation `Name` is the action function name.

#### `_extract_triggers(diagram_name)`

Queries all elements of `object_type = 'Trigger'` from `t_object`. For each trigger, reads `ea_el.CustomProperties` (which performs an additional query against `t_xref` — see `MockEAObject` below). The type is determined by the `Value` field of the custom property:

- `"Time"` → `"HSM_TIMING"`, calls `_get_timing_value()` for the millisecond value.
- `"Call"` → `"HSM_CALLBACK"`.
- `"Signal"` → `"HSM_SIGNAL"`.
- `"Change"` → warning printed, trigger type stays `"NULL"`.
- No property → warning printed, trigger type stays `"NULL"`.

Triggers with `"NULL"` type are still added to the model to preserve the complete list.

#### `_get_timing_value(trigger_name)`

Calls `repository.get_timing_raw(trigger_name)` which queries `t_xref` for `Name='MOFProps'` associated with the trigger. Parses the `RefName=<value>;` pattern. Returns `0` if the raw string is absent, malformed, or contains `"-1"` (EA's unset sentinel). Logs an error if the value is `"0"` (zero timing period is not valid at runtime).

#### `_fill_transitions(element_id, state_obj, diagram_name)`

Reads all connectors leaving the source state. The SQL filters destinations to types that can be real targets: `State`, `StateMachine`, `ExitPoint`, Final `StateNode` (NType=4), or Entry point `StateNode` (NType=13). This excludes `Initial` pseudo-states from appearing as raw targets.

Destination resolution is done here, not in a separate flattening step:

1. If the destination is a `StateMachine` (has its own sub-diagram), `replace_destination()` is called to follow its `Initial` or `Entry` connector and get the first real state.
2. If the destination is a `State` (composite, with sub-states), `get_initial_id()` is called in a loop until a non-composite leaf state is reached. The loop handles multiple levels of nesting.

The result is that all `Transition.target_id` values in the model point to real leaf states — no pseudo-states appear as targets.

Events, guards, and actions are read from the connector:

- **Events** (`conn.TransitionEvent`, `pdata1`): split on commas, whitespace stripped.
- **Guard** (`conn.TransitionGuard`, `pdata2`): stored as a single string.
- **Action** (`conn.TransitionAction`, `pdata3`): stored as a single string (may contain comma-separated names for the backend to interpret).

#### `replace_destination(elementID)`

When a transition points to a `StateMachine` element, finds the first connector leaving its `Initial` (NType=3) or `Entry` (NType=13) pseudo-state. Returns the `SupplierID` of that connector — the first real state activated on entry into the sub-machine.

#### `get_initial_id(elementId, diagram_name)`

Given a composite state, finds its inner `Initial` (NType=3) and returns the `SupplierID` of the connector leaving that `Initial`. The connector query explicitly excludes `StateNode` elements with NType other than 4 and prefers connectors with a non-null `StereoType`, ordered by most-recent `Connector_ID` as tiebreaker.

Returns `0` if no `Initial` is found (the state is a leaf).

#### `search_init_state_id(hsmName)` and `_has_initial_state()`

`_has_initial_state()` delegates to `search_init_state_id()` and checks the result is non-zero.

`search_init_state_id()` queries all `Initial` nodes (NType=3) in the diagram, then identifies the root one. The key discriminator:

```python
if init.ParentID not in diagram_element_ids:
    initial_id = init.ElementID
    break
```

A root `Initial`'s `ParentID` is the diagram itself (not any state in `diagram_element_ids`). Sub-state `Initial` nodes have a state element as their parent. If no root `Initial` is found this way, the first one from the query is used as fallback. The function returns the `SupplierID` of the connector leaving that `Initial` — the first real state of the diagram.

---

### `MockEAObject` and `DictRow` (`parser/ea_db_repository.py`)

#### Why they exist

`pyodbc` returns plain tuples and `JPype` returns Java objects — neither supports column-name access. `DictRow` wraps both into a unified interface: access by column name (`row["Name"]`) or by index (`row[0]`), just like `sqlite3.Row`. `AccessRepository._execute()` and `UCanAccessRepository._execute()` both return `DictRow` instances. `SQLiteRepository._execute()` returns `sqlite3.Row` directly and does not use `DictRow`.

`MockEAObject` wraps a row (either `DictRow` or `sqlite3.Row`) and exposes it with the same attribute names as EA COM objects. The constructor takes an `obj_type` string (`"Element"`, `"Connector"`, `"Operation"`, or `"Diagram"`) and maps the relevant columns to COM-compatible names for that type:

- `"Element"`: `object_id` → `ElementID`, `name` → `Name`, `object_type` → `Type`, `parentid` → `ParentID`, `ntype` → `NType`
- `"Connector"`: `connector_id` → `ConnectorID`, `start_object_id` → `ClientID`, `end_object_id` → `SupplierID`, `pdata1/2/3` → `TransitionEvent/Guard/Action`
- `"Operation"`: `name` → `Name`, `type` → `ReturnType`
- `"Diagram"`: `name` → `Name`, `notes` → `Notes`, `author` → `Author`, `modifieddate` → `ModifiedDate`

The constructor also calls `setattr(self, key, row[key])` for every column, so raw column names are accessible as attributes too. This allows `EParser` to write `ea_el.Name`, `conn.SupplierID`, `conn.TransitionEvent` exactly as if using the EA COM API, with no knowledge of the underlying database engine.

#### `CustomProperties`

This property of `MockEAObject` is the only one that performs a database query rather than reading a stored field. It emulates `trigger.CustomProperties` from EA COM. In EA the trigger type is stored in `t_xref` with `Name='CustomProperties'` and `Description` field in the format:

```
@VALU=Call@ENDVALU
@VALU=Time@ENDVALU
```

The property queries `t_xref` by the trigger's `ea_guid` to retrieve this data. If no `CustomProperties` entry is found, it falls back to checking `MOFProps` in `t_xref` and treats its presence as a `Signal` type.

The property returns a list of objects each having a `.Value` attribute, matching the EA COM iteration interface.

---

### Concrete parsers

#### `E17Parser` (`parser/eparser17.py`)

For `.qea` files (EA v17). Uses `SQLiteRepository`, which wraps `sqlite3` — built-in, no dependencies, cross-platform. `sqlite3.Row` supports column-name access natively, so `DictRow` wrapping is not needed: `SQLiteRepository._execute()` returns `sqlite3.Row` objects directly.

#### `E13Parser` (`parser/eparser13.py`)

For `.eap` files (EA v13, Microsoft Access/Jet 3). Two platform-specific backends:

- **Windows** (`AccessRepository`): uses `pyodbc` with the `Microsoft Access Driver (*.mdb, *.accdb)`. This driver is 32-bit only. If 64-bit Python is detected when the file extension is `.eap`, `state_machine_generator.maybe_relaunch_32bit()` relaunches the process with Python 32-bit before the parser is even instantiated.

- **Linux** (`UCanAccessRepository`): uses `JPype` to start a JVM and connect via JDBC with the UCanAccess driver. The required JARs are in `parser/jars/`. The JVM is started once per process (guarded with `jpype.isJVMStarted()`). JDBC row data is explicitly converted from Java types to Python (`str`, `int`, `float`) before being stored in `DictRow`.

Both imports are wrapped in `try/except ImportError` at module level so the file can be imported without crashing when the dependency is absent; the error is raised only when a connection is actually attempted.

#### `find_python32()` (`parser/ea_db_repository.py`)

Windows-only. Searches for a Python 32-bit executable in two steps:

1. Runs `py -3-32 -c "import sys; print(sys.executable)"` via the Python Launcher.
2. If that fails, enumerates the Windows registry under `HKLM` and `HKCU` at `SOFTWARE\Python\PythonCore` and `SOFTWARE\WOW6432Node\Python\PythonCore`, looking for version entries with the `-32` suffix.

Returns the executable path, or `None` if not found (in which case `state_machine_generator` prints an installation URL and exits).

---

## Backend layer

### `IGenerator` (`backends/igenerator.py`)

Minimal abstract interface:

```python
class IGenerator(ABC):
    def __init__(self, sm: object) -> None:
        self._sm = sm

    @abstractmethod
    def generate(self) -> None:
        pass
```

The constructor receives and stores the `StateMachine` model. `generate()` takes no arguments — all output paths are derived from `self._sm.config.path` and `self._sm.name` inside the backend.

### Backend discovery (`backend_runner.load_backend_class()`)

No registration or `ICreation` pattern. `backend_runner` loads the backend module dynamically with `importlib` and scans all classes with `inspect.getmembers`. The first class whose name contains `"Generator"` but does not start with `"I"` is used. This means naming the class `XxxGenerator` is the only convention required for a new backend to be discovered.

### C Verification Backend (`backends/backend_c_verify_generator.py`)

Generates `<hsm>_verify.h` and `<hsm>_verify.c`. The `.c` file, when compiled with `-DVERIFY_MAIN` and executed, prints the complete model to stdout.

The constructor pre-computes:
- `_hsm_name`: diagram name as-is.
- `_hsm_name_up`: uppercase version (for `#define` guards).
- `_hsm_decorated`: `<name>_hsm` (lowercase).
- `_verify_name`: `<name>_hsm_verify` (used as the file base name).
- `_id_to_state`: dict mapping `element_id → State` for all states, including pseudo-states.

#### Output structure

**`.h` file**:
```c
#ifndef <HSM_NAME_UP>_HSM_VERIFY_H_
#define <HSM_NAME_UP>_HSM_VERIFY_H_

void <hsm>_hsm_verify_print(void);

#endif
```

**`.c` file**:
```c
#include "<hsm>_hsm_verify.h"
#include <stdio.h>

void <hsm>_hsm_verify_print(void) {
    // DiagramConfig block  (name, loop_time, prefixes, author, date, path)
    // One block per Trigger  (name, type, value)
    // One block per State    (name, type, parent, entry/exit/do)
    //   One line per Transition  (events, guard, action, target)
    // Summary block  (total counts)
}

#ifdef VERIFY_MAIN
int main(void) { <hsm>_hsm_verify_print(); return 0; }
#endif
```

#### `_c_safe(value)`

Escapes a Python value for safe embedding inside a C `printf` format string: backslash → `\\`, double-quote → `\"`, percent → `%%`.

---

## Adding a new backend

1. Create `backends/my_backend_generator.py`.
2. Define a class whose name contains `Generator` (e.g. `MyBackendGenerator`), inheriting from `IGenerator`.
3. Implement `generate(self)`. Use `self._sm.config` for output path and prefixes. Iterate `self._sm.states` and `self._sm.triggers` for the model data.

```python
from igenerator import IGenerator

class MyBackendGenerator(IGenerator):
    def __init__(self, sm) -> None:
        super().__init__(sm)
        # pre-compute anything needed from self._sm

    def generate(self) -> None:
        output_path = self._sm.config.path
        # write files to output_path
```

Run:

```bash
python backend.py my_model.py backends/my_backend_generator.py
```

`backend_runner` discovers `MyBackendGenerator` automatically because it contains `"Generator"` in its name. No registration step is needed.

---

## Adding a new parser

1. Create `parser/my_parser.py`.
2. Subclass `EParser` from `eparser.py` and implement `connect(filename) -> BaseRepository`.
3. Extend `state_machine_generator.get_parser()` to return your parser for the relevant extension.

If the new format uses the same EA database schema (only the connection mechanism differs), all of `EParser`'s logic is inherited for free.

```python
from eparser import EParser
from ea_db_repository import BaseRepository

class MyParser(EParser):
    def connect(self, filename: str) -> BaseRepository:
        return MyRepository(filename)
```

---

## EA database schema reference

Key tables used by the parser:

| Table | Used for |
|-------|----------|
| `t_diagram` | Finding diagrams by name, reading Notes/Author/ModifiedDate |
| `t_diagramobjects` | Mapping elements to diagrams |
| `t_object` | All model elements (states, triggers, pseudo-states) |
| `t_connector` | All transitions and their event/guard/action data |
| `t_operation` | entry/do/exit actions stored as UML operations |
| `t_xref` | Trigger CustomProperties (Call/Time/Signal) and timing values |

Key column mappings in `t_connector` (exposed as `MockEAObject` Connector):

| DB column | MockEAObject attribute | Content |
|-----------|----------------------|---------|
| `Connector_ID` | `ConnectorID` | Connector primary key |
| `Start_Object_ID` | `ClientID` | Source state element ID |
| `End_Object_ID` | `SupplierID` | Target state element ID |
| `pdata1` | `TransitionEvent` | Comma-separated trigger names |
| `pdata2` | `TransitionGuard` | Guard expression |
| `pdata3` | `TransitionAction` | Action function name(s) |

Key column mappings in `t_object` (exposed as `MockEAObject` Element):

| DB column | MockEAObject attribute | Content |
|-----------|----------------------|---------|
| `Object_ID` | `ElementID` | Element primary key |
| `Name` | `Name` | Element name |
| `Object_Type` | `Type` | "State", "StateMachine", "StateNode", "ExitPoint", "Trigger" |
| `NType` | `NType` | Pseudo-state subtype (see NType table above) |
| `ParentID` | `ParentID` | Parent element ID |
| `ea_guid` | `ea_guid` | GUID used for `t_xref` lookups |