####################################################
#      AUTO-GENERATED — do not modify manually     #
####################################################

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

# State: ChildA
state_childa = State(element_id='ChildA', name='ChildA', parent_id=None, state_type='State', ntype=0)
state_childa.entry = 'EntryChildA'
state_childa.exit  = 'ExitChildA'
state_childa.add_transition(Transition(connector_id=27, source_id='ChildA', target_id='ChildB', events=['EVENTA'], guard='', action=''))
state_childa.add_transition(Transition(connector_id=10, source_id='ChildA', target_id='ChildB', events=['EVENT4', 'TRANSITION_CHILDA_TO_CHILDB'], guard='!guard4', action=''))
state_childa.add_transition(Transition(connector_id=8, source_id='ChildA', target_id='ChildA', events=['FIRST_TRIGGER'], guard='guardAnnounce', action=''))
state_childa.add_transition(Transition(connector_id=7, source_id='ChildA', target_id='ChildA', events=['SECOND_TRIGGER2'], guard='', action=''))

# State: GrandParentC
state_grandparentc = State(element_id='GrandParentC', name='GrandParentC', parent_id=None, state_type='State', ntype=0)
state_grandparentc.entry = 'EntryGrandParentC'
state_grandparentc.exit  = 'ExitGrandParentC'
state_grandparentc.add_transition(Transition(connector_id=34, source_id='GrandParentC', target_id='ChildC', events=['CC1', 'CC2'], guard='', action=''))
state_grandparentc.add_transition(Transition(connector_id=30, source_id='GrandParentC', target_id='ChildD', events=['PRUEBA1'], guard='', action=''))
state_grandparentc.add_transition(Transition(connector_id=21, source_id='GrandParentC', target_id='ChildD', events=['TRANSITION_GRANDPARENTC_TO_CHILDD'], guard='guard4&&guard5', action=''))

# State: ParentC
state_parentc = State(element_id='ParentC', name='ParentC', parent_id='GrandParentC', state_type='State', ntype=0)
state_parentc.entry = 'EntryParentC'
state_parentc.exit  = 'ExitParentC'
state_parentc.add_transition(Transition(connector_id=33, source_id='ParentC', target_id='ChildC', events=['PP1', 'PP2'], guard='', action=''))

# State: ChildC
state_childc = State(element_id='ChildC', name='ChildC', parent_id='ParentC', state_type='State', ntype=0)
state_childc.entry = 'EntryChildC'
state_childc.exit  = 'ExitChildC'
state_childc.add_transition(Transition(connector_id=19, source_id='ChildC', target_id='ChildC', events=['SELF_TRANSITION_STATE7', 'SELF_TRANSITION2_STATE7'], guard='', action=''))

# State: Initial_ParentC
state_initial_parentc = State(element_id='Initial_ParentC', name='Initial', parent_id='ParentC', state_type='StateNode', ntype=3)
state_initial_parentc.add_transition(Transition(connector_id=16, source_id='Initial_ParentC', target_id='ChildC', events=[], guard='', action=''))

# State: Initial_GrandParentC
state_initial_grandparentc = State(element_id='Initial_GrandParentC', name='Initial', parent_id='GrandParentC', state_type='StateNode', ntype=3)
state_initial_grandparentc.add_transition(Transition(connector_id=15, source_id='Initial_GrandParentC', target_id='ChildC', events=[], guard='', action=''))

# State: ParentB
state_parentb = State(element_id='ParentB', name='ParentB', parent_id=None, state_type='State', ntype=0)
state_parentb.entry = 'EntryParentB'
state_parentb.exit  = 'ExitParentB'
state_parentb.add_transition(Transition(connector_id=17, source_id='ParentB', target_id='ChildC', events=['TRANSITION_PARENT_B_TO_PARENTC'], guard='', action='CompleteState2'))

# State: ChildB
state_childb = State(element_id='ChildB', name='ChildB', parent_id='ParentB', state_type='State', ntype=0)
state_childb.entry = 'EntryChildB'
state_childb.exit  = 'ExitChildB'
state_childb.add_transition(Transition(connector_id=35, source_id='ChildB', target_id='ChildB', events=['BB1', 'BB2'], guard='', action=''))
state_childb.add_transition(Transition(connector_id=28, source_id='ChildB', target_id='SiblingB', events=['EVENTA'], guard='', action=''))
state_childb.add_transition(Transition(connector_id=11, source_id='ChildB', target_id='SiblingB', events=['TRANSITION_CHILDB_TO_SIBLINGB'], guard='', action=''))

