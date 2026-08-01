"""
Unit + integration tests for schematic field-placement/layout commands.

The text S-expression helpers and the set/batch property writers are exercised against a
real minimal .kicad_sch written to a temp file (pure text manipulation — no KiCad needed).
autoplace_schematic_fields is tested for parameter validation; the geometry helpers are
unit-tested directly.
"""

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from commands.schematic_field_layout import (  # noqa: E402
    SchematicFieldLayoutCommands,
    _bbox_overlaps,
    _gather_components,
    _gather_labels,
)
from commands.schematic_text_utils import (  # noqa: E402
    _extract_component_properties,
    _extract_property_position,
    _extract_property_visible,
    _find_matching_paren,
    _find_placed_symbol_block,
    _get_sheet_usable_area,
    _move_property_in_block,
)

MINIMAL_SCH = """(kicad_sch (version 20230121) (paper "A4")
  (lib_symbols
    (symbol "Device:R" (property "Reference" "R" (at 0 0 0)))
  )
  (symbol (lib_id "Device:R") (at 100 100 0) (uuid "11111111")
    (property "Reference" "R1" (at 102.0 98.0 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "10k" (at 102.0 102.0 0)
      (effects (font (size 1.27 1.27))))
  )
  (symbol (lib_id "Device:C") (at 150 100 0) (uuid "22222222")
    (property "Reference" "C1" (at 152.0 98.0 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "100nF" (at 152.0 102.0 0)
      (effects (font (size 1.27 1.27))))
  )
)
"""


class TestTextHelpers:
    def test_find_matching_paren(self):
        s = "(a (b) c)"
        assert _find_matching_paren(s, 0) == len(s) - 1
        assert _find_matching_paren(s, 3) == 5

    def test_find_placed_symbol_block_skips_lib_symbols(self):
        block, start, end = _find_placed_symbol_block(MINIMAL_SCH, "R1")
        assert block is not None
        # Must be the placed instance (has lib_id + (at 100 100 0)), not the lib_symbols def
        assert '(lib_id "Device:R")' in block and "(at 100 100 0)" in block

    def test_find_placed_symbol_block_missing(self):
        assert _find_placed_symbol_block(MINIMAL_SCH, "R99") == (None, -1, -1)

    def test_extract_property_position(self):
        block, _, _ = _find_placed_symbol_block(MINIMAL_SCH, "R1")
        assert _extract_property_position(block, "Reference") == {
            "x": 102.0,
            "y": 98.0,
            "angle": 0.0,
        }

    def test_extract_property_visible(self):
        block, _, _ = _find_placed_symbol_block(MINIMAL_SCH, "R1")
        assert _extract_property_visible(block, "Reference") is True

    def test_extract_component_properties(self):
        block, _, _ = _find_placed_symbol_block(MINIMAL_SCH, "R1")
        props = _extract_component_properties(block)
        assert props["Reference"] == "R1" and props["Value"] == "10k"

    def test_move_property_in_block_and_hide(self):
        block, _, _ = _find_placed_symbol_block(MINIMAL_SCH, "R1")
        new_block, n = _move_property_in_block(block, "Reference", 105, 95, 0, visible=False)
        assert n == 1
        assert "(at 105 95 0)" in new_block
        assert "(hide yes)" in new_block
        # Re-show it
        reshown, _ = _move_property_in_block(new_block, "Reference", 105, 95, 0, visible=True)
        assert "(hide yes)" not in reshown

    def test_move_property_missing(self):
        block, _, _ = _find_placed_symbol_block(MINIMAL_SCH, "R1")
        _, n = _move_property_in_block(block, "Footprint", 1, 2, 0, True)
        assert n == 0


class TestGeometryHelpers:
    def test_bbox_overlaps(self):
        a = {"x_min": 0, "y_min": 0, "x_max": 10, "y_max": 10}
        b = {"x_min": 5, "y_min": 5, "x_max": 15, "y_max": 15}
        c = {"x_min": 20, "y_min": 20, "x_max": 30, "y_max": 30}
        assert _bbox_overlaps(a, b)
        assert not _bbox_overlaps(a, c)
        assert _bbox_overlaps(a, c, margin=11)  # margin bridges the gap

    def test_get_sheet_usable_area_default_a4(self, tmp_path):
        f = tmp_path / "a4.kicad_sch"
        f.write_text('(kicad_sch (paper "A4")')
        left, top, right, bottom = _get_sheet_usable_area(str(f))
        assert (left, top) == (12.7, 12.7)
        assert right == pytest.approx(297.0 - 12.7)
        assert bottom == pytest.approx(210.0 - 12.7)

    def test_get_sheet_usable_area_a3(self, tmp_path):
        f = tmp_path / "a3.kicad_sch"
        f.write_text('(kicad_sch (paper "A3")')
        _, _, right, _ = _get_sheet_usable_area(str(f))
        assert right == pytest.approx(420.0 - 12.7)

    def test_gather_labels(self):
        def lbl(v, at):
            return types.SimpleNamespace(value=v, at=types.SimpleNamespace(value=at))

        sch = types.SimpleNamespace(
            label=[lbl("SDA", [1, 2, 0])], global_label=[lbl("VBUS", [3, 4, 90])]
        )
        labels = _gather_labels(sch)
        assert {x["name"] for x in labels} == {"SDA", "VBUS"}
        vbus = next(x for x in labels if x["name"] == "VBUS")
        assert vbus["type"] == "global" and vbus["angle"] == 90.0


class TestSetPropertyPosition:
    def _sch(self, tmp_path):
        f = tmp_path / "x.kicad_sch"
        f.write_text(MINIMAL_SCH)
        return f

    def test_missing_params(self):
        c = SchematicFieldLayoutCommands()
        assert (
            c.set_schematic_property_position({"schematicPath": "/x", "reference": "R1"})["success"]
            is False
        )

    def test_rejects_non_ref_value(self, tmp_path):
        f = self._sch(tmp_path)
        c = SchematicFieldLayoutCommands()
        r = c.set_schematic_property_position(
            {"schematicPath": str(f), "reference": "R1", "property": "Footprint", "x": 1, "y": 2}
        )
        assert r["success"] is False

    def test_moves_field(self, tmp_path):
        f = self._sch(tmp_path)
        c = SchematicFieldLayoutCommands()
        r = c.set_schematic_property_position(
            {"schematicPath": str(f), "reference": "R1", "property": "Reference", "x": 105, "y": 95}
        )
        assert r["success"] is True
        content = f.read_text()
        assert '(property "Reference" "R1" (at 105 95 0)' in content
        # C1 left untouched
        assert '(property "Reference" "C1" (at 152.0 98.0 0)' in content

    def test_component_not_found(self, tmp_path):
        f = self._sch(tmp_path)
        c = SchematicFieldLayoutCommands()
        r = c.set_schematic_property_position(
            {"schematicPath": str(f), "reference": "R99", "property": "Value", "x": 1, "y": 2}
        )
        assert r["success"] is False


class TestBatchSetPropertyPositions:
    def test_batch_applies_and_reports(self, tmp_path):
        f = tmp_path / "x.kicad_sch"
        f.write_text(MINIMAL_SCH)
        c = SchematicFieldLayoutCommands()
        r = c.batch_set_schematic_property_positions(
            {
                "schematicPath": str(f),
                "updates": [
                    {"reference": "R1", "property": "Reference", "x": 90, "y": 90},
                    {"reference": "C1", "property": "Value", "x": 160, "y": 110},
                    {"reference": "R99", "property": "Value", "x": 0, "y": 0},  # should fail
                ],
            }
        )
        assert r["applied_count"] == 2
        assert r["failed_count"] == 1
        assert r["success"] is False  # because one failed
        content = f.read_text()
        assert '(property "Reference" "R1" (at 90 90 0)' in content
        assert '(property "Value" "100nF" (at 160 110 0)' in content

    def test_requires_updates(self, tmp_path):
        f = tmp_path / "x.kicad_sch"
        f.write_text(MINIMAL_SCH)
        c = SchematicFieldLayoutCommands()
        assert (
            c.batch_set_schematic_property_positions({"schematicPath": str(f)})["success"] is False
        )


class TestAutoplaceValidation:
    def test_autoplace_requires_path(self):
        assert SchematicFieldLayoutCommands().autoplace_schematic_fields({})["success"] is False


# ---------------------------------------------------------------------------
# P0-b: graphics-aware body bbox (union of body graphics + pin envelope)
# ---------------------------------------------------------------------------

import sexpdata as _sexpdata
import uuid as _uuid

from commands.pin_locator import PinLocator  # noqa: E402
from commands.schematic import SchematicManager  # noqa: E402

# A wide-body IC whose rectangle body (±5 X, ±3 Y) is larger than its pin
# envelope (pins at ±2.54 X, ±1.27 Y → envelope ±3.81 X, ±2.54 Y). Under the
# legacy pin-only bbox the body rectangle would be missed and autoplace could
# drop Ref/Value onto the body; with graphics-aware bbox the rectangle extent
# must dominate.
_WIDE_IC_LIB_SYMBOL = """
    (symbol "Test:WideIC" (pin_numbers hide) (pin_names (offset 0)) (in_bom yes) (on_board yes)
      (property "Reference" "U" (at 0 5.08 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Value" "WideIC" (at 0 -5.08 0)
        (effects (font (size 1.27 1.27)))
      )
      (property "Footprint" "" (at 0 0 0)
        (effects (font (size 1.27 1.27)) hide)
      )
      (property "Datasheet" "~" (at 0 0 0)
        (effects (font (size 1.27 1.27)) hide)
      )
      (symbol "WideIC_0_1"
        (rectangle (start -5 -3) (end 5 3)
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
      )
      (symbol "WideIC_1_1"
        (pin passive line (at -2.54 -1.27 0) (length 1.27)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at -2.54 1.27 0) (length 1.27)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 2.54 -1.27 180) (length 1.27)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "3" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 2.54 1.27 180) (length 1.27)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "4" (effects (font (size 1.27 1.27))))
        )
      )
    )
"""


