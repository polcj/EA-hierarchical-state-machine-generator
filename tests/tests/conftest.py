"""
Shared pytest fixtures for GeneratorStateMachine test suite.
"""
from __future__ import annotations
import sys
import os
import pytest

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
BACKENDS_DIR = os.path.join(PROJECT_ROOT, 'backends')
PARSER_DIR   = os.path.join(PROJECT_ROOT, 'parser')

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKENDS_DIR)
sys.path.insert(0, PARSER_DIR)

# ── Minimal in-memory StateMachine builder ────────────────────────────────────
# Used by unit tests without touching any DB or file.

from template import StateMachine, State, Transition, Trigger, DiagramConfig


def make_state(element_id, name, parent_id=None, state_type='State', ntype=0):
    return State(element_id=element_id, name=name, parent_id=parent_id,
                 state_type=state_type, ntype=ntype)


def make_normal_state(eid, name, parent_id=None):
    return make_state(eid, name, parent_id, state_type='State', ntype=0)


def make_initial_state(eid, name='Initial', parent_id=None):
    return make_state(eid, name, parent_id, state_type='StateNode', ntype=3)


def make_final_state(eid, name='Final', parent_id=None):
    return make_state(eid, name, parent_id, state_type='StateNode', ntype=4)


def make_entry_point_state(eid, name, parent_id=None):
    return make_state(eid, name, parent_id, state_type='StateNode', ntype=13)


@pytest.fixture
def minimal_sm(tmp_path):
    """
    A tiny StateMachine for testing the generator:
      Initial → StateA → StateB → Final
    """
    sm = StateMachine(name='TestHSM')
    sm.config.path          = str(tmp_path)
    sm.config.loop_time     = '10'
    sm.config.event_prefix  = 'EVT'
    sm.config.state_prefix  = 'ST'
    sm.config.author        = 'tester'
    sm.config.modified_date = '2025-01-01'

    init  = make_initial_state('init_id',  'Initial')
    a     = make_normal_state( 'a_id',     'StateA')
    b     = make_normal_state( 'b_id',     'StateB')
    final = make_final_state(  'final_id', 'Final')

    a.entry = 'entryA'
    a.exit  = 'exitA'
    b.entry = 'entryB'

    init.add_transition(Transition('c0', 'init_id',  'a_id',     [], '', ''))
    a.add_transition(   Transition('c1', 'a_id',     'b_id',     ['EVT_GO'],  'guardA', 'actionA'))
    b.add_transition(   Transition('c2', 'b_id',     'final_id', [], '', ''))

    sm.add_trigger(Trigger(name='EVT_GO', trigger_type='HSM_CALLBACK', value=0))

    for s in (init, a, b, final):
        sm.add_state(s)

    return sm


@pytest.fixture(scope='module')
def real_sm():
    """
    Loads the pre-generated hsm_test_cases_model.py as the ground-truth model.
    This avoids any DB dependency and tests against the real EA diagram output.
    """
    import importlib.util
    model_path = os.path.join(PROJECT_ROOT, 'hsm_test_cases_model.py')
    spec = importlib.util.spec_from_file_location('hsm_test_cases_model', model_path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules['hsm_test_cases_model'] = mod   # needed for @dataclass
    spec.loader.exec_module(mod)
    return mod.sm
