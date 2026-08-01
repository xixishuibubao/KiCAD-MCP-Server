"""
Tests for rotate_schematic_component mirror/rotation fix.

Tests are split into two layers:
 1. WireDragger unit tests — pure sexpdata logic, no KiCAD deps.
 2. Handler integration smoke test — patches SchematicManager away.
"""

import importlib.util
import math
import os
import sys
import tempfile
import textwrap
from unittest.mock import MagicMock, patch

import sexpdata
from sexpdata import Symbol

# ---------------------------------------------------------------------------
# Import WireDragger directly (no pcbnew / kicad_interface needed)
# ---------------------------------------------------------------------------
_wd_spec = importlib.util.spec_from_file_location(
    "wire_dragger",
    os.path.join(os.path.dirname(__file__), "..", "python", "commands", "wire_dragger.py"),
)
_wd_mod = importlib.util.module_from_spec(_wd_spec)

# wire_dragger imports pin_locator lazily inside get_pin_defs.
# We stub only the submodule, not the parent package, so that
# kicad_interface can still import commands.board etc. from disk.
_pin_locator_mock = MagicMock()
_had_real_pin_locator = "commands.pin_locator" in sys.modules
sys.modules.setdefault("commands.pin_locator", _pin_locator_mock)

_wd_spec.loader.exec_module(_wd_mod)
WireDragger = _wd_mod.WireDragger

# Immediately remove the throwaway pin_locator mock. wire_dragger imports
# pin_locator lazily (inside get_pin_defs), so the mock is no longer needed
# once wire_dragger is loaded. Leaving it in sys.modules would leak into
# later-collected modules (e.g. test_schematic_analysis) which import the
# real commands.pin_locator and would silently get this mock instead (#287).
if not _had_real_pin_locator and sys.modules.get("commands.pin_locator") is _pin_locator_mock:
    del sys.modules["commands.pin_locator"]


