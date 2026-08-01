"""Tests for lint_schematic_design_rules (经验.md-derived checks)."""
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from commands.schematic_lint import SchematicLintCommands  # noqa: E402

_U = lambda: str(uuid.uuid4())


def _sch(tmp_path, body: str) -> Path:
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
    return f


def _run(path, rules=None):
    params = {"schematicPath": str(path)}
    if rules is not None:
        params["rules"] = rules
    return SchematicLintCommands().lint_schematic_design_rules(params)


def _rules_of(result):
    return {v["rule"] for v in result["violations"]}


def test_requires_path():
    assert SchematicLintCommands().lint_schematic_design_rules({})["success"] is False


def test_unknown_rule_rejected(tmp_path):
    f = _sch(tmp_path, "")
    res = _run(f, rules=["bogus"])
    assert res["success"] is False
    assert "bogus" in res["message"]


def test_value_missing_detected(tmp_path):
    body = f'''  (symbol (lib_id "Device:R") (at 100 100 0) (unit 1)
    (uuid "{_U()}")
    (property "Reference" "R1" (at 100 100 0))
    (property "Value" "?" (at 100 100 0))
  )'''
    f = _sch(tmp_path, body)
    res = _run(f, rules=["value_missing"])
    assert res["success"] is True
    assert any(v["rule"] == "value_missing" and v["reference"] == "R1" for v in res["violations"])


def test_value_present_not_flagged(tmp_path):
    body = f'''  (symbol (lib_id "Device:R") (at 100 100 0) (unit 1)
    (uuid "{_U()}")
    (property "Reference" "R1" (at 100 100 0))
    (property "Value" "10k" (at 100 100 0))
  )'''
    f = _sch(tmp_path, body)
    res = _run(f, rules=["value_missing"])
    assert res["success"] is True
    assert res["violations"] == []


def test_power_naming_multi_alias(tmp_path):
    body = f'''  (label "3V3" (at 50 50 0))
  (label "VCC33" (at 60 60 0))'''
    f = _sch(tmp_path, body)
    res = _run(f, rules=["power_naming"])
    assert res["success"] is True
    assert any(v["rule"] == "power_naming" and v["severity"] == "error" for v in res["violations"])


def test_power_naming_single_ok(tmp_path):
    body = '  (label "3V3" (at 50 50 0))'
    f = _sch(tmp_path, body)
    res = _run(f, rules=["power_naming"])
    assert res["violations"] == []


def test_junction_missing_at_crossing(tmp_path):
    # Two wires crossing at (100,100), no junction dot.
    body = '''  (wire (pts (xy 50 100) (xy 150 100)))
  (wire (pts (xy 100 50) (xy 100 150)))'''
    f = _sch(tmp_path, body)
    res = _run(f, rules=["junction"])
    assert res["success"] is True
    assert any(v["rule"] == "junction" for v in res["violations"])


def test_junction_present_at_crossing_ok(tmp_path):
    body = '''  (wire (pts (xy 50 100) (xy 150 100)))
  (wire (pts (xy 100 50) (xy 100 150)))
  (junction (at 100 100))'''
    f = _sch(tmp_path, body)
    res = _run(f, rules=["junction"])
    assert res["violations"] == []


def test_decoupling_missing_for_ic(tmp_path):
    body = f'''  (symbol (lib_id "MCU_STM32:STM32F103C8") (at 100 100 0) (unit 1)
    (uuid "{_U()}")
    (property "Reference" "U1" (at 100 100 0))
    (property "Value" "STM32F103C8" (at 100 100 0))
  )'''
    f = _sch(tmp_path, body)
    res = _run(f, rules=["decoupling"])
    assert any(v["rule"] == "decoupling" and v["reference"] == "U1" for v in res["violations"])


def test_decoupling_present_ok(tmp_path):
    body = f'''  (symbol (lib_id "MCU_STM32:STM32F103C8") (at 100 100 0) (unit 1)
    (uuid "{_U()}")
    (property "Reference" "U1" (at 100 100 0))
    (property "Value" "STM32F103C8" (at 100 100 0))
  )
  (symbol (lib_id "Device:C") (at 105 100 0) (unit 1)
    (uuid "{_U()}")
    (property "Reference" "C1" (at 105 100 0))
    (property "Value" "100nF" (at 105 100 0))
  )'''
    f = _sch(tmp_path, body)
    res = _run(f, rules=["decoupling"])
    assert res["violations"] == []


def test_interface_i2c_no_pullup(tmp_path):
    body = '''  (label "SDA" (at 50 50 0))
  (label "SCL" (at 60 60 0))'''
    f = _sch(tmp_path, body)
    res = _run(f, rules=["interface"])
    assert any(v["rule"] == "interface" and "I2C" in v["message"] for v in res["violations"])


def test_flow_direction_power_below_gnd(tmp_path):
    # power at y=120 (lower), gnd at y=80 (higher) -> power below gnd -> info
    body = '''  (label "VCC" (at 50 120 0))
  (label "GND" (at 50 80 0))'''
    f = _sch(tmp_path, body)
    res = _run(f, rules=["flow_direction"])
    assert any(v["rule"] == "flow_direction" for v in res["violations"])


def test_annotation_missing_for_key_net(tmp_path):
    body = '  (label "VCC" (at 50 50 0))'
    f = _sch(tmp_path, body)
    res = _run(f, rules=["annotation"])
    assert any(v["rule"] == "annotation" and v["reference"] == "VCC" for v in res["violations"])


def test_annotation_present_ok(tmp_path):
    body = '''  (label "VCC" (at 50 50 0))
  (text "5V/2A" (at 50 50 0))'''
    f = _sch(tmp_path, body)
    res = _run(f, rules=["annotation"])
    assert res["violations"] == []


def test_summary_counts(tmp_path):
    body = f'''  (symbol (lib_id "Device:R") (at 100 100 0) (unit 1)
    (uuid "{_U()}")
    (property "Reference" "R1" (at 100 100 0))
    (property "Value" "?" (at 100 100 0))
  )'''
    f = _sch(tmp_path, body)
    res = _run(f, rules=["value_missing"])
    assert res["summary"]["total"] == 1
    assert res["summary"]["by_rule"]["value_missing"] == 1
