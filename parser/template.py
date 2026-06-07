from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Optional

class StateMachine:
    def __init__(self, name: str) -> None:
        self.name:     str           = name
        self.states:   list[State]   = []
        self.triggers: list[Trigger] = []
        self.config:   DiagramConfig = DiagramConfig()

    def add_state(self, state: State) -> None:
        self.states.append(state)

    def add_trigger(self, trigger: Trigger) -> None:
        self.triggers.append(trigger)

    def to_code(self) -> str:
        id_to_state = {s.element_id: s for s in self.states}

        name_counts = {}
        for state in self.states:
            n = re.sub(r'[^a-zA-Z0-9_]', '_', state.name)
            name_counts[n] = name_counts.get(n, 0) + 1

        # Asign unique names and variable names to each state
        for state in self.states:
            n = re.sub(r'[^a-zA-Z0-9_]', '_', state.name)
            if name_counts[n] > 1 and state.parent_id and state.parent_id in id_to_state:
                parent_name = re.sub(r'[^a-zA-Z0-9_]', '_', id_to_state[state.parent_id].name)
                state._unique_name = f"{n}_{parent_name}"
            else:
                state._unique_name = n
            
            state._var_name = f"state_{state._unique_name.lower()}"

        lines = []
        
        for state in self.states:
            lines.append(state.to_code(id_to_state))
            lines.append("")

        lines.append(f"# StateMachine: {self.name}")
        lines.append(f"sm = StateMachine(name={self.name!r})")
        lines.append(self.config.to_code(sm_var="sm"))
        
        for state in self.states:
            lines.append(f"sm.add_state({state._var_name})")
            
        for t in self.triggers:
            lines.append(f"sm.add_trigger({t.to_code()})")

        return "\n".join(lines)

class State:
    def __init__(self, element_id: str, name: str, parent_id: str, state_type: str, ntype: int) -> None:
        self.element_id:  str              = element_id
        self.name:        str              = name
        self.parent_id:   Optional[str]    = parent_id
        self.state_type:  str              = state_type
        self.ntype:       int              = ntype
        self.transitions: list[Transition] = []
        self.entry:       Optional[str]    = None
        self.exit:        Optional[str]    = None
        self.do:          Optional[str]    = None

    def add_transition(self, transition: Transition) -> None:
        self.transitions.append(transition)

    @property
    def is_final(self) -> bool:
        return self.state_type == "StateNode" and self.ntype == 4
    @property
    def is_initial(self) -> bool:
        return self.state_type == "StateNode" and self.ntype == 3
    @property
    def is_entry_point(self) -> bool:
        return self.state_type == "StateNode" and self.ntype == 13
    
    def to_code(self, id_to_state: dict) -> str:
        var_name = getattr(self, '_var_name', 'state_unknown')
        unique_name = getattr(self, '_unique_name', self.name)
        
        parent_str = "None"
        if self.parent_id and self.parent_id in id_to_state:
            parent_str = repr(id_to_state[self.parent_id]._unique_name)

        lines = []
        lines.append(f"# State: {unique_name}")
        lines.append(f"{var_name} = State(element_id={unique_name!r}, name={self.name!r}, parent_id={parent_str}, state_type={self.state_type!r}, ntype={self.ntype})")
        if self.entry: lines.append(f"{var_name}.entry = {self.entry!r}")
        if self.exit:  lines.append(f"{var_name}.exit  = {self.exit!r}")
        if self.do:    lines.append(f"{var_name}.do    = {self.do!r}")
        
        for t in self.transitions:
            lines.append(f"{var_name}.add_transition({t.to_code(id_to_state)})")
            
        return "\n".join(lines)

class Transition:
    def __init__(
        self,
        connector_id:   str,
        source_id:      str,
        target_id:      str,
        events:         list[str] = [],
        guard:          str = "",
        action:         str = "",
    ) -> None:
        self.connector_id:  str = connector_id
        self.source_id:     str = source_id
        self.target_id:     str = target_id
        self.events:        list[str] = events
        self.guard:         str = guard
        self.action:        str = action
    
    def to_code(self, id_to_state: dict) -> str:

        source_name = id_to_state[self.source_id]._unique_name if self.source_id in id_to_state else str(self.source_id)
        target_name = id_to_state[self.target_id]._unique_name if self.target_id in id_to_state else str(self.target_id)

        return (f"Transition("
                f"connector_id={self.connector_id}, "
                f"source_id={repr(source_name)}, "
                f"target_id={repr(target_name)}, "
                f"events={self.events!r}, "
                f"guard={self.guard!r}, "
                f"action={self.action!r})")

@dataclass
class Trigger:
    name:         str
    trigger_type: str
    value:        int = 0

    def to_code(self) -> str:
        return (f"Trigger("
                f"name={self.name!r}, "
                f"trigger_type={self.trigger_type!r}, "
                f"value={self.value})")

@dataclass
class DiagramConfig:
    path:          str = "./"
    loop_time:     str = "1"
    event_prefix:  str = ""
    state_prefix:  str = ""
    action_prefix: str = ""
    guard_prefix:  str = ""
    author:        str = ""
    modified_date: str = ""

    def to_code(self, sm_var: str = "sm") -> str:
        lines = []
        lines.append(f"{sm_var}.config.path          = {self.path!r}")
        lines.append(f"{sm_var}.config.loop_time     = {self.loop_time!r}")
        lines.append(f"{sm_var}.config.event_prefix  = {self.event_prefix!r}")
        lines.append(f"{sm_var}.config.state_prefix  = {self.state_prefix!r}")
        lines.append(f"{sm_var}.config.action_prefix = {self.action_prefix!r}")
        lines.append(f"{sm_var}.config.guard_prefix  = {self.guard_prefix!r}")
        lines.append(f"{sm_var}.config.author        = {self.author!r}")
        lines.append(f"{sm_var}.config.modified_date = {self.modified_date!r}")
        return "\n".join(lines)