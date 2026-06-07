"""
Unit tests for GeneratorStateMachine Python code.

Covers:
  - DiagramConfig.to_code()
  - State properties and to_code()
  - Transition.to_code()
  - Trigger.to_code()
  - StateMachine.to_code()
  - Custom exceptions
  - CVerifyGenerator._q(), _c_safe(), _parent_name(), _state_type_label()
  - CVerifyGenerator generated file structure
"""
from __future__ import annotations
import os
import sys
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
BACKENDS_DIR = os.path.join(PROJECT_ROOT, 'backends')
PARSER_DIR   = os.path.join(PROJECT_ROOT, 'parser')
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKENDS_DIR)
sys.path.insert(0, PARSER_DIR)

from template import StateMachine, State, Transition, Trigger, DiagramConfig
from exceptions import (VirtualException, RepositoryConnectionError,
                        DiagramNotFoundError, InvalidDiagramError)
from backend_c_verify_generator import CVerifyGenerator
from conftest import (make_normal_state, make_initial_state,
                      make_final_state, make_entry_point_state)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DiagramConfig
# ═══════════════════════════════════════════════════════════════════════════════
class TestDiagramConfig:

    def test_default_values(self):
        c = DiagramConfig()
        assert c.path          == './'
        assert c.loop_time     == '1'
        assert c.event_prefix  == ''
        assert c.state_prefix  == ''
        assert c.author        == ''
        assert c.modified_date == ''

    def test_to_code_contains_all_fields(self):
        c = DiagramConfig(path='/out', loop_time='5', event_prefix='EV',
                          state_prefix='ST', author='me', modified_date='2025')
        code = c.to_code()
        assert "path"          in code
        assert "loop_time"     in code
        assert "event_prefix"  in code
        assert "state_prefix"  in code
        assert "author"        in code
        assert "modified_date" in code

    def test_to_code_values_appear(self):
        c = DiagramConfig(path='/output', loop_time='42', author='alice')
        code = c.to_code()
        assert "'/output'" in code
        assert "'42'"      in code
        assert "'alice'"   in code

    def test_to_code_custom_sm_var(self):
        c = DiagramConfig()
        code = c.to_code(sm_var='machine')
        assert code.startswith('machine.config.path')

    def test_to_code_is_valid_python(self):
        """Generated code must be executable Python."""
        sm = StateMachine(name='T')
        sm.config = DiagramConfig(path='./', loop_time='1', author='test')
        code = sm.config.to_code()
        exec(compile(code, '<config>', 'exec'), {'sm': sm})


