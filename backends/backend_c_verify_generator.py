from __future__ import annotations

import os

from igenerator import IGenerator


class CVerifyGenerator(IGenerator):
    """Generates a .c / .h pair that prints the complete state machine model to stdout."""

    def __init__(self, sm) -> None:
        super().__init__(sm)

        self._config        = self._sm.config
        self._hsm_name      = self._sm.name
        self._hsm_name_up   = self._sm.name.upper()
        self._hsm_decorated = (self._sm.name + "_hsm").lower()
        self._verify_name   = self._hsm_decorated + "_verify"

        # id → state, keeping ALL states (including initial/final pseudo-states)
        self._id_to_state: dict[str, object] = {
            s.element_id: s for s in self._sm.states
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _c_safe(self, value) -> str:
        """
        Escape a value for safe embedding inside a C printf format string literal.
        Escapes: backslash → \\\\, double-quote → \\", percent → %%.
        """
        s = str(value).strip() if value else "none"
        if not s:
            s = "none"
        s = s.replace('\\', '\\\\')
        s = s.replace('"',  '\\"')
        s = s.replace('%',  '%%')
        return s

    def _q(self, value) -> str:
        """Return a C string literal for value, using 'none' when empty."""
        return f'"{self._c_safe(value)}"'

    def _parent_name(self, state) -> str:
        parent = self._id_to_state.get(state.parent_id)
        return parent.name if parent else "none"

    def _state_type_label(self, state) -> str:
        if state.is_final:   return "final"
        if state.is_initial: return "initial"
        return "normal"

    # ------------------------------------------------------------------
    # .h
    # ------------------------------------------------------------------

    def _write_h(self, out: str) -> None:
        fname = f"{self._verify_name}.h"
        guard = self._hsm_name_up + "_HSM_VERIFY_H_"

        with open(os.path.join(out, fname), "w", encoding="utf-8") as f:
            f.write(f"/* Auto-generated verification header for {self._hsm_decorated} */\n")
            f.write(f"#ifndef {guard}\n#define {guard}\n\n")
            f.write("/* Prints the full state machine model to stdout. */\n")
            f.write(f"void {self._verify_name}_print(void);\n\n")
            f.write(f"#endif /* {guard} */\n")

    # ------------------------------------------------------------------
    # .c
    # ------------------------------------------------------------------

    def _write_c(self, out: str) -> None:
        fname = f"{self._verify_name}.c"

        all_states    = self._sm.states
        normal_count  = sum(1 for s in all_states if not s.is_initial and not s.is_final)
        initial_count = sum(1 for s in all_states if s.is_initial)
        final_count   = sum(1 for s in all_states if s.is_final)
        trans_count   = sum(len(s.transitions) for s in all_states)
        trig_count    = len(self._sm.triggers)
        state_count   = len(all_states)

        with open(os.path.join(out, fname), "w", encoding="utf-8") as f:
            f.write(f"/* Auto-generated verification file for {self._hsm_decorated} */\n")
            f.write(f'#include "{self._verify_name}.h"\n')
            f.write("#include <stdio.h>\n\n")

            # ----------------------------------------------------------
            # print function
            # ----------------------------------------------------------
            f.write(f"void {self._verify_name}_print(void)\n{{\n")

            # Config ---------------------------------------------------
            f.write('    printf("\\n=== CONFIG ===\\n");\n')
            f.write(f'    printf("  name        : {self._c_safe(self._hsm_name)}\\n");\n')
            f.write(f'    printf("  loop_time   : {self._c_safe(self._config.loop_time)}\\n");\n')
            f.write(f'    printf("  event_prefix: {self._c_safe(self._config.event_prefix or "(none)")}\\n");\n')
            f.write(f'    printf("  state_prefix: {self._c_safe(self._config.state_prefix or "(none)")}\\n");\n')
            f.write(f'    printf("  author      : {self._c_safe(self._config.author)}\\n");\n')
            f.write(f'    printf("  date        : {self._c_safe(self._config.modified_date)}\\n");\n')
            f.write(f'    printf("  output path : {self._c_safe(self._config.path)}\\n");\n')
            f.write("\n")

            # Triggers -------------------------------------------------
            f.write(f'    printf("\\n=== TRIGGERS ({trig_count}) ===\\n");\n')
            for i, t in enumerate(self._sm.triggers):
                f.write(
                    f'    printf("  [{i:>2}] name={self._c_safe(t.name):<40s}'
                    f' type={self._c_safe(t.trigger_type):<15s}'
                    f' value={t.value}\\n");\n'
                )
            f.write("\n")

            # States ---------------------------------------------------
            f.write(f'    printf("\\n=== STATES ({state_count}) ===\\n");\n')

            for i, s in enumerate(all_states):
                parent_name = self._c_safe(self._parent_name(s))
                stype       = self._state_type_label(s)
                entry_s     = self._c_safe(s.entry or "none")
                exit_s      = self._c_safe(s.exit  or "none")
                do_s        = self._c_safe(s.do    or "none")

                f.write(f'    printf("\\n  [{i:>2}] {self._c_safe(s.name)}\\n");\n')
                f.write(f'    printf("        type   : {stype}\\n");\n')
                f.write(f'    printf("        parent : {parent_name}\\n");\n')
                f.write(f'    printf("        entry  : {entry_s}\\n");\n')
                f.write(f'    printf("        exit   : {exit_s}\\n");\n')
                f.write(f'    printf("        do     : {do_s}\\n");\n')

                if s.transitions:
                    f.write(f'    printf("        transitions ({len(s.transitions)}):\\n");\n')
                    for j, tr in enumerate(s.transitions):
                        target      = self._id_to_state.get(tr.target_id)
                        target_name = self._c_safe(target.name if target else str(tr.target_id))
                        events_str  = self._c_safe(", ".join(tr.events) if tr.events else "completion")
                        guard_s     = self._c_safe(tr.guard  or "none")
                        action_s    = self._c_safe(tr.action or "none")

                        f.write(
                            f'    printf("          T{j}: events=[{events_str}]'
                            f'  guard={guard_s}  action={action_s}'
                            f'  -> {target_name}\\n");\n'
                        )
                else:
                    f.write(f'    printf("        transitions: none\\n");\n')

            f.write("\n")

            # Summary --------------------------------------------------
            f.write('    printf("\\n=== SUMMARY ===\\n");\n')
            f.write(f'    printf("  Total states     : {state_count} ({normal_count} normal, {initial_count} initial, {final_count} final)\\n");\n')
            f.write(f'    printf("  Total transitions: {trans_count}\\n");\n')
            f.write(f'    printf("  Total triggers   : {trig_count}\\n");\n')
            f.write('    printf("\\n");\n')

            f.write("}\n\n")

            # ----------------------------------------------------------
            # main() — compile standalone with -DVERIFY_MAIN
            # ----------------------------------------------------------
            f.write("#ifdef VERIFY_MAIN\n")
            f.write("#include <stdlib.h>\n")
            f.write("int main(void)\n{\n")
            f.write(f"    {self._verify_name}_print();\n")
            f.write("    return EXIT_SUCCESS;\n")
            f.write("}\n")
            f.write("#endif /* VERIFY_MAIN */\n")

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def generate(self) -> None:
        out = self._config.path
        os.makedirs(out, exist_ok=True)

        self._write_h(out)
        self._write_c(out)

        print(f"Generated: {self._verify_name}.c / {self._verify_name}.h")
        print(f"Output:    {out}")
        print(f"Compile:   gcc -DVERIFY_MAIN {self._verify_name}.c -o verify && ./verify")