def _make_wide_ic_sch(
    tmp_path, x=100.0, y=100.0, rotation=0.0, mirror=None,
    ref_y_offset=5.08, ref_do_not_autoplace=False,
):
    """Build a .kicad_sch with one placed Test:WideIC instance."""
    mirror_tok = f"(mirror {mirror})" if mirror else ""
    dna_tok = "      (do_not_autoplace yes)\n" if ref_do_not_autoplace else ""
    content = f'''(kicad_sch (version 20260306) (generator "test") (generator_version "10.0")
  (uuid "{_uuid.uuid4()}")
  (paper "A4")
  (lib_symbols
{_WIDE_IC_LIB_SYMBOL}
  )
  (symbol (lib_id "Test:WideIC") (at {x} {y} {rotation}){mirror_tok} (unit 1)
    (in_bom yes) (on_board yes) (dnp no)
    (uuid "{_uuid.uuid4()}")
    (property "Reference" "U1" (at {x} {y + ref_y_offset} 0)
      (effects (font (size 1.27 1.27)))
{dna_tok}    )
    (property "Value" "WideIC" (at {x} {y - 5.08} 0)
      (effects (font (size 1.27 1.27)))
    )
    (property "Footprint" "" (at {x} {y} 0)
      (effects (font (size 1.27 1.27)) hide)
    )
    (property "Datasheet" "~" (at {x} {y} 0)
      (effects (font (size 1.27 1.27)) hide)
    )
    (pin "1" (uuid "{_uuid.uuid4()}"))
    (pin "2" (uuid "{_uuid.uuid4()}"))
    (pin "3" (uuid "{_uuid.uuid4()}"))
    (pin "4" (uuid "{_uuid.uuid4()}"))
    (instances
      (project "test"
        (path "/" (reference "U1") (unit 1))
      )
    )
  )
  (sheet_instances
    (path "/" (page "1"))
  )
)
'''
    f = tmp_path / "wide_ic.kicad_sch"
    f.write_text(content, encoding="utf-8")
    return f


class TestGatherComponentsGraphicsBbox:
    """P0-b: _gather_components must use body graphics bbox unioned with pin envelope."""

    def test_wide_ic_bbox_uses_graphics(self, tmp_path):
        f = _make_wide_ic_sch(tmp_path)
        schematic = SchematicManager.load_schematic(str(f))
        raw = f.read_text(encoding="utf-8")
        sexp_data = _sexpdata.loads(raw)
        comps = _gather_components(schematic, f, raw, PinLocator(), sexp_data=sexp_data)
        u1 = [c for c in comps if c["reference"] == "U1"][0]
        assert "body_bbox" in u1
        bb = u1["body_bbox"]
        # Rectangle ±5 X, ±3 Y dominates over pin envelope (±3.81 X, ±2.54 Y)
        assert bb["x_min"] == pytest.approx(100 - 5, abs=0.05)
        assert bb["x_max"] == pytest.approx(100 + 5, abs=0.05)
        assert bb["y_min"] == pytest.approx(100 - 3, abs=0.05)
        assert bb["y_max"] == pytest.approx(100 + 3, abs=0.05)

    def test_wide_ic_bbox_legacy_without_sexp(self, tmp_path):
        """Without sexp_data, falls back to the legacy pin-only envelope."""
        f = _make_wide_ic_sch(tmp_path)
        schematic = SchematicManager.load_schematic(str(f))
        raw = f.read_text(encoding="utf-8")
        comps = _gather_components(schematic, f, raw, PinLocator())
        u1 = [c for c in comps if c["reference"] == "U1"][0]
        bb = u1["body_bbox"]
        # Pin envelope: X ±(2.54+1.27)=3.81, Y ±(1.27+1.27)=2.54
        assert bb["x_min"] == pytest.approx(100 - 3.81, abs=0.05)
        assert bb["x_max"] == pytest.approx(100 + 3.81, abs=0.05)
        assert bb["y_min"] == pytest.approx(100 - 2.54, abs=0.05)
        assert bb["y_max"] == pytest.approx(100 + 2.54, abs=0.05)

    def test_wide_ic_mirror_y_recorded(self, tmp_path):
        """P0-b配套: mirror state is captured from sexp_data."""
        f = _make_wide_ic_sch(tmp_path, mirror="y")
        schematic = SchematicManager.load_schematic(str(f))
        raw = f.read_text(encoding="utf-8")
        sexp_data = _sexpdata.loads(raw)
        comps = _gather_components(schematic, f, raw, PinLocator(), sexp_data=sexp_data)
        u1 = [c for c in comps if c["reference"] == "U1"][0]
        assert u1.get("mirror_y") is True
        assert u1.get("mirror_x") is False