# ═══════════════════════════════════════════════════════════════════════════════
# 2. State
# ═══════════════════════════════════════════════════════════════════════════════
class TestState:

    def test_is_final_true(self):
        s = make_final_state('f1', 'Final')
        assert s.is_final is True

    def test_is_final_false_wrong_ntype(self):
        s = State('x', 'X', None, 'StateNode', 0)
        assert s.is_final is False

    def test_is_final_false_wrong_type(self):
        s = State('x', 'X', None, 'State', 4)
        assert s.is_final is False

    def test_is_initial_true(self):
        s = make_initial_state('i1')
        assert s.is_initial is True

    def test_is_initial_false(self):
        s = make_normal_state('n1', 'Normal')
        assert s.is_initial is False

    def test_is_entry_point_true(self):
        s = make_entry_point_state('ep1', 'EntryPoint')
        assert s.is_entry_point is True

    def test_is_entry_point_false(self):
        s = make_initial_state('i1')
        assert s.is_entry_point is False

    def test_final_initial_entry_mutually_exclusive(self):
        final   = make_final_state('f', 'F')
        initial = make_initial_state('i')
        ep      = make_entry_point_state('e', 'E')
        assert not (final.is_initial or final.is_entry_point)
        assert not (initial.is_final or initial.is_entry_point)
        assert not (ep.is_final or ep.is_initial)

    def test_add_transition(self):
        s = make_normal_state('a', 'A')
        t = Transition('c0', 'a', 'b', ['EVT'], '', '')
        s.add_transition(t)
        assert len(s.transitions) == 1
        assert s.transitions[0] is t

    def test_to_code_no_parent(self):
        sm = StateMachine(name='T')
        s  = make_normal_state('s1', 'MyState')
        sm.add_state(s)
        sm.to_code()  # assigns _var_name/_unique_name
        code = s.to_code({})
        assert 'parent_id=None' in code
        assert 'MyState' in code

    def test_to_code_entry_exit_do(self):
        sm = StateMachine(name='T')
        s  = make_normal_state('s1', 'A')
        s.entry = 'doEntry'
        s.exit  = 'doExit'
        s.do    = 'doDo'
        sm.add_state(s)
        sm.to_code()
        code = s.to_code({})
        assert 'doEntry' in code
        assert 'doExit'  in code
        assert 'doDo'    in code

    def test_to_code_no_entry_exit_do_when_none(self):
        sm = StateMachine(name='T')
        s  = make_normal_state('s1', 'A')
        sm.add_state(s)
        sm.to_code()
        code = s.to_code({})
        assert '.entry' not in code
        assert '.exit'  not in code
        assert '.do'    not in code

    def test_to_code_with_parent(self):
        sm     = StateMachine(name='T')
        parent = make_normal_state('p', 'Parent')
        child  = make_normal_state('c', 'Child', parent_id='p')
        sm.add_state(parent)
        sm.add_state(child)
        sm.to_code()
        id_map = {'p': parent, 'c': child}
        code = child.to_code(id_map)
        assert 'Parent' in code


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Transition
# ═══════════════════════════════════════════════════════════════════════════════
class TestTransition:

    def _id_map(self):
        a = make_normal_state('a', 'StateA')
        b = make_normal_state('b', 'StateB')
        a._unique_name = 'StateA'
        b._unique_name = 'StateB'
        return {'a': a, 'b': b}

    def test_to_code_basic(self):
        t    = Transition('c1', 'a', 'b', ['EVT'], 'guard1', 'action1')
        code = t.to_code(self._id_map())
        assert 'EVT'     in code
        assert 'guard1'  in code
        assert 'action1' in code

    def test_to_code_multiple_events(self):
        t    = Transition('c1', 'a', 'b', ['E1', 'E2', 'E3'], '', '')
        code = t.to_code(self._id_map())
        assert "'E1'" in code
        assert "'E2'" in code
        assert "'E3'" in code

    def test_to_code_empty_events(self):
        t    = Transition('c1', 'a', 'b', [], '', '')
        code = t.to_code(self._id_map())
        assert 'events=[]' in code

    def test_to_code_source_target_resolved(self):
        t    = Transition('c1', 'a', 'b', [], '', '')
        code = t.to_code(self._id_map())
        assert 'StateA' in code
        assert 'StateB' in code

    def test_to_code_unknown_id_uses_raw(self):
        a = make_normal_state('a', 'A')
        a._unique_name = 'A'   # to_code() requires _unique_name set
        t    = Transition('c1', 'a', 'unknown_id', [], '', '')
        code = t.to_code({'a': a})
        assert 'unknown_id' in code

    def test_to_code_guard_action_empty_string(self):
        t    = Transition('c1', 'a', 'b', [], '', '')
        code = t.to_code(self._id_map())
        assert "guard=''"  in code
        assert "action=''" in code


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Trigger
# ═══════════════════════════════════════════════════════════════════════════════
class TestTrigger:

    def test_default_value_is_zero(self):
        t = Trigger(name='EVT', trigger_type='HSM_CALLBACK')
        assert t.value == 0

    def test_to_code_name_and_type(self):
        t    = Trigger(name='MY_EVENT', trigger_type='HSM_CALLBACK', value=0)
        code = t.to_code()
        assert 'MY_EVENT'     in code
        assert 'HSM_CALLBACK' in code

    def test_to_code_timing_type_with_value(self):
        t    = Trigger(name='TIMER', trigger_type='HSM_TIMING', value=100)
        code = t.to_code()
        assert 'HSM_TIMING' in code
        assert '100'        in code

    def test_to_code_is_valid_python(self):
        t    = Trigger(name='E', trigger_type='HSM_CALLBACK', value=0)
        code = t.to_code()
        result = eval(code, {'Trigger': Trigger})
        assert result.name         == 'E'
        assert result.trigger_type == 'HSM_CALLBACK'


