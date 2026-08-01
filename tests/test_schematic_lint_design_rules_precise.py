"""Tests for the precise variants of lint_schematic_design_rules."""
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from commands.schematic_lint import SchematicLintCommands  # noqa: E402

_U = lambda: str(uuid.uuid4())


def _sch_with_ic(tmp_path, ic_lib_id: str, pins: list, instance: str,
                 extra_body: str = "") -> Path:
    """Build a schematic with a lib_symbol definition + one placed instance.

    pins: list of (number, type, name, lib_x, lib_y) tuples.
    instance: S-expression body for the placed symbol (with Reference/Value).
    """
    pin_sexps = "\n".join(
        f'      (pin {ptype} line (at {lx} {ly} 0) (length 2) (name "{pname}") (number "{pnum}"))'
        for pnum, ptype, pname, lx, ly in pins
    )
    lib_name = ic_lib_id.split(":")[-1]
    content = textwrap.dedent(f"""\
        (kicad_sch (version 20260306) (generator "test") (generator_version "10.0")
          (uuid "{_U()}")
          (paper "A4")
          (lib_symbols
            (symbol "{ic_lib_id}"
              (in_bom yes)
              (on_board yes)
              (symbol "{lib_name}_1_1"
{pin_sexps}
              )
            )
          )
        {instance}
        {extra_body}
          (sheet_instances
            (path "/" (page "1"))
          )
        )
    """)
    f = tmp_path / "t.kicad_sch"
    f.write_text(content, encoding="utf-8")
    return f


def _run(path, rules):
    return SchematicLintCommands().lint_schematic_design_rules(
        {"schematicPath": str(path), "rules": rules}
    )


def test_decoupling_precise_flags_missing_cap(tmp_path):
    ic = "MCU_ST_STM32:STM32F103C8"
    pins = [("1", "power_in", "VCC", -10, 0), ("2", "power_in", "VDD", 10, 0)]
    inst = f'''  (symbol (lib_id "{ic}") (at 100 100 0) (unit 1)
    (uuid "{_U()}")
    (property "Reference" "U1" (at 100 100 0))
    (property "Value" "STM32F103C8" (at 100 100 0))
  )'''
    f = _sch_with_ic(tmp_path, ic, pins, inst)
    res = _run(f, ["decoupling_precise"])
    assert res["success"] is True
    rules_found = {v["rule"] for v in res["violations"]}
    assert "decoupling_precise" in rules_found
    # Should reference a power pin of U1
    assert any(v["reference"].startswith("U1.") for v in res["violations"])


def test_decoupling_precise_ok_with_local_cap(tmp_path):
    ic = "MCU_ST_STM32:STM32F103C8"
    pins = [("1", "power_in", "VCC", -10, 0)]
    inst = f'''  (symbol (lib_id "{ic}") (at 100 100 0) (unit 1)
    (uuid "{_U()}")
    (property "Reference" "U1" (at 100 100 0))
    (property "Value" "STM32F103C8" (at 100 100 0))
  )'''
    # VCC pin world coords ~ (90, 100); place C1 within 10mm.
    cap = f'''  (symbol (lib_id "Device:C") (at 92 100 0) (unit 1)
    (uuid "{_U()}")
    (property "Reference" "C1" (at 92 100 0))
    (property "Value" "100nF" (at 92 100 0))
  )'''
    f = _sch_with_ic(tmp_path, ic, pins, inst, extra_body=cap)
    res = _run(f, ["decoupling_precise"])
    assert res["success"] is True
    assert res["violations"] == []


def test_decoupling_precise_ignores_passive_pins(tmp_path):
    ic = "MCU_ST_STM32:STM32F103C8"
    # Only passive pins — should not be flagged as power pins.
    pins = [("1", "passive", "P1", -10, 0)]
    inst = f'''  (symbol (lib_id "{ic}") (at 100 100 0) (unit 1)
    (uuid "{_U()}")
    (property "Reference" "U1" (at 100 100 0))
    (property "Value" "STM32F103C8" (at 100 100 0))
  )'''
    f = _sch_with_ic(tmp_path, ic, pins, inst)
    res = _run(f, ["decoupling_precise"])
    assert res["success"] is True
    assert res["violations"] == []


def test_flow_direction_precise_flags_input_on_right(tmp_path):
    ic = "MCU_ST_STM32:STM32F103C8"
    # input pin on the RIGHT of the body (lib x = +10) -> world x > centroid -> flag.
    pins = [("1", "input", "IN1", 10, 0)]
    inst = f'''  (symbol (lib_id "{ic}") (at 100 100 0) (unit 1)
    (uuid "{_U()}")
    (property "Reference" "U1" (at 100 100 0))
    (property "Value" "STM32F103C8" (at 100 100 0))
  )'''
    f = _sch_with_ic(tmp_path, ic, pins, inst)
    res = _run(f, ["flow_direction_precise"])
    assert res["success"] is True
    assert any(v["rule"] == "flow_direction_precise" and v["reference"].startswith("U1.")
               for v in res["violations"])


def test_flow_direction_precise_ok_input_on_left(tmp_path):
    ic = "MCU_ST_STM32:STM32F103C8"
    # input pin on the LEFT (lib x = -10) -> world x < centroid -> OK.
    pins = [("1", "input", "IN1", -10, 0), ("2", "output", "OUT1", 10, 0)]
    inst = f'''  (symbol (lib_id "{ic}") (at 100 100 0) (unit 1)
    (uuid "{_U()}")
    (property "Reference" "U1" (at 100 100 0))
    (property "Value" "STM32F103C8" (at 100 100 0))
  )'''
    f = _sch_with_ic(tmp_path, ic, pins, inst)
    res = _run(f, ["flow_direction_precise"])
    assert res["success"] is True
    assert res["violations"] == []


def test_flow_direction_precise_flags_output_on_left(tmp_path):
    ic = "MCU_ST_STM32:STM32F103C8"
    # output pin on the LEFT (lib x = -10) -> world x < centroid -> flag.
    pins = [("1", "output", "OUT1", -10, 0)]
    inst = f'''  (symbol (lib_id "{ic}") (at 100 100 0) (unit 1)
    (uuid "{_U()}")
    (property "Reference" "U1" (at 100 100 0))
    (property "Value" "STM32F103C8" (at 100 100 0))
  )'''
    f = _sch_with_ic(tmp_path, ic, pins, inst)
    res = _run(f, ["flow_direction_precise"])
    assert res["success"] is True
    assert any(v["rule"] == "flow_direction_precise" for v in res["violations"])


def test_interface_precise_runs_without_crash(tmp_path):
    # Minimal: I2C labels present. Whether the analyser finds pull-ups depends
    # on the skip backend; we only assert the rule dispatches and returns success.
    body = '  (label "SDA" (at 50 50 0))\n  (label "SCL" (at 60 60 0))'
    content = textwrap.dedent(f"""\
        (kicad_sch (version 20260306) (generator "test") (generator_version "10.0")
          (uuid "{_U()}")
          (paper "A4")
          (lib_symbols
          )
        {body}
          (sheet_instances
            (path "/" (page "1"))
          )
        )
    """)
    f = tmp_path / "t.kicad_sch"
    f.write_text(content, encoding="utf-8")
    res = _run(f, ["interface_precise"])
    assert res["success"] is True
    # Either flags missing pull-ups (real skip) or returns info note (stub).
    for v in res["violations"]:
        assert v["rule"] == "interface_precise"


def test_all_rules_in_design_rules_constant():
    rules = SchematicLintCommands._DESIGN_RULES
    for r in ("decoupling_precise", "interface_precise", "flow_direction_precise"):
        assert r in rules