# ---------------------------------------------------------------------------
# P1-c: autoplace respects (do_not_autoplace yes)
# ---------------------------------------------------------------------------


class TestAutoplaceDoNotAutoplace:
    """A field locked with (do_not_autoplace yes) must not be moved by autoplace."""

    def _prop_at(self, f, ref, prop):
        from commands.schematic_text_utils import _extract_property_position
        raw = f.read_text(encoding="utf-8")
        from commands.schematic_text_utils import _find_placed_symbol_block
        block, _, _ = _find_placed_symbol_block(raw, ref)
        return _extract_property_position(block, prop)

    def test_locked_reference_is_not_moved(self, tmp_path):
        # Reference placed inside the body (y_offset 0 → at (100,100), body spans
        # y 97..103), so autoplace would normally move it. Lock it and verify it
        # stays put while Value still gets repositioned.
        f = _make_wide_ic_sch(tmp_path, ref_y_offset=0.0, ref_do_not_autoplace=True)
        ref_before = self._prop_at(f, "U1", "Reference")
        val_before = self._prop_at(f, "U1", "Value")
        SchematicFieldLayoutCommands().autoplace_schematic_fields(
            {"schematicPath": str(f), "references": ["U1"]}
        )
        ref_after = self._prop_at(f, "U1", "Reference")
        val_after = self._prop_at(f, "U1", "Value")
        assert ref_after == ref_before, "locked Reference must not move"
        assert val_after != val_before, "Value should still be repositioned"

    def test_unlocked_reference_is_moved(self, tmp_path):
        # Same setup but without the lock: Reference inside the body must move.
        f = _make_wide_ic_sch(tmp_path, ref_y_offset=0.0, ref_do_not_autoplace=False)
        ref_before = self._prop_at(f, "U1", "Reference")
        SchematicFieldLayoutCommands().autoplace_schematic_fields(
            {"schematicPath": str(f), "references": ["U1"]}
        )
        ref_after = self._prop_at(f, "U1", "Reference")
        assert ref_after != ref_before, "unlocked Reference inside body should move"

    def test_result_includes_unresolved_key(self, tmp_path):
        # The autoplace result must always carry an "unresolved" list (possibly
        # empty) so callers can detect components that could not be placed
        # without collision even after growing the clearance.
        f = _make_wide_ic_sch(tmp_path)
        res = SchematicFieldLayoutCommands().autoplace_schematic_fields(
            {"schematicPath": str(f), "references": ["U1"]}
        )
        assert res["success"] is True
        assert "unresolved" in res
        assert isinstance(res["unresolved"], list)


# ---------------------------------------------------------------------------
# P0-a + P0-b + P1-a integration: rotate a wide-body IC, then autoplace
# ---------------------------------------------------------------------------

class TestRotateThenAutoplaceWideIC:
    """End-to-end: rotate a wide-body IC 90°, recompute fields (P0-a), then
    autoplace (P1-a) using the graphics-aware body bbox (P0-b). The fields
    must end up outside the rotated body (no field_on_own_body overlap)."""

    def test_rotate_90_then_autoplace_no_field_on_body(self, tmp_path):
        import sexpdata as _sex
        from utils.sexpr_format import dumps as kicad_dumps
        from commands.schematic_analysis import find_overlapping_elements
        from commands.wire_dragger import WireDragger

        # Place a wide-body IC at rotation=0, then rotate it 90° in-place.
        f = _make_wide_ic_sch(tmp_path, x=100.0, y=100.0, rotation=0.0)
        sch = _sex.loads(f.read_text(encoding="utf-8"))
        ok = WireDragger.update_symbol_rotation_mirror(sch, "U1", 90.0, None)
        assert ok is True
        f.write_text(kicad_dumps(sch), encoding="utf-8")

        # Now run the neighbourhood-aware autoplace.
        ap = SchematicFieldLayoutCommands().autoplace_schematic_fields(
            {"schematicPath": str(f), "references": ["U1"]}
        )
        assert ap["success"] is True

        # After autoplace, no visible field should overlap its own body.
        overlaps = find_overlapping_elements(f)
        own = [
            o for o in overlaps["overlappingFields"]
            if o.get("type") == "field_on_own_body" and o.get("reference") == "U1"
        ]
        assert own == [], f"U1 field still on body after autoplace: {own}"