# State: SiblingB
state_siblingb = State(element_id='SiblingB', name='SiblingB', parent_id='ParentB', state_type='State', ntype=0)
state_siblingb.entry = 'EntrySiblingB'
state_siblingb.exit  = 'ExitSiblingB'

# State: Initial_ParentB
state_initial_parentb = State(element_id='Initial_ParentB', name='Initial', parent_id='ParentB', state_type='StateNode', ntype=3)
state_initial_parentb.add_transition(Transition(connector_id=12, source_id='Initial_ParentB', target_id='ChildB', events=[], guard='', action=''))

# State: ParentD
state_parentd = State(element_id='ParentD', name='ParentD', parent_id=None, state_type='State', ntype=0)
state_parentd.add_transition(Transition(connector_id=32, source_id='ParentD', target_id='ChildD', events=['DD1', 'DD2'], guard='', action=''))
state_parentd.add_transition(Transition(connector_id=22, source_id='ParentD', target_id='ChildB', events=[], guard='', action=''))

# State: ChildD
state_childd = State(element_id='ChildD', name='ChildD', parent_id='ParentD', state_type='State', ntype=0)
state_childd.add_transition(Transition(connector_id=31, source_id='ChildD', target_id='ChildD', events=['XX1', 'XX2'], guard='', action=''))
state_childd.add_transition(Transition(connector_id=26, source_id='ChildD', target_id='Final', events=[], guard='', action=''))

# State: Initial_ParentD
state_initial_parentd = State(element_id='Initial_ParentD', name='Initial', parent_id='ParentD', state_type='StateNode', ntype=3)
state_initial_parentd.add_transition(Transition(connector_id=25, source_id='Initial_ParentD', target_id='ChildD', events=[], guard='', action=''))
state_initial_parentd.add_transition(Transition(connector_id=24, source_id='Initial_ParentD', target_id='42', events=[], guard='', action=''))
state_initial_parentd.add_transition(Transition(connector_id=23, source_id='Initial_ParentD', target_id='46', events=[], guard='', action=''))

# State: Final
state_final = State(element_id='Final', name='Final', parent_id='ParentD', state_type='StateNode', ntype=4)

# State: Initial
state_initial = State(element_id='Initial', name='Initial', parent_id=None, state_type='StateNode', ntype=3)
state_initial.add_transition(Transition(connector_id=9, source_id='Initial', target_id='ChildA', events=[], guard='', action=''))

# StateMachine: Unit_Test
sm = StateMachine(name='Unit_Test')
sm.config.path          = 'C:\\Users\\IDPCJ0\\Documents\\Personal\\code\\GeneratorStateMachine'
sm.config.loop_time     = '1'
sm.config.event_prefix  = 'EVT2'
sm.config.state_prefix  = 'STA'
sm.config.action_prefix = ''
sm.config.guard_prefix  = ''
sm.config.author        = 'IDPMN0'
sm.config.modified_date = '2026-04-01 10:00:49'
sm.add_state(state_childa)
sm.add_state(state_grandparentc)
sm.add_state(state_parentc)
sm.add_state(state_childc)
sm.add_state(state_initial_parentc)
sm.add_state(state_initial_grandparentc)
sm.add_state(state_parentb)
sm.add_state(state_childb)
sm.add_state(state_siblingb)
sm.add_state(state_initial_parentb)
sm.add_state(state_parentd)
sm.add_state(state_childd)
sm.add_state(state_initial_parentd)
sm.add_state(state_final)
sm.add_state(state_initial)
sm.add_trigger(Trigger(name='PRUEBA1', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='XX1', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='XX2', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='DD1', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='DD2', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='PP1', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='CC1', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='CC2', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='BB1', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='PP2', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='BB2', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='FIRST_TRIGGER', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='SECOND_TRIGGER2', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='TRANSITION_STATE1_TO_STATE2', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='TRANSITION_CHILDB_TO_SIBLINGB', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='EVENT4', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='TRANSITION_CHILDA_TO_CHILDB', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='EVENTA', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='SELF_TRANSITION_STATE7', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='SELF_TRANSITION2_STATE7', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='TRANSITION_PARENT_B_TO_PARENTC', trigger_type='HSM_CALLBACK', value=0))
sm.add_trigger(Trigger(name='TRANSITION_GRANDPARENTC_TO_CHILDD', trigger_type='HSM_TIMING', value=10))