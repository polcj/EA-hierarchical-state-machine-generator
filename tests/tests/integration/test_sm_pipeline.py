"""
Integration tests for CVerifyGenerator.

Strategy
--------
1. Load hsm_test_cases_model.py (pre-generated, no DB needed) as ground truth.
2. Run CVerifyGenerator.generate() → produces <name>_verify.c / .h
3. Compile with gcc -DVERIFY_MAIN
4. Run the binary and capture stdout
5. Parse MANIFEST lines and compare against the Python model
6. Verify that all state/trigger names appear in the output

The key invariant: 0% information loss between the EA diagram
(captured in the model) and the generated C output.
"""
from __future__ import annotations
import os
import sys
import re
import shutil
import subprocess
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
BACKENDS_DIR = os.path.join(PROJECT_ROOT, 'backends')
PARSER_DIR   = os.path.join(PROJECT_ROOT, 'parser')
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKENDS_DIR)
sys.path.insert(0, PARSER_DIR)

from backend_c_verify_generator import CVerifyGenerator

# ── Skip entire module if gcc is not available ─────────────────────────────
if not shutil.which('gcc'):
    pytest.skip('gcc not found — install gcc to run C integration tests',
                allow_module_level=True)


# ── Helpers ────────────────────────────────────────────────────────────────

def _compile(c_file: str, binary: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['gcc', '-DVERIFY_MAIN', '-std=c11', c_file, '-o', binary],
        capture_output=True, text=True
    )


def _run(binary: str) -> subprocess.CompletedProcess:
    return subprocess.run([binary], capture_output=True, text=True)


def _parse_manifest(stdout: str) -> dict[str, int]:
    """Extract all MANIFEST:key=value lines into a dict."""
    result = {}
    for line in stdout.splitlines():
        m = re.match(r'MANIFEST:(\w+)=(\d+)', line.strip())
        if m:
            result[m.group(1)] = int(m.group(2))
    return result


def _expected_counts(sm) -> dict[str, int]:
    """Compute expected counts directly from the Python model."""
    all_states   = sm.states
    transitions  = sum(len(s.transitions) for s in all_states)
    normal       = sum(1 for s in all_states if not s.is_initial and not s.is_final)
    initial      = sum(1 for s in all_states if s.is_initial)
    final        = sum(1 for s in all_states if s.is_final)
    return {
        'state_count':         len(all_states),
        'normal_state_count':  normal,
        'initial_state_count': initial,
        'final_state_count':   final,
        'transition_count':    transitions,
        'trigger_count':       len(sm.triggers),
    }


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def generated(tmp_path_factory, real_sm):
    """Generate, compile, and run once for all tests in this module."""
    tmp     = str(tmp_path_factory.mktemp('verify_gen'))
    real_sm.config.path = tmp

    gen = CVerifyGenerator(real_sm)
    gen.generate()

    name   = gen._verify_name
    c_file = os.path.join(tmp, f'{name}.c')
    h_file = os.path.join(tmp, f'{name}.h')
    binary = os.path.join(tmp, 'verify')

    compile_result = _compile(c_file, binary)
    run_result     = _run(binary) if compile_result.returncode == 0 else None

    return {
        'sm':             real_sm,
        'gen':            gen,
        'tmp':            tmp,
        'c_file':         c_file,
        'h_file':         h_file,
        'binary':         binary,
        'compile_result': compile_result,
        'run_result':     run_result,
        'expected':       _expected_counts(real_sm),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# A. File generation
# ═══════════════════════════════════════════════════════════════════════════════
class TestGeneration:

    def test_c_file_exists(self, generated):
        assert os.path.exists(generated['c_file']), '.c file was not created'

    def test_h_file_exists(self, generated):
        assert os.path.exists(generated['h_file']), '.h file was not created'

    def test_c_file_not_empty(self, generated):
        assert os.path.getsize(generated['c_file']) > 0

    def test_h_file_not_empty(self, generated):
        assert os.path.getsize(generated['h_file']) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# B. Compilation
# ═══════════════════════════════════════════════════════════════════════════════
class TestCompilation:

    def test_compiles_without_errors(self, generated):
        r = generated['compile_result']
        assert r.returncode == 0, (
            f'gcc failed:\nstdout: {r.stdout}\nstderr: {r.stderr}'
        )

    def test_no_compiler_errors(self, generated):
        """stderr must not contain 'error:' — warnings are acceptable."""
        r = generated['compile_result']
        errors = [l for l in r.stderr.splitlines() if 'error:' in l]
        assert errors == [], f'Compiler errors:\n' + '\n'.join(errors)

    def test_binary_exists(self, generated):
        assert os.path.exists(generated['binary'])


# ═══════════════════════════════════════════════════════════════════════════════
# C. Execution
# ═══════════════════════════════════════════════════════════════════════════════
class TestExecution:

    def test_binary_exits_zero(self, generated):
        r = generated['run_result']
        assert r is not None, 'Binary was not run (compilation failed)'
        assert r.returncode == 0, f'Binary exited with {r.returncode}:\n{r.stdout}'

    def test_output_not_empty(self, generated):
        assert generated['run_result'].stdout.strip() != ''

    def test_output_has_config_section(self, generated):
        assert '=== CONFIG ===' in generated['run_result'].stdout

    def test_output_has_states_section(self, generated):
        assert '=== STATES (' in generated['run_result'].stdout

    def test_output_has_triggers_section(self, generated):
        assert '=== TRIGGERS (' in generated['run_result'].stdout

    def test_output_has_summary_section(self, generated):
        assert '=== SUMMARY ===' in generated['run_result'].stdout

    def test_output_has_manifest_section(self, generated):
        assert '=== MANIFEST ===' in generated['run_result'].stdout


# ═══════════════════════════════════════════════════════════════════════════════
# D. MANIFEST counts — 0% information loss
# ═══════════════════════════════════════════════════════════════════════════════
class TestManifestCounts:
    """
    These are the key correctness tests: every count in the generated C output
    must exactly match what the Python model says.
    """

    @pytest.fixture(autouse=True)
    def setup(self, generated):
        self.manifest = _parse_manifest(generated['run_result'].stdout)
        self.expected = generated['expected']

    def test_manifest_has_all_keys(self):
        required = {'state_count', 'normal_state_count', 'initial_state_count',
                    'final_state_count', 'transition_count', 'trigger_count'}
        missing = required - set(self.manifest.keys())
        assert missing == set(), f'Missing MANIFEST keys: {missing}'

    def test_state_count_matches_model(self):
        assert self.manifest['state_count'] == self.expected['state_count'], (
            f"state_count: got {self.manifest['state_count']}, "
            f"expected {self.expected['state_count']}"
        )

    def test_normal_state_count_matches_model(self):
        assert self.manifest['normal_state_count'] == self.expected['normal_state_count']

    def test_initial_state_count_matches_model(self):
        assert self.manifest['initial_state_count'] == self.expected['initial_state_count']

    def test_final_state_count_matches_model(self):
        assert self.manifest['final_state_count'] == self.expected['final_state_count']

    def test_transition_count_matches_model(self):
        assert self.manifest['transition_count'] == self.expected['transition_count'], (
            f"transition_count: got {self.manifest['transition_count']}, "
            f"expected {self.expected['transition_count']}"
        )

    def test_trigger_count_matches_model(self):
        assert self.manifest['trigger_count'] == self.expected['trigger_count']

    def test_counts_sum_coherence(self):
        """normal + initial + final must equal total states."""
        m = self.manifest
        assert (m['normal_state_count'] + m['initial_state_count']
                + m['final_state_count']) == m['state_count']


# ═══════════════════════════════════════════════════════════════════════════════
# E. Content correctness — names and values present in output
# ═══════════════════════════════════════════════════════════════════════════════
class TestContentCorrectness:

    @pytest.fixture(autouse=True)
    def setup(self, generated):
        self.out = generated['run_result'].stdout
        self.sm  = generated['sm']

    def test_all_state_names_in_output(self):
        """Every state name from the model must appear in the output."""
        missing = [s.name for s in self.sm.states if s.name not in self.out]
        assert missing == [], f'State names missing from output: {missing}'

    def test_all_trigger_names_in_output(self):
        """Every trigger name from the model must appear in the output."""
        missing = [t.name for t in self.sm.triggers if t.name not in self.out]
        assert missing == [], f'Trigger names missing from output: {missing}'

    def test_config_loop_time_in_output(self):
        assert self.sm.config.loop_time in self.out

    def test_config_event_prefix_in_output(self):
        assert self.sm.config.event_prefix in self.out

    def test_config_state_prefix_in_output(self):
        assert self.sm.config.state_prefix in self.out

    def test_config_author_in_output(self):
        assert self.sm.config.author in self.out

    def test_transition_events_in_output(self):
        """All event names that appear in transitions must be in output."""
        all_events = set()
        for s in self.sm.states:
            for tr in s.transitions:
                all_events.update(tr.events)
        missing = [e for e in all_events if e and e not in self.out]
        assert missing == [], f'Transition events missing from output: {missing}'

    def test_transition_guards_in_output(self):
        """Non-empty guards must appear in output."""
        guards = {tr.guard for s in self.sm.states for tr in s.transitions if tr.guard}
        missing = [g for g in guards if g not in self.out]
        assert missing == [], f'Guards missing from output: {missing}'

    def test_transition_actions_in_output(self):
        """Non-empty actions must appear in output."""
        actions = {tr.action for s in self.sm.states for tr in s.transitions if tr.action}
        missing = [a for a in actions if a not in self.out]
        assert missing == [], f'Actions missing from output: {missing}'

    def test_state_entry_actions_in_output(self):
        """Non-empty entry actions must appear in output."""
        entries = {s.entry for s in self.sm.states if s.entry}
        missing = [e for e in entries if e not in self.out]
        assert missing == [], f'Entry actions missing from output: {missing}'

    def test_state_exit_actions_in_output(self):
        """Non-empty exit actions must appear in output."""
        exits = {s.exit for s in self.sm.states if s.exit}
        missing = [e for e in exits if e not in self.out]
        assert missing == [], f'Exit actions missing from output: {missing}'

    def test_hsm_name_in_output(self):
        assert self.sm.name in self.out

    def test_parent_child_relationships_in_output(self):
        """For each child state, the parent name must appear near it in output."""
        id_to_state = {s.element_id: s for s in self.sm.states}
        for s in self.sm.states:
            if s.parent_id and s.parent_id in id_to_state:
                parent = id_to_state[s.parent_id]
                assert parent.name in self.out

    def test_summary_counts_correct(self):
        """Summary line must report correct total state count."""
        m = re.search(r'Total states\s*:\s*(\d+)', self.out)
        assert m, 'Summary "Total states" line not found'
        assert int(m.group(1)) == len(self.sm.states)

    def test_summary_transition_count_correct(self):
        m = re.search(r'Total transitions\s*:\s*(\d+)', self.out)
        assert m, 'Summary "Total transitions" line not found'
        expected = sum(len(s.transitions) for s in self.sm.states)
        assert int(m.group(1)) == expected

    def test_summary_trigger_count_correct(self):
        m = re.search(r'Total triggers\s*:\s*(\d+)', self.out)
        assert m, 'Summary "Total triggers" line not found'
        assert int(m.group(1)) == len(self.sm.triggers)
