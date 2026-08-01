"""Netlist-safe cosmetic lint for .kicad_sch files (lint_schematic_cosmetic).

Two passes, both applied as raw-text edits that never move a symbol, pin,
wire, junction, or label ANCHOR — only display attributes change, so the
netlist is preserved by construction:

  * hide_pin_names — ensure every top-level embedded lib_symbol definition
    (name contains ':'; sub-units and placed instances skipped) has a
    ``(pin_names ... (hide yes))`` directive, inserting
    ``(pin_names (offset 1.016) (hide yes))`` when the block is absent.
    In label-driven schematics the symbol's internal pin names duplicate the
    net label sitting on the same pin.

  * orient_labels — for every label/global_label/hierarchical_label whose
    anchor coincides with a component pin endpoint, rewrite only the text
    angle and justify so the text reads AWAY from the symbol body. Pin
    sheet positions and outward angles come from PinLocator
    (get_all_symbol_pins / get_pin_angle), which applies the full
    mirror/rotation-aware transform — rotated and mirrored instances are
    handled. Labels not sitting on a pin are counted and left untouched.

Field repositioning (Reference/Value) is autoplace_schematic_fields' job,
not this tool's.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sexpdata import Symbol

logger = logging.getLogger("kicad_interface")


def _segments_intersect_point(
    p1: Tuple[float, float], p2: Tuple[float, float],
    p3: Tuple[float, float], p4: Tuple[float, float],
) -> Optional[Tuple[float, float]]:
    """Return the intersection point of two line segments, or None.

    Only proper crossings (not parallel/collinear) are reported; this is a
    standard parametric line-segment intersection.
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None

_PASSES = ("hide_pin_names", "orient_labels")

# pin sheet-space outward angle -> (label text angle, justify), field-validated.
_ORIENT = {
    0: (180, "right"),  # pin on left edge  -> text extends left
    180: (0, "left"),  # pin on right edge -> text extends right
    90: (270, "right"),  # pin on top edge   -> text reads upward
    270: (90, "left"),  # pin on bottom edge-> text reads downward
}


def _find_blocks(src: str, opener: str) -> List[Tuple[int, int]]:
    """Spans (start, end_exclusive) of balanced-paren blocks starting with
    ``opener``. String-aware: parens inside quoted strings are ignored."""
    out: List[Tuple[int, int]] = []
    i = 0
    while True:
        j = src.find(opener, i)
        if j < 0:
            break
        depth = 0
        k = j
        in_str = esc = False
        while k < len(src):
            c = src[k]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    out.append((j, k + 1))
                    break
            k += 1
        i = k + 1
    return out


def _hide_pin_names(src: str) -> Tuple[str, int]:
    """Ensure every top-level embedded lib_symbol def hides its pin names.

    Only defs whose name contains ':' (real Lib:Part ids) are touched;
    sub-units like PART_1_1 and placed instances are skipped. Display
    attribute only — no geometry, no connectivity impact. Idempotent.
    """
    n = 0
    lib_blocks = _find_blocks(src, "(lib_symbols")
    if not lib_blocks:
        return src, 0
    lib_s, lib_e = lib_blocks[0]
    section = src[lib_s:lib_e]
    defs = []
    for s, e in _find_blocks(section, '(symbol "'):
        m = re.match(r'\(symbol "([^"]*)"', section[s:e])
        if m and ":" in m.group(1):
            defs.append((s, e))
    # right-to-left so earlier spans stay valid
    for s, e in reversed(defs):
        blk = section[s:e]
        # this def's OWN pin_names = the first (pin_names before any sub-unit
        sub = blk.find('(symbol "', 1)
        header = blk if sub < 0 else blk[:sub]
        pn = header.find("(pin_names")
        if pn >= 0:
            for ps, pe in _find_blocks(blk, "(pin_names"):
                if ps == pn:
                    if "hide" not in blk[ps:pe]:
                        blk = blk[: pe - 1].rstrip() + "\n\t\t\t\t(hide yes)\n\t\t\t)" + blk[pe:]
                        n += 1
                    break
        else:
            nl = blk.find("\n")
            blk = (
                blk[: nl + 1]
                + "\t\t\t(pin_names\n\t\t\t\t(offset 1.016)\n\t\t\t\t(hide yes)\n\t\t\t)\n"
                + blk[nl + 1 :]
            )
            n += 1
        section = section[:s] + blk + section[e:]
    return src[:lib_s] + section + src[lib_e:], n