def teardown_module(module: object) -> None:
    """Undo the module-level ``commands.pin_locator`` stub above.

    The mock is already removed right after wire_dragger was loaded above; this
    teardown is kept as a defensive no-op in case a future change re-introduces
    a leak.
    """
    if not _had_real_pin_locator and sys.modules.get("commands.pin_locator") is _pin_locator_mock:
        del sys.modules["commands.pin_locator"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(text: str) -> list:
    return sexpdata.loads(text)


def _dump(data: list) -> str:
    return sexpdata.dumps(data)


def _make_sch(sym_extra: str = "", wires: str = "") -> list:
    """Build a minimal schematic sexpdata with one Q1 symbol."""
    text = textwrap.dedent(f"""\
        (kicad_sch (version 20250114) (generator "test")
          (lib_symbols
            (symbol "Transistor_BJT:MMBT3904"
              (pin passive line (at 0.0 1.0 270) (length 1.27)
                (name "B" (effects (font (size 1.27 1.27))))
                (number "1" (effects (font (size 1.27 1.27))))
              )
              (pin passive line (at -1.0 0.0 0) (length 1.27)
                (name "C" (effects (font (size 1.27 1.27))))
                (number "2" (effects (font (size 1.27 1.27))))
              )
            )
          )
          (symbol (lib_id "Transistor_BJT:MMBT3904")
                  (at 75 105 0)
                  {sym_extra}
                  (property "Reference" "Q1" (at 75 105 0))
                  (property "Value" "MMBT3904" (at 75 105 0))
          )
          {wires}
        )
    """)
    return _parse(text)


# ---------------------------------------------------------------------------
# Tests: update_symbol_rotation_mirror
# ---------------------------------------------------------------------------


def test_update_rotation_sets_angle():
    sch = _make_sch()
    result = WireDragger.update_symbol_rotation_mirror(sch, "Q1", 90.0, None)
    assert result is True
    dumped = _dump(sch)
    # at should now have 90 as the rotation value
    assert "90" in dumped


def test_update_mirror_x_adds_token():
    sch = _make_sch()
    WireDragger.update_symbol_rotation_mirror(sch, "Q1", 0.0, "x")
    dumped = _dump(sch)
    assert "mirror" in dumped
    assert " x" in dumped or "(mirror x)" in dumped


def test_update_mirror_y_adds_token():
    sch = _make_sch()
    WireDragger.update_symbol_rotation_mirror(sch, "Q1", 0.0, "y")
    dumped = _dump(sch)
    assert "mirror" in dumped


def test_update_mirror_none_removes_existing():
    """mirror=None should remove a pre-existing (mirror x) token."""
    sch = _make_sch(sym_extra="(mirror x)")
    WireDragger.update_symbol_rotation_mirror(sch, "Q1", 0.0, None)
    dumped = _dump(sch)
    assert "mirror" not in dumped


def test_update_mirror_replaces_existing():
    """Setting mirror='y' when (mirror x) exists should replace, not duplicate."""
    sch = _make_sch(sym_extra="(mirror x)")
    WireDragger.update_symbol_rotation_mirror(sch, "Q1", 0.0, "y")
    dumped = _dump(sch)
    assert dumped.count("mirror") == 1


def test_update_unknown_reference_returns_false():
    sch = _make_sch()
    result = WireDragger.update_symbol_rotation_mirror(sch, "U99", 0.0, "x")
    assert result is False


# ---------------------------------------------------------------------------
# Tests: compute_pin_positions_for_rotation
# ---------------------------------------------------------------------------


def test_pin_positions_change_on_rotation():
    """Pins at non-zero local offsets should move when the symbol rotates."""
    sch = _make_sch()

    # Provide a real pin_defs via patch so we don't need KiCAD libs
    fake_pins = {
        "1": {"x": 0.0, "y": 1.0},
        "2": {"x": -1.0, "y": 0.0},
    }
    with patch.object(WireDragger, "get_pin_defs", return_value=fake_pins):
        pos = WireDragger.compute_pin_positions_for_rotation(sch, "Q1", 90.0, False, False)

    assert len(pos) == 2
    for pin_num, (old_xy, new_xy) in pos.items():
        # After 90° rotation the positions must differ (pins not at origin)
        assert old_xy != new_xy, f"Pin {pin_num} should have moved"


def test_pin_positions_unchanged_at_same_transform():
    """Same rotation and same mirror → no movement."""
    sch = _make_sch()  # symbol at rotation=0, no mirror

    fake_pins = {"1": {"x": 1.0, "y": 0.0}}
    with patch.object(WireDragger, "get_pin_defs", return_value=fake_pins):
        pos = WireDragger.compute_pin_positions_for_rotation(sch, "Q1", 0.0, False, False)

    for _, (old_xy, new_xy) in pos.items():
        assert old_xy == new_xy


def test_pin_positions_mirror_x_flips_y():
    """mirror_x = SYM_MIRROR_X = TRANSFORM(1,0,0,-1) negates the screen-Y
    coordinate (eeschema symbol.h:43-44), not X. With the lib→screen Y-flip
    applied first, this means the pin's screen Y is reflected back to lib Y."""
    sch = _make_sch()  # at (75, 105, 0), no mirror

    fake_pins = {"1": {"x": 0.0, "y": 2.0}}
    with patch.object(WireDragger, "get_pin_defs", return_value=fake_pins):
        pos = WireDragger.compute_pin_positions_for_rotation(sch, "Q1", 0.0, True, False)

    _, (old_xy, new_xy) = next(iter(pos.items()))
    # old: pin at lib (0, 2). Y-flip → (0, -2). No mirror. World = (75, 105-2) = (75, 103).
    assert abs(old_xy[1] - 103.0) < 1e-4
    # new: mirror_x → negate screen-Y → (0, 2). World = (75, 105+2) = (75, 107).
    assert abs(new_xy[1] - 107.0) < 1e-4


# ---------------------------------------------------------------------------
# Integration smoke test: handler uses sexpdata, not kicad-skip
# ---------------------------------------------------------------------------


def test_rotate_handler_no_crash(tmp_path):
    """_handle_rotate_schematic_component should succeed without kicad-skip."""
    # Ensure python/ is on sys.path so commands.* imports resolve
    _python_dir = os.path.join(os.path.dirname(__file__), "..", "python")
    if _python_dir not in sys.path:
        sys.path.insert(0, _python_dir)

    # Stub heavy imports before loading kicad_interface. Save and restore
    # sys.modules state so we don't pollute already-imported real modules
    # (notably schemas.tool_schemas, whose TOOL_SCHEMAS dict is shared across
    # the test session).
    _stub_modnames = (
        "pcbnew",
        "skip",
        "resources",
        "schemas",
        "resources.resource_definitions",
        "schemas.tool_schemas",
        "annotations",
    )
    _saved_modules = {n: sys.modules.get(n) for n in _stub_modnames}
    _modules_before = set(sys.modules)
    try:
        for modname in _stub_modnames:
            sys.modules[modname] = MagicMock()
        sys.modules["resources.resource_definitions"].RESOURCE_DEFINITIONS = {}
        sys.modules["resources.resource_definitions"].handle_resource_read = MagicMock()
        sys.modules["schemas.tool_schemas"].TOOL_SCHEMAS = []

        _pcbnew = sys.modules["pcbnew"]
        _pcbnew.__file__ = "/fake/pcbnew.so"
        _pcbnew.GetBuildVersion.return_value = "9.0.0"

        ki_spec = importlib.util.spec_from_file_location(
            "kicad_interface_smoke",
            os.path.join(os.path.dirname(__file__), "..", "python", "kicad_interface.py"),
        )
        ki_mod = importlib.util.module_from_spec(ki_spec)
        ki_spec.loader.exec_module(ki_mod)
        KiCADInterface = ki_mod.KiCADInterface
    finally:
        for modname, mod in _saved_modules.items():
            if mod is None:
                sys.modules.pop(modname, None)
            else:
                sys.modules[modname] = mod

        # kicad_interface.py eagerly imports ~20 commands.* submodules, several
        # of which do `from skip import Schematic` / `import pcbnew` at their
        # own module level. Any of those imported here for the first time in
        # the whole session captured a reference to *this test's* throwaway
        # mocks — restoring sys.modules["skip"]/["pcbnew"] above doesn't fix
        # that, since the submodule already bound its own name to the mock at
        # import time. Evict any such newly-added commands.* submodule so a
        # later, unstubbed import re-executes it against the real/conftest
        # modules instead of silently keeping the stale mock reference (#287).
        # Scoped to "commands." specifically: third-party/stdlib modules
        # pulled in as a side effect (e.g. PIL's C extension) are not
        # safely re-importable and must be left alone.
        for modname in set(sys.modules) - _modules_before:
            if modname.startswith("commands."):
                sys.modules.pop(modname, None)

    # Write a minimal schematic file
    sch_path = str(tmp_path / "test.kicad_sch")
    sch_content = textwrap.dedent("""\
        (kicad_sch (version 20250114) (generator "test")
          (lib_symbols
            (symbol "Device:R"
              (pin passive line (at 0 1.016 270) (length 1.27)
                (name "~" (effects (font (size 1.27 1.27))))
                (number "1" (effects (font (size 1.27 1.27))))
              )
              (pin passive line (at 0 -1.016 90) (length 1.27)
                (name "~" (effects (font (size 1.27 1.27))))
                (number "2" (effects (font (size 1.27 1.27))))
              )
            )
          )
          (symbol (lib_id "Device:R") (at 100 100 0)
            (property "Reference" "R1" (at 100 100 0))
            (property "Value" "10k" (at 100 100 0))
          )
        )
    """)
    with open(sch_path, "w") as f:
        f.write(sch_content)

    iface = KiCADInterface.__new__(KiCADInterface)
    result = iface._handle_rotate_schematic_component(
        {
            "schematicPath": sch_path,
            "reference": "R1",
            "angle": 90,
        }
    )

    assert result["success"] is True
    assert result["angle"] == 90

    # Verify the file was actually updated
    with open(sch_path) as f:
        updated = f.read()
    assert "90" in updated


# ---------------------------------------------------------------------------
# P0-a: rotation/mirror recomputes field positions from lib defaults
# ---------------------------------------------------------------------------

import textwrap as _textwrap  # noqa: E402

from sexpdata import Symbol as _Symbol  # noqa: E402

_PROP_K = _Symbol("property")
_AT_K = _Symbol("at")
_DNA_K = _Symbol("do_not_autoplace")


def _field_at(sch, ref, prop_name):
    """Return (x, y, angle) of a placed property, or None."""
    found = WireDragger.find_symbol(sch, ref)
    if not found:
        return None
    item = found[0]
    for sub in item[1:]:
        if isinstance(sub, list) and len(sub) >= 3 and sub[0] == _PROP_K:
            if str(sub[1]).strip('"') == prop_name:
                for p in sub[1:]:
                    if isinstance(p, list) and len(p) >= 3 and p[0] == _AT_K:
                        ang = float(p[3]) if len(p) >= 4 else 0.0
                        return (float(p[1]), float(p[2]), ang)
    return None


_FIELD_SCH = _textwrap.dedent("""\
    (kicad_sch (version 20250114) (generator "test")
      (lib_symbols
        (symbol "Test:R" (pin_numbers hide) (pin_names (offset 0))
          (property "Reference" "R" (at 2.032 0 90)
            (effects (font (size 1.27 1.27))))
          (property "Value" "R" (at 0 0 90)
            (effects (font (size 1.27 1.27))))
          (symbol "R_1_1"
            (pin passive line (at 0 3.81 270) (length 1.27)
              (name "~" (effects (font (size 1.27 1.27))))
              (number "1" (effects (font (size 1.27 1.27))))
            )
          )
        )
      )
      (symbol (lib_id "Test:R") (at 100 100 0) (unit 1)
        (property "Reference" "R1" (at 102.032 100 90)
          (effects (font (size 1.27 1.27))))
        (property "Value" "10k" (at 100 100 90)
          (effects (font (size 1.27 1.27))))
      )
    )
""")


def test_rotation_recomputes_reference_field():
    """Rotating 90° must move Reference from (102.032,100,90) to (100,97.968,0)."""
    sch = _parse(_FIELD_SCH)
    assert _field_at(sch, "R1", "Reference") == (102.032, 100.0, 90.0)
    ok = WireDragger.update_symbol_rotation_mirror(sch, "R1", 90.0, None)
    assert ok is True
    ref_at = _field_at(sch, "R1", "Reference")
    assert ref_at == (100.0, 97.968, 0)


def test_rotation_recomputes_value_field():
    """Value at lib (0,0,90) stays at origin (100,100) but text angle normalises 90->90... 90+90=180->0."""
    sch = _parse(_FIELD_SCH)
    ok = WireDragger.update_symbol_rotation_mirror(sch, "R1", 90.0, None)
    assert ok is True
    assert _field_at(sch, "R1", "Value") == (100.0, 100.0, 0)


def test_field_text_angle_keepupright_270():
    """Rotating 180°: Reference lib text_ang=90 → 90+180=270 → keep-upright 90."""
    sch = _parse(_FIELD_SCH)
    WireDragger.update_symbol_rotation_mirror(sch, "R1", 180.0, None)
    # Reference lib (2.032,0,90): pin_world_xy(2.032,0,100,100,180,F,F)
    # lx,ly=2.032,0; _rotate(2.032,0,-180)=(-2.032,0); -> (97.968,100); ang=270->90
    assert _field_at(sch, "R1", "Reference") == (97.968, 100.0, 90)


def test_do_not_autoplace_field_is_skipped():
    """A property marked (do_not_autoplace yes) must not be repositioned."""
    sch = _parse(_FIELD_SCH)
    # Inject (do_not_autoplace yes) into the placed Reference property.
    found = WireDragger.find_symbol(sch, "R1")
    item = found[0]
    for sub in item[1:]:
        if (
            isinstance(sub, list)
            and len(sub) >= 3
            and sub[0] == _PROP_K
            and str(sub[1]).strip('"') == "Reference"
        ):
            sub.append([_DNA_K, _Symbol("yes")])
            break
    WireDragger.update_symbol_rotation_mirror(sch, "R1", 90.0, None)
    # Reference stays at its original position; Value still moves.
    assert _field_at(sch, "R1", "Reference") == (102.032, 100.0, 90.0)
    assert _field_at(sch, "R1", "Value") == (100.0, 100.0, 0)


def test_mirror_y_flips_reference_field_offset():
    """mirror_y (negates screen-X) moves Reference from (102.032,100) to (97.968,100)."""
    sch = _parse(_FIELD_SCH)
    WireDragger.update_symbol_rotation_mirror(sch, "R1", 0.0, "y")
    # lib (2.032,0,90): pin_world_xy(2.032,0,100,100,0,F,T)
    # lx,ly=2.032,0; _rotate(2.032,0,0)=(2.032,0); mirror_y rx=-2.032 -> (97.968,100); ang=90
    assert _field_at(sch, "R1", "Reference") == (97.968, 100.0, 90)


def test_get_lib_property_positions_reads_top_level():
    """get_lib_property_positions returns top-level lib property offsets."""
    sch = _parse(_FIELD_SCH)
    props = WireDragger.get_lib_property_positions(sch, "Test:R")
    assert props["Reference"] == (2.032, 0.0, 90.0)
    assert props["Value"] == (0.0, 0.0, 90.0)


# ---------------------------------------------------------------------------
# P0-a golden: rotation × mirror full matrix for field recomputation
# ---------------------------------------------------------------------------
# lib Reference (2.032, 0, 90), Value (0, 0, 90); symbol at (100, 100).
# Forward transform = Y-flip → rotate(-R) → mirror → translate; text angle
# keep-upright (180→0, 270→90). Value sits at the origin so only its angle
# changes; Reference moves around the body.
import pytest  # noqa: E402

# (rotation, mirror, expected_ref, expected_val_angle)
_GOLDEN = [
    (0, None, (102.032, 100.0, 90), 90),
    (90, None, (100.0, 97.968, 0), 0),
    (180, None, (97.968, 100.0, 90), 90),
    (270, None, (100.0, 102.032, 0), 0),
    (0, "x", (102.032, 100.0, 90), 90),
    (0, "y", (97.968, 100.0, 90), 90),
    (90, "x", (100.0, 102.032, 0), 0),
    (90, "y", (100.0, 97.968, 0), 0),
    (180, "x", (97.968, 100.0, 90), 90),
    (180, "y", (102.032, 100.0, 90), 90),
    (270, "x", (100.0, 97.968, 0), 0),
    (270, "y", (100.0, 102.032, 0), 0),
]


@pytest.mark.parametrize("rot,mirror,exp_ref,exp_val_ang", _GOLDEN)
def test_rotation_mirror_field_golden_matrix(rot, mirror, exp_ref, exp_val_ang):
    """All 12 rotation×mirror combinations must recompute Reference to the
    golden position/angle and Value to (100,100) with the keep-upright angle."""
    sch = _parse(_FIELD_SCH)
    ok = WireDragger.update_symbol_rotation_mirror(sch, "R1", float(rot), mirror)
    assert ok is True
    assert _field_at(sch, "R1", "Reference") == exp_ref
    # Value is at the lib origin (0,0) so it stays at the symbol origin (100,100)
    vx, vy, va = _field_at(sch, "R1", "Value")
    assert (vx, vy) == (100.0, 100.0)
    assert va == exp_val_ang