# ═══════════════════════════════════════════════════════════════════════════════
# 5. StateMachine
# ═══════════════════════════════════════════════════════════════════════════════
class TestStateMachine:

    def test_add_state_appends(self):
        sm = StateMachine(name='T')
        s  = make_normal_state('s', 'S')
        sm.add_state(s)
        assert s in sm.states

    def test_add_trigger_appends(self):
        sm = StateMachine(name='T')
        t  = Trigger(name='E', trigger_type='HSM_CALLBACK')
        sm.add_trigger(t)
        assert t in sm.triggers

    def test_to_code_contains_state_names(self):
        sm = StateMachine(name='MyHSM')
        sm.add_state(make_initial_state('i', 'Initial'))
        sm.add_state(make_normal_state('a', 'Alpha'))
        code = sm.to_code()
        assert 'Initial' in code
        assert 'Alpha'   in code

    def test_to_code_contains_trigger_names(self):
        sm = StateMachine(name='T')
        sm.add_trigger(Trigger('EVT_X', 'HSM_CALLBACK'))
        sm.add_trigger(Trigger('EVT_Y', 'HSM_TIMING', 5))
        code = sm.to_code()
        assert 'EVT_X' in code
        assert 'EVT_Y' in code

    def test_to_code_is_valid_python(self):
        """The full to_code() output must be executable Python."""
        sm  = StateMachine(name='Mini')
        ini = make_initial_state('i', 'Initial')
        a   = make_normal_state('a', 'StateA')
        ini.add_transition(Transition(1, 'i', 'a', [], '', ''))
        sm.add_state(ini)
        sm.add_state(a)
        sm.add_trigger(Trigger('EVT', 'HSM_CALLBACK'))
        code = sm.to_code()
        ns = {'StateMachine': StateMachine, 'State': State,
              'Transition': Transition, 'Trigger': Trigger}
        exec(compile(code, '<sm>', 'exec'), ns)

    def test_duplicate_state_names_get_unique_var(self):
        """States with the same name in different parents must get distinct variables."""
        sm     = StateMachine(name='T')
        parent = make_normal_state('p', 'Parent')
        i1     = make_initial_state('i1', 'Initial', parent_id='p')
        i2     = make_initial_state('i2', 'Initial', parent_id=None)
        sm.add_state(parent)
        sm.add_state(i1)
        sm.add_state(i2)
        code = sm.to_code()
        # Both vars must appear, not just one
        assert 'state_initial_parent' in code or code.count('state_initial') >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Custom exceptions
# ═══════════════════════════════════════════════════════════════════════════════
class TestExceptions:

    def test_virtual_exception_is_exception(self):
        assert issubclass(VirtualException, Exception)

    def test_virtual_exception_message_no_args(self):
        e = VirtualException()
        assert 'Virtual method not implemented' in str(e)

    def test_virtual_exception_message_with_args(self):
        e = VirtualException(type_name='MyClass', func_name='my_func')
        msg = str(e)
        assert 'MyClass'   in msg
        assert 'my_func'   in msg

    def test_repository_connection_error(self):
        with pytest.raises(RepositoryConnectionError):
            raise RepositoryConnectionError("db unreachable")

    def test_diagram_not_found_error(self):
        with pytest.raises(DiagramNotFoundError):
            raise DiagramNotFoundError("no such diagram")

    def test_invalid_diagram_error(self):
        with pytest.raises(InvalidDiagramError):
            raise InvalidDiagramError("missing initial state")

    def test_all_are_exceptions(self):
        for cls in (VirtualException, RepositoryConnectionError,
                    DiagramNotFoundError, InvalidDiagramError):
            assert issubclass(cls, Exception)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. CVerifyGenerator helper methods
