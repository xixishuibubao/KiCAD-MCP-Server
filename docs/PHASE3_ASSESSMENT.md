# 阶段三评估：无 GUI 编辑路径与 SWIG 退役

> 以 KiCad 本体（`kicad-cli` 10.0.5 二进制 + `kicad-source-mirror-shallow`）的实际行为为基准。

## 结论摘要

阶段三的目标是"编辑类操作摆脱 SWIG，实现真正无 GUI 全自动"。经评估，**完整退役 SWIG 在当前条件下不可行**，原因均来自 KiCad 本体的实际状态，而非 MCP 侧限制：

1. **`kicad-cli` 无 `api-server` 子命令** — 顶层只有 `fp / jobset / pcb / sch / sym / version`。计划中"封装 `kicad-cli api-server` 无 GUI IPC"的前提不成立。无 GUI 的 IPC 服务需要运行 KiCad 进程（GUI 或 headless），不属于 `kicad-cli` 范围。
2. **`kicad-cli` 无编辑命令** — `pcb` 只有 `drc / export / import / render / upgrade`，`sch` 只有 `erc / export / upgrade`。放置/移动/走线/改规则等编辑操作没有对应 CLI 子命令，CLI 无法承担编辑。
3. **KiCad 10.0.5 仍提供 SWIG `pcbnew`** — `import pcbnew` 可用，`pcbnew.GetBuildVersion()` 返回 `10.0.5`。计划中"SWIG will be removed in KiCAD 10.0"的判断与本体实际不符；SWIG 仍可用（仅不再新增特性）。
4. **kipy 的 footprint-library 加载能力有限** — `ipc_backend.place_component` 当前采用 hybrid：用 SWIG `pcbnew.FootprintLoad` 从库加载封装定义，再经 IPC `create_items` 放置。kipy 尚无等价的"从库加载封装到内存"API，故放置元件仍需 SWIG。

## 已落地的阶段三工作

| 项 | 状态 | 说明 |
|---|---|---|
| 引入 `cli` 正式后端 | ✅ 已落地 | 新增 `python/kicad_api/cli_backend.py`（`CLIBackend`/`CLIBoardAPI`），`factory.py` 支持 `backend_type='cli'` 与 `KICAD_BACKEND=cli`，`get_available_backends` 增加 `cli` 探测。CLI 后端为只读/导出后端，**不参与 `auto`**（不支持编辑）。 |
| 评估 `kicad-cli api-server` | ✅ 评估完成 | 确认 `kicad-cli` 10.0.5 无 `api-server` 子命令；无 GUI IPC 需运行 KiCad 进程，不属 CLI 封装范围。 |
| IPC 编辑能力扩展 | ✅ 评估完成 | `ipc_backend.py` 已具备 `place_component`/`move_component`/`add_track`/`add_arc_track`/`add_via`/`delete_component`/`refill_zones` 等编辑方法，采用 `begin_commit`/`create_items`/`push_commit` 事务模型。`place_component` 因 kipy 库加载限制仍用 hybrid（SWIG 加载 + IPC 放置）。 |
| SWIG 退役 | ✅ 评估完成（保留兼容） | 以本体为准：KiCad 10.0.5 仍支持 SWIG，kipy 库加载有限，**SWIG 暂不退役**。已将 `factory.py`/`swig_backend.py` 中"will be removed in 10.0"的过时警告更正为准确信息。 |

## SWIG 退役路线（待条件成熟）

SWIG 退役的硬前提是 kipy 提供独立的 footprint-library 加载 API（不依赖 `pcbnew.FootprintLoad`）。在此之前：

1. **短期**：编辑操作继续 IPC 优先 → SWIG 回退（`auto` 模式），`place_component` 保持 hybrid。
2. **中期**：跟踪 kipy 上游，待其支持库加载后，将 `_load_footprint_from_library` 切换为 kipy 原生实现，移除 hybrid 的 SWIG 依赖。
3. **长期**：`commands/*.py` 中 16 个直接 `import pcbnew` 的文件逐个迁移到 `ipc_backend`，最终移除 `swig_backend.py`。

## 后端优先级（当前）

```
auto:  IPC (编辑，需 KiCad 进程)  →  SWIG (编辑，deprecated 但可用)
cli:   显式选择，只读/导出/检查/CI（无 KiCad 进程）
```

`cli` 后端不进 `auto`，因为它无法编辑；它服务于无 GUI 的 CI/导出/检查场景，与 `kicad_interface.py` 中已走 `run_cli` 的导出工具互补。