def _build_pin_orient_map(sch_path: Path) -> Dict[Tuple[float, float], int]:
    """(round(x,2), round(y,2)) -> outward angle (0/90/180/270) for every
    placed component pin, via the mirror/rotation-aware PinLocator."""
    from commands.pin_locator import PinLocator
    from commands.schematic import SchematicManager

    # Fresh locator per call: PinLocator caches parsed schematics by path
    # with no mtime invalidation, so a shared instance could serve stale
    # geometry after other edits.
    locator = PinLocator()
    sch = SchematicManager.load_schematic(str(sch_path))

    pin_map: Dict[Tuple[float, float], int] = {}
    for symbol in getattr(sch, "symbol", None) or []:
        try:
            if not hasattr(symbol, "property") or not hasattr(symbol.property, "Reference"):
                continue
            ref = symbol.property.Reference.value
            if ref.startswith("_TEMPLATE"):
                continue
            pin_locations = locator.get_all_symbol_pins(sch_path, ref)
            for pin_num, coords in pin_locations.items():
                angle = locator.get_pin_angle(sch_path, ref, pin_num)
                if angle is None:
                    continue
                rounded = int(round(angle / 90.0) * 90) % 360
                if min(abs(angle - rounded) % 360, 360 - abs(angle - rounded) % 360) > 1:
                    continue  # non-cardinal pin; skip
                pin_map[(round(coords[0], 2), round(coords[1], 2))] = rounded
        except Exception as e:
            logger.warning(f"orient_labels: skipping symbol pins: {e}")
    return pin_map


def _orient_labels(src: str, pin_map: Dict[Tuple[float, float], int]) -> Tuple[str, int, int]:
    """Rewrite label text angle + justify from the pin each label sits on.

    The anchor coordinates are never touched. Returns
    (new_src, oriented_count, skipped_not_on_pin).
    """
    n = 0
    skipped = 0
    for opener in ('(global_label "', '(hierarchical_label "', '(label "'):
        for s, e in reversed(_find_blocks(src, opener)):
            blk = src[s:e]
            at = re.search(r"(\(at )(-?[\d.]+) (-?[\d.]+) (-?[\d.]+)(\))", blk)
            if not at:
                continue
            key = (round(float(at.group(2)), 2), round(float(at.group(3)), 2))
            if key not in pin_map:
                skipped += 1
                continue
            angle, justify = _ORIENT[pin_map[key]]
            new = blk
            if float(at.group(4)) != angle:
                new = (
                    new[: at.start()]
                    + f"{at.group(1)}{at.group(2)} {at.group(3)} {angle}{at.group(5)}"
                    + new[at.end() :]
                )
            jm = re.search(r"\(justify [^)]*\)", new)
            if jm:
                new = new[: jm.start()] + f"(justify {justify})" + new[jm.end() :]
            else:
                fm = re.search(r"(\(font\s*\(size [\d.]+ [\d.]+\)\s*\))", new)
                if fm:
                    new = new[: fm.end()] + f"\n\t\t\t(justify {justify})" + new[fm.end() :]
            if new != blk:
                src = src[:s] + new + src[e:]
                n += 1
    return src, n, skipped