# ═══════════════════════════════════════════════════════════════════════════════
class TestCVerifyGeneratorHelpers:
    """Tests _q, _c_safe, _parent_name, _state_type_label in isolation."""

    @pytest.fixture(autouse=True)
    def gen(self, minimal_sm):
        self.g = CVerifyGenerator(minimal_sm)

    def test_q_none_returns_none_literal(self):
        assert self.g._q(None) == '"none"'

    def test_q_empty_string_returns_none_literal(self):
        assert self.g._q('') == '"none"'

    def test_q_whitespace_only_returns_none_literal(self):
        assert self.g._q('   ') == '"none"'

    def test_q_value_wrapped_in_quotes(self):
        assert self.g._q('hello') == '"hello"'

    def test_q_strips_whitespace(self):
        assert self.g._q('  stripped  ') == '"stripped"'

    def test_c_safe_escapes_percent(self):
        assert '%%' in self.g._c_safe('50%')

    def test_c_safe_escapes_backslash(self):
        assert '\\\\' in self.g._c_safe('C:\\path')

    def test_c_safe_escapes_double_quote(self):
        assert '\\"' in self.g._c_safe('say "hello"')

    def test_c_safe_none_returns_none_string(self):
        assert self.g._c_safe(None) == 'none'

    def test_c_safe_empty_returns_none_string(self):
        assert self.g._c_safe('') == 'none'

    def test_parent_name_with_known_parent(self):
        parent = make_normal_state('p', 'ParentState')
        child  = make_normal_state('c', 'Child', parent_id='p')
        self.g._id_to_state = {'p': parent, 'c': child}
        assert self.g._parent_name(child) == 'ParentState'

    def test_parent_name_no_parent(self):
        s = make_normal_state('s', 'Orphan')
        assert self.g._parent_name(s) == 'none'

    def test_parent_name_unknown_parent_id(self):
        s = make_normal_state('s', 'X', parent_id='nonexistent')
        assert self.g._parent_name(s) == 'none'

    def test_state_type_label_final(self):
        assert self.g._state_type_label(make_final_state('f', 'F')) == 'final'

    def test_state_type_label_initial(self):
        assert self.g._state_type_label(make_initial_state('i')) == 'initial'

    def test_state_type_label_normal(self):
        assert self.g._state_type_label(make_normal_state('n', 'N')) == 'normal'

    def test_state_type_label_entry_point(self):
        # entry_point is not final/initial, so it falls through to "normal"
        assert self.g._state_type_label(make_entry_point_state('e', 'E')) == 'normal'


