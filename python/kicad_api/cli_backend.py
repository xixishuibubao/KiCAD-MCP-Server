"""
CLI Backend (headless, read-only)

Uses the official ``kicad-cli`` binary for headless, GUI-less operations:
version probing, DRC/ERC, exports, stats, rendering, jobsets, imports and
upgrades. This backend is **read-only / file-based** — it has no in-memory
board handle, so editing operations (place/move/route) raise
``NotImplementedError``. Use it for CI and automation where no KiCad GUI
process is running and only export/check/render workflows are needed.

Priority vs. other backends:
    - IPC backend: full editing, requires a running KiCad process
    - SWIG backend: full editing via pcbnew, DEPRECATED (removed in KiCad 10)
    - CLI backend: headless read-only/export, no editing, no KiCad process

In ``auto`` mode the CLI backend is NOT selected (it cannot edit); it is only
used when explicitly requested via ``backend_type='cli'`` or
``KICAD_BACKEND=cli``.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_api.base import APINotAvailableError, BoardAPI, ConnectionError, KiCADBackend
from utils.kicad_cli import resolve_kicad_cli, run_cli

logger = logging.getLogger(__name__)


class CLIBackend(KiCADBackend):
    """Headless, read-only backend backed by the ``kicad-cli`` binary."""

    def __init__(self) -> None:
        self._connected = False
        self._cli_path: Optional[str] = None
        self._version: Optional[str] = None
        self._project_path: Optional[Path] = None

    # -- connection lifecycle -------------------------------------------------
    def connect(self) -> bool:
        cli = resolve_kicad_cli()
        if not cli:
            raise APINotAvailableError(
                "CLI backend requires the kicad-cli binary, which was not found."
            )
        res = run_cli(["--version"], timeout=15)
        if not res["success"]:
            raise ConnectionError(f"kicad-cli probe failed: {res['stderr']}")
        self._cli_path = cli
        self._version = res["stdout"].strip()
        self._connected = True
        logger.info(f"✓ Connected to kicad-cli (CLI backend): {self._version}")
        return True

    def disconnect(self) -> None:
        self._connected = False
        self._cli_path = None
        self._project_path = None
        logger.info("Disconnected from CLI backend")

    def is_connected(self) -> bool:
        return self._connected

    def get_version(self) -> str:
        if not self.is_connected():
            raise ConnectionError("Not connected")
        return self._version or "unknown"

    # -- project operations (file-based, no in-memory state) ------------------
    def create_project(self, path: Path, name: str) -> Dict[str, Any]:
        # kicad-cli has no `create project` subcommand; project creation still
        # goes through the SWIG/IPC path or the template writer in
        # commands/project.py. Surface this clearly rather than faking it.
        raise NotImplementedError(
            "CLI backend cannot create projects (kicad-cli has no create-project "
            "subcommand). Use the IPC or SWIG backend, or commands/project.py."
        )

    def open_project(self, path: Path) -> Dict[str, Any]:
        if not self.is_connected():
            raise ConnectionError("Not connected")
        path = Path(path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Project not found: {path}")
        self._project_path = path
        return {
            "success": True,
            "projectPath": str(path),
            "backend": "cli",
            "version": self.get_version(),
        }

    def save_project(self, path: Optional[Path] = None, overwrite: bool = False) -> Dict[str, Any]:
        # CLI is stateless: nothing to save. Board edits are not supported here.
        return {"success": True, "message": "CLI backend is stateless; nothing to save"}

    def close_project(self) -> None:
        self._project_path = None

    def get_board(self) -> "CLIBoardAPI":
        if not self.is_connected():
            raise ConnectionError("Not connected")
        return CLIBoardAPI(self)


class CLIBoardAPI(BoardAPI):
    """Read-only BoardAPI backed by kicad-cli. Editing is not supported."""

    def __init__(self, backend: CLIBackend) -> None:
        self._backend = backend

    def set_size(self, width: float, height: float, unit: str = "mm") -> bool:
        raise NotImplementedError("CLI backend is read-only; cannot edit board size")

    def get_size(self) -> Dict[str, Any]:
        raise NotImplementedError("CLI backend does not parse board geometry; use get_board_stats")

    def add_layer(self, layer_name: str, layer_type: str) -> bool:
        raise NotImplementedError("CLI backend is read-only; cannot add layers")

    def list_components(self) -> List[Dict[str, Any]]:
        raise NotImplementedError(
            "CLI backend does not enumerate components; use the IPC/SWIG backend or export_pos"
        )

    def place_component(
        self,
        reference: str,
        footprint: str,
        x: float,
        y: float,
        rotation: float = 0,
        layer: str = "F.Cu",
        value: str = "",
    ) -> bool:
        raise NotImplementedError("CLI backend is read-only; cannot place components")