class SchematicLintCommands:
    """Handler for the lint_schematic_cosmetic MCP tool."""

    def lint_schematic_cosmetic(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from commands.schematic import SchematicLoadError

            schematic_path = params.get("schematicPath")
            if not schematic_path:
                return {"success": False, "message": "schematicPath is required"}
            if not os.path.isfile(schematic_path):
                return {
                    "success": False,
                    "message": f"Schematic not found: {schematic_path}",
                }

            passes = params.get("passes", list(_PASSES))
            unknown = [p for p in passes if p not in _PASSES]
            if unknown:
                return {
                    "success": False,
                    "message": (
                        f"Unknown pass(es): {', '.join(unknown)}. "
                        f"Valid passes: {', '.join(_PASSES)}"
                    ),
                }
            dry_run = bool(params.get("dryRun", False))

            with open(schematic_path, "r", encoding="utf-8") as f:
                src = f.read()
            original = src

            counts = {p: 0 for p in _PASSES}
            skipped_labels = 0
            for pass_name in passes:
                if pass_name == "hide_pin_names":
                    src, counts["hide_pin_names"] = _hide_pin_names(src)
                elif pass_name == "orient_labels":
                    try:
                        pin_map = _build_pin_orient_map(Path(schematic_path))
                    except SchematicLoadError as e:
                        return e.to_response()
                    src, counts["orient_labels"], skipped_labels = _orient_labels(src, pin_map)

            changed = src != original
            if changed and not dry_run:
                with open(schematic_path, "w", encoding="utf-8") as f:
                    f.write(src)

            message_parts = []
            if "hide_pin_names" in passes:
                message_parts.append(f"hide_pin_names: {counts['hide_pin_names']} def(s) hidden")
            if "orient_labels" in passes:
                message_parts.append(
                    f"orient_labels: {counts['orient_labels']} label(s) reoriented "
                    f"({skipped_labels} not on a pin, untouched)"
                )
            message = "; ".join(message_parts)
            if dry_run:
                message = f"[dry run] {message}"

            return {
                "success": True,
                "dryRun": dry_run,
                "changed": changed,
                "counts": {p: counts[p] for p in passes},
                "skippedLabels": skipped_labels,
                "message": message,
            }
        except Exception as e:
            import traceback

            logger.error(f"lint_schematic_cosmetic failed: {e}")
            return {
                "success": False,
                "message": f"lint_schematic_cosmetic failed: {e}",
                "errorDetails": traceback.format_exc(),
            }

    # ------------------------------------------------------------------
    # lint_schematic_design_rules — read-only checks derived from 经验.md
    # ------------------------------------------------------------------
    _DESIGN_RULES = (
        "value_missing",
        "power_naming",
        "decoupling",
        "decoupling_precise",
        "interface",
        "interface_precise",
        "flow_direction",
        "flow_direction_precise",
        "junction",
        "annotation",
    )

    def lint_schematic_design_rules(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read-only design-rule checks for a .kicad_sch, derived from 经验.md.

        Returns a structured violation list — the file is never modified.
        Each violation carries ``rule``, ``severity`` (error/warning/info),
        ``reference`` (when applicable) and ``message``.
        """
        try:
            schematic_path = params.get("schematicPath")
            if not schematic_path:
                return {"success": False, "message": "schematicPath is required"}
            if not os.path.isfile(schematic_path):
                return {"success": False, "message": f"Schematic not found: {schematic_path}"}

            rules = params.get("rules") or list(self._DESIGN_RULES)
            unknown = [r for r in rules if r not in self._DESIGN_RULES]
            if unknown:
                return {
                    "success": False,
                    "message": f"Unknown rule(s): {', '.join(unknown)}. "
                    f"Valid: {', '.join(self._DESIGN_RULES)}",
                }

            from commands import schematic_analysis as sa

            sexp = sa._load_sexp(Path(schematic_path))
            symbols = sa._parse_symbols(sexp)
            props = sa._parse_symbol_properties(sexp)
            wires = sa._parse_wires(sexp)
            labels = sa._parse_labels(sexp)
            junctions = self._parse_junctions(sexp)
            texts = self._parse_texts(sexp)

            val_by_ref = {
                p["reference"]: p["value"] for p in props if p["name"] == "Value"
            }
            violations: List[Dict[str, Any]] = []

            if "value_missing" in rules:
                violations += self._check_value_missing(symbols, val_by_ref)
            if "power_naming" in rules:
                violations += self._check_power_naming(labels, props)
            if "decoupling" in rules:
                violations += self._check_decoupling(symbols)
            if "decoupling_precise" in rules:
                violations += self._check_decoupling_precise(symbols, schematic_path)
            if "interface" in rules:
                violations += self._check_interface(labels, props)
            if "interface_precise" in rules:
                violations += self._check_interface_precise(labels, schematic_path)
            if "flow_direction" in rules:
                violations += self._check_flow_direction(labels)
            if "flow_direction_precise" in rules:
                violations += self._check_flow_direction_precise(symbols, schematic_path)
            if "junction" in rules:
                violations += self._check_junctions(wires, junctions)
            if "annotation" in rules:
                violations += self._check_annotation(labels, texts)

            by_rule: Dict[str, int] = {}
            for v in violations:
                by_rule[v["rule"]] = by_rule.get(v["rule"], 0) + 1
            return {
                "success": True,
                "violations": violations,
                "summary": {"total": len(violations), "by_rule": by_rule},
                "message": f"{len(violations)} design-rule violation(s) found.",
            }
        except Exception as e:
            import traceback
            logger.error(f"lint_schematic_design_rules failed: {e}")
            return {
                "success": False,
                "message": f"lint_schematic_design_rules failed: {e}",
                "errorDetails": traceback.format_exc(),
            }

    @staticmethod
    def _parse_junctions(sexp_data: list) -> List[Dict[str, float]]:
        out = []
        for item in sexp_data:
            if not isinstance(item, list) or not item or item[0] != Symbol("junction"):
                continue
            for sub in item:
                if isinstance(sub, list) and len(sub) >= 3 and sub[0] == Symbol("at"):
                    out.append({"x": float(sub[1]), "y": float(sub[2])})
                    break
        return out

    @staticmethod
    def _parse_texts(sexp_data: list) -> List[Dict[str, Any]]:
        out = []
        for item in sexp_data:
            if not isinstance(item, list) or len(item) < 2 or item[0] != Symbol("text"):
                continue
            content = str(item[1]).strip('"') if len(item) >= 2 else ""
            x = y = 0.0
            for sub in item:
                if isinstance(sub, list) and len(sub) >= 3 and sub[0] == Symbol("at"):
                    x, y = float(sub[1]), float(sub[2])
                    break
            out.append({"content": content, "x": x, "y": y})
        return out

    @staticmethod
    def _check_value_missing(symbols, val_by_ref) -> List[Dict[str, Any]]:
        """R1: every part needs a clear value (经验.md 2.1#3)."""
        out = []
        placeholders = {"", "?", "~", "TBD", "TBD?"}
        for sym in symbols:
            ref = sym["reference"]
            if ref.startswith("#") or ref.startswith("_TEMPLATE"):
                continue
            val = val_by_ref.get(ref, "")
            if val in placeholders or val == ref:
                out.append({
                    "rule": "value_missing",
                    "severity": "warning",
                    "reference": ref,
                    "message": f"Value is empty or placeholder '{val}' — every part needs a clear value (经验.md 2.1#3)",
                })
        return out

    # Canonical power-rail names → known aliases (case-insensitive). Two
    # aliases of the same rail in one sheet means an implicit net split.
    _POWER_ALIAS_GROUPS = {
        "3V3": {"3V3", "3.3V", "VCC33", "P3V3", "V3P3", "+3V3", "+3.3V", "VDD3V3"},
        "5V": {"5V", "VCC5", "P5V", "+5V", "VDD5V"},
        "12V": {"12V", "VCC12", "+12V"},
        "GND": {"GND", "GNDD", "GNDP", "DGND", "AGND", "PGND", "VSS"},
        "VBAT": {"VBAT", "V_BAT", "VBATT"},
    }

    @classmethod
    def _check_power_naming(cls, labels, props) -> List[Dict[str, Any]]:
        """R2: unify power-rail naming (经验.md 2.1#4)."""
        names = {l["name"] for l in labels}
        for p in props:
            if p["name"] == "Value" and p["reference"].startswith("#PWR"):
                if p["value"] and p["value"] not in ("?", "~"):
                    names.add(p["value"])
        out = []
        for canonical, aliases in cls._POWER_ALIAS_GROUPS.items():
            present = {n for n in names if n in aliases}
            if len(present) > 1:
                out.append({
                    "rule": "power_naming",
                    "severity": "error",
                    "message": f"Power rail '{canonical}' has multiple aliases in use: {sorted(present)} — unify naming or nets will split (经验.md 2.1#4)",
                })
        return out

    # IC lib_id substrings that should have local decoupling (经验.md 2.2).
    _IC_LIB_HINTS = ("MCU", "STM", "STM32", "STM8", "ESP", "GD32", "ATmega",
                     "ATtiny", "PIC", "RP2040", "nRF", "BLE", "LDO", "DCDC",
                     "TPS", "RT", "AMS1117", "AMS", "MAX", "ADU", "74", "CD40")

    @classmethod
    def _check_decoupling(cls, symbols) -> List[Dict[str, Any]]:
        """R3: every IC needs a 100nF decoupling cap within ~10 mm (经验.md 2.2)."""
        cap_positions = []
        for sym in symbols:
            name = sym["lib_id"].split(":")[-1]
            if name.startswith("C"):
                cap_positions.append((sym["x"], sym["y"]))
        out = []
        for sym in symbols:
            lib = sym["lib_id"]
            name = lib.split(":")[-1]
            if name.startswith(("C", "R", "L", "D", "Q", "J", "P", "K")):
                continue
            if not any(h in lib for h in cls._IC_LIB_HINTS):
                continue
            has_local = any(
                abs(cx - sym["x"]) <= 10.0 and abs(cy - sym["y"]) <= 10.0
                for cx, cy in cap_positions
            )
            if not has_local:
                out.append({
                    "rule": "decoupling",
                    "severity": "warning",
                    "reference": sym["reference"],
                    "message": f"No decoupling capacitor within 10 mm — every IC VCC pin needs a 100nF cap nearby (经验.md 2.2)",
                })
        return out

    @staticmethod
    def _check_interface(labels, props) -> List[Dict[str, Any]]:
        """R4: interface circuits need pull-ups / series resistors / ESD (经验.md 2.4)."""
        all_names = {l["name"] for l in labels}
        all_names |= {p["value"] for p in props if p["name"] == "Value"}
        joined = " ".join(all_names).upper()
        out = []
        if "SDA" in joined and "SCL" in joined:
            has_pull = any(
                p["name"] == "Value" and p["reference"].startswith("R")
                and any(s in str(p["value"]).upper() for s in ("K", "Ω", "OHM"))
                for p in props
            )
            if not has_pull:
                out.append({
                    "rule": "interface",
                    "severity": "warning",
                    "message": "I2C bus detected (SDA/SCL) but no pull-up resistor found — I2C needs ~4.7kΩ pull-ups (经验.md 2.4)",
                })
        if "D+" in joined and "D-" in joined:
            out.append({
                "rule": "interface",
                "severity": "info",
                "message": "USB D+/D- detected — verify 22-33Ω series resistors and ESD protection (经验.md 2.4)",
            })
        return out

    @staticmethod
    def _check_flow_direction(labels) -> List[Dict[str, Any]]:
        """R5: power on top, ground on bottom (经验.md 2.1#2). Info-level — full
        flow analysis needs pin electrical types."""
        out = []
        power = [l for l in labels
                 if l["name"].upper().startswith(("VCC", "VDD", "+", "VBAT"))
                 or "3V3" in l["name"].upper() or "5V" in l["name"].upper()]
        gnd = [l for l in labels if l["name"].upper().startswith(("GND", "VSS"))]
        if power and gnd:
            avg_power_y = sum(p["y"] for p in power) / len(power)
            avg_gnd_y = sum(g["y"] for g in gnd)
            if avg_power_y > avg_gnd_y:
                out.append({
                    "rule": "flow_direction",
                    "severity": "info",
                    "message": "Power labels sit below ground labels — convention is power on top, ground on bottom (经验.md 2.1#2)",
                })
        return out

    @staticmethod
    def _check_junctions(wires, junctions) -> List[Dict[str, Any]]:
        """R6: wire crossings need a junction dot (经验.md 2.1❌)."""
        out = []
        n = len(wires)
        for i in range(n):
            for j in range(i + 1, n):
                w1, w2 = wires[i], wires[j]
                pt = _segments_intersect_point(w1["start"], w1["end"], w2["start"], w2["end"])
                if pt is None:
                    continue
                # Endpoint touches are real connections, not crossings.
                touch = False
                for endp in (w1["start"], w1["end"], w2["start"], w2["end"]):
                    if abs(endp[0] - pt[0]) < 0.01 and abs(endp[1] - pt[1]) < 0.01:
                        touch = True
                        break
                if touch:
                    continue
                has_junction = any(
                    abs(jc["x"] - pt[0]) < 0.3 and abs(jc["y"] - pt[1]) < 0.3
                    for jc in junctions
                )
                if not has_junction:
                    out.append({
                        "rule": "junction",
                        "severity": "warning",
                        "message": f"Wire crossing at ({pt[0]:.2f}, {pt[1]:.2f}) has no junction dot — verify it is not an unintended connection (经验.md 2.1❌)",
                    })
        return out

    @staticmethod
    def _check_annotation(labels, texts) -> List[Dict[str, Any]]:
        """R7: key nets should have a nearby text annotation (经验.md 2.1#5)."""
        out = []
        for lbl in labels:
            name_u = lbl["name"].upper()
            is_key = name_u.startswith(("VCC", "VDD", "VBAT", "+")) or "3V3" in name_u or "5V" in name_u
            if not is_key:
                continue
            has_text = any(
                abs(t["x"] - lbl["x"]) <= 5.0 and abs(t["y"] - lbl["y"]) <= 5.0
                for t in texts
            )
            if not has_text:
                out.append({
                    "rule": "annotation",
                    "severity": "info",
                    "reference": lbl["name"],
                    "message": f"Key net '{lbl['name']}' has no nearby text annotation — annotate voltage/current on key nodes (经验.md 2.1#5)",
                })
        return out

    # ------------------------------------------------------------------
    # Precise variants — use PinLocator pin electrical types + world coords
    # (经验.md deepening). Fall back to a note when PinLocator is unavailable.
    # ------------------------------------------------------------------
    _POWER_PIN_TYPES = {"power_in", "power_out", "power_in_out", "passive"}

    @classmethod
    def _check_decoupling_precise(cls, symbols, schematic_path) -> List[Dict[str, Any]]:
        """R3-precise: every IC power pin needs a 100nF cap within 10 mm.

        Uses PinLocator to identify power_in/power_out pins by electrical type
        and locate them in world space, so the check is per-VCC-pin rather
        than per-IC-centroid (经验.md 2.2).
        """
        out = []
        try:
            from commands.pin_locator import PinLocator
            locator = PinLocator()
        except Exception as e:
            return [{
                "rule": "decoupling_precise",
                "severity": "info",
                "message": f"PinLocator unavailable ({e}); decoupling_precise skipped — use 'decoupling' heuristic instead",
            }]

        cap_positions = [(s["x"], s["y"]) for s in symbols
                         if s["reference"].startswith("C")]
        for sym in symbols:
            ref = sym["reference"]
            name = sym["lib_id"].split(":")[-1]
            if ref.startswith(("#", "_TEMPLATE")):
                continue
            if name.startswith(("C", "R", "L", "D", "Q", "J", "P", "K")):
                continue
            if not any(h in sym["lib_id"] for h in cls._IC_LIB_HINTS):
                continue
            try:
                pins = locator.get_symbol_pins(Path(schematic_path), sym["lib_id"])
            except Exception:
                pins = {}
            if not pins:
                continue
            for pin_num, pin in pins.items():
                if pin.get("type") not in ("power_in", "power_out"):
                    continue
                loc = locator.get_pin_location(Path(schematic_path), ref, pin_num)
                if not loc:
                    continue
                px, py = loc[0], loc[1]
                has_local = any(
                    abs(cx - px) <= 10.0 and abs(cy - py) <= 10.0
                    for cx, cy in cap_positions
                )
                if not has_local:
                    out.append({
                        "rule": "decoupling_precise",
                        "severity": "warning",
                        "reference": f"{ref}.{pin_num}",
                        "message": f"Power pin {ref}/{pin_num} ({pin.get('name','?')}) has no 100nF decoupling cap within 10 mm — every IC VCC pin needs local decoupling (经验.md 2.2)",
                    })
        return out

    @staticmethod
    def _check_flow_direction_precise(symbols, schematic_path) -> List[Dict[str, Any]]:
        """R5-precise: input pins on the right / output pins on the left of an
        IC body violate the left→right signal-flow convention (经验.md 2.1#2).

        Uses PinLocator pin electrical types + world coordinates against the
        symbol centroid, so this is a real per-pin flow check rather than the
        label-Y heuristic in ``flow_direction``.
        """
        out = []
        try:
            from commands.pin_locator import PinLocator
            locator = PinLocator()
        except Exception as e:
            return [{
                "rule": "flow_direction_precise",
                "severity": "info",
                "message": f"PinLocator unavailable ({e}); flow_direction_precise skipped — use 'flow_direction' heuristic instead",
            }]

        for sym in symbols:
            ref = sym["reference"]
            name = sym["lib_id"].split(":")[-1]
            if ref.startswith(("#", "_TEMPLATE")):
                continue
            if name.startswith(("C", "R", "L", "D", "Q", "J", "P", "K")):
                continue
            cx, cy = sym["x"], sym["y"]
            try:
                pins = locator.get_symbol_pins(Path(schematic_path), sym["lib_id"])
            except Exception:
                continue
            for pin_num, pin in pins.items():
                ptype = pin.get("type", "")
                if ptype not in ("input", "output", "bidirectional"):
                    continue
                loc = locator.get_pin_location(Path(schematic_path), ref, pin_num)
                if not loc:
                    continue
                px, py = loc[0], loc[1]
                if ptype in ("input", "bidirectional") and px > cx + 0.5:
                    out.append({
                        "rule": "flow_direction_precise",
                        "severity": "info",
                        "reference": f"{ref}.{pin_num}",
                        "message": f"Input pin {ref}/{pin_num} ({pin.get('name','?')}) is on the right side of the body — convention is signal flow left→right, inputs on the left (经验.md 2.1#2)",
                    })
                elif ptype == "output" and px < cx - 0.5:
                    out.append({
                        "rule": "flow_direction_precise",
                        "severity": "info",
                        "reference": f"{ref}.{pin_num}",
                        "message": f"Output pin {ref}/{pin_num} ({pin.get('name','?')}) is on the left side of the body — convention is signal flow left→right, outputs on the right (经验.md 2.1#2)",
                    })
        return out

    @staticmethod
    def _check_interface_precise(labels, schematic_path) -> List[Dict[str, Any]]:
        """R4-precise: verify interface pull-ups / series resistors / ESD using
        net topology (get_net_connections) rather than mere net-name presence
        (经验.md 2.4). Falls back to a note when the connection analyser is
        unavailable.
        """
        out = []
        try:
            from commands.schematic import SchematicManager
            from commands.connection_schematic import ConnectionManager
            sch = SchematicManager.load_schematic(str(schematic_path))
            conn = ConnectionManager()
        except Exception as e:
            return [{
                "rule": "interface_precise",
                "severity": "info",
                "message": f"Connection analyser unavailable ({e}); interface_precise skipped — use 'interface' heuristic instead",
            }]

        label_names = {l["name"] for l in labels}

        def _net_has_resistor(net_name: str) -> bool:
            try:
                conns = conn.get_net_connections(sch, net_name, Path(schematic_path))
            except Exception:
                return False
            for c in conns:
                comp = str(c.get("component", ""))
                if comp.startswith("R"):
                    return True
            return False

        def _net_has_esd(net_name: str) -> bool:
            try:
                conns = conn.get_net_connections(sch, net_name, Path(schematic_path))
            except Exception:
                return False
            for c in conns:
                comp = str(c.get("component", ""))
                if comp.startswith(("D", "TVS", "U")):
                    return True
            return False

        # I2C: SDA + SCL both need pull-ups.
        i2c_pairs = []
        sda = next((n for n in label_names if n.upper() == "SDA"), None)
        scl = next((n for n in label_names if n.upper() == "SCL"), None)
        if sda and scl:
            i2c_pairs.append((sda, scl))
        for sda_n, scl_n in i2c_pairs:
            if not _net_has_resistor(sda_n) or not _net_has_resistor(scl_n):
                out.append({
                    "rule": "interface_precise",
                    "severity": "warning",
                    "message": f"I2C bus {sda_n}/{scl_n} is missing a pull-up resistor on one or both lines — I2C needs ~4.7kΩ pull-ups on SDA and SCL (经验.md 2.4)",
                })

        # USB: D+ / D- need series resistors + ESD.
        dp = next((n for n in label_names if n.upper() in ("D+", "DP")), None)
        dm = next((n for n in label_names if n.upper() in ("D-", "DM")), None)
        if dp and dm:
            if not _net_has_resistor(dp) or not _net_has_resistor(dm):
                out.append({
                    "rule": "interface_precise",
                    "severity": "warning",
                    "message": f"USB {dp}/{dm} is missing a series resistor on one or both lines — USB needs 22-33Ω series resistors (经验.md 2.4)",
                })
            if not _net_has_esd(dp) and not _net_has_esd(dm):
                out.append({
                    "rule": "interface_precise",
                    "severity": "info",
                    "message": f"USB {dp}/{dm} has no ESD protection detected on either line — add a TVS/ESD diode (经验.md 2.4)",
                })
        return out