# ═══════════════════════════════════════════════════════════════════════════════
# 8. CVerifyGenerator generated file structure
# ═══════════════════════════════════════════════════════════════════════════════
class TestCVerifyGeneratorOutput:

    @pytest.fixture(autouse=True)
    def generate(self, minimal_sm):
        self.sm  = minimal_sm
        self.gen = CVerifyGenerator(minimal_sm)
        self.gen.generate()
        out  = minimal_sm.config.path
        name = self.gen._verify_name
        with open(os.path.join(out, f'{name}.h')) as f:
            self.h = f.read()
        with open(os.path.join(out, f'{name}.c')) as f:
            self.c = f.read()

    # ── Header ────────────────────────────────────────────────────────────────

    def test_h_file_created(self, minimal_sm):
        assert os.path.exists(
            os.path.join(minimal_sm.config.path, f'{self.gen._verify_name}.h'))

    def test_h_has_include_guard(self):
        assert '#ifndef' in self.h
        assert '#define' in self.h
        assert '#endif'  in self.h

    def test_h_has_print_declaration(self):
        assert f'{self.gen._verify_name}_print(void)' in self.h

    def test_h_has_verify_counts_declaration(self):
        assert f'{self.gen._verify_name}_verify_counts(' in self.h

    # ── Source ────────────────────────────────────────────────────────────────

    def test_c_file_created(self, minimal_sm):
        assert os.path.exists(
            os.path.join(minimal_sm.config.path, f'{self.gen._verify_name}.c'))

    def test_c_includes_its_own_header(self):
        assert f'#include "{self.gen._verify_name}.h"' in self.c

    def test_c_includes_stdio(self):
        assert '#include <stdio.h>' in self.c

    def test_c_has_print_function(self):
        assert f'void {self.gen._verify_name}_print(void)' in self.c

    def test_c_has_verify_counts_function(self):
        assert f'int {self.gen._verify_name}_verify_counts(' in self.c

    def test_c_has_ifdef_verify_main(self):
        assert '#ifdef VERIFY_MAIN' in self.c

    def test_c_has_main_function(self):
        assert 'int main(void)' in self.c

    def test_c_main_calls_print(self):
        assert f'{self.gen._verify_name}_print()' in self.c

    def test_c_main_calls_verify_counts(self):
        assert f'{self.gen._verify_name}_verify_counts(' in self.c

    def test_c_has_exit_success(self):
        assert 'EXIT_SUCCESS' in self.c

    def test_c_config_hsm_name_appears(self):
        assert 'TestHSM' in self.c

    def test_c_config_author_appears(self):
        assert 'tester' in self.c

    def test_c_state_names_appear(self):
        for name in ('StateA', 'StateB', 'Initial', 'Final'):
            assert name in self.c, f'State name "{name}" not found in .c'

    def test_c_trigger_names_appear(self):
        assert 'EVT_GO' in self.c

    def test_c_has_manifest_lines(self):
        assert 'MANIFEST:state_count='      in self.c
        assert 'MANIFEST:transition_count=' in self.c
        assert 'MANIFEST:trigger_count='    in self.c

    def test_c_manifest_counts_are_correct(self):
        """Baked-in counts must match what we put in the model."""
        import re
        m = re.search(r'MANIFEST:state_count=(\d+)', self.c)
        assert m and int(m.group(1)) == 4    # init, A, B, final

        m = re.search(r'MANIFEST:transition_count=(\d+)', self.c)
        assert m and int(m.group(1)) == 3    # c0, c1, c2

        m = re.search(r'MANIFEST:trigger_count=(\d+)', self.c)
        assert m and int(m.group(1)) == 1    # EVT_GO

    def test_c_guard_and_action_appear(self):
        assert 'guardA'  in self.c
        assert 'actionA' in self.c

    def test_c_percent_in_name_escaped(self, tmp_path):
        """A state name with '%' must produce '%%' in printf, not a raw '%'."""
        import re
        sm = StateMachine(name='T')
        sm.config.path = str(tmp_path)
        s = make_normal_state('s1', '50%_done')
        sm.add_state(s)
        gen = CVerifyGenerator(sm)
        gen.generate()
        with open(os.path.join(str(tmp_path), f'{gen._verify_name}.c')) as f:
            c = f.read()
        # Every printf call must not contain a lone % (i.e. not followed by %)
        # Extract only the format-string arguments from printf lines
        printf_strs = re.findall(r'printf\("([^"\\]|\\.)*"\)', c)
        for ps in printf_strs:
            # Remove escaped %% pairs, then check no % remains
            cleaned = ps.replace('%%', '')
            assert '%' not in cleaned, (
                f'Unescaped %% in printf format string: {ps!r}'
            )
