# 两种 KiCad MCP 扩展能力评估报告

> 基于 KiCad 最新源码（`kicad-source-mirror-shallow`）由 5 个并行 agent 分领域评估
> 评估对象：华秋 `kicad-mcp` v0.1.6（76 工具，GUI 遥控）与本仓库 `KiCAD-MCP-Server` v2.2.3（122 工具，完整流程）
> 生成日期：2026-08-01

---

## 一、总体结论

**两种 MCP 都还有显著的接入与优化空间，且互补性远大于替代性。**

| 维度 | 华秋 kicad-mcp | 本仓库 KiCAD-MCP-Server |
|------|----------------|--------------------------|
| 当前能力上限 | GUI 遥控 + 参数化绘图/放置（约 50 个白名单 API） | 完整设计流程 + 离线交付（约 60% CLI 覆盖） |
| 最大未接入能力 | PCB DRC、制造导出全套、离线 ERC、原理图多格式导入 | PNS 交互布线、GUI 遥控、3D 渲染、原理图 IPC 实时同步 |
| 扩展天花板 | cpp_sdk 私有协议无开源服务端，难自行扩展；动作系统 500+ 项仅覆盖子集 | kipy 官方 API 约 90+ 命令仅接 25 个；可三后端并存 |
| 最佳扩展路径 | **封装 kicad-cli** 补齐 DRC/导出/离线（不改架构） | **IPC 后端扩到全量 + 引入 cpp_sdk 第三后端补 GUI** |

**一句话**：华秋强在"操作 KiCad 界面"但工程化天花板低；本仓库强在"完成设计全流程"但 GUI 交互与实时性弱。两者最大共同短板是 **PNS Push-and-Shove 交互布线引擎**（两种 MCP 均未接入）。

---

## 二、五领域评估汇总

### 领域 1：IPC API / kipy 扩展（[IPC API 评估](9354cf4b-b180-454a-b076-5b85d9b2326d)）

官方 IPC 约 **90+ 条 protobuf 命令**，本仓库 IPC 后端仅覆盖约 25 个 MCP 工具的 PCB 实时同步。

| 潜在能力 | KiCad 源码位置 | 本仓库 | 华秋 | 优化建议 | 适用 |
|---------|---------------|:------:|:----:|---------|:----:|
| 原理图 CRUD（符号/连线/标签） | `api/proto/schematic/`、`eeschema/api/api_handler_sch.cpp` | ❌ | ✅ | 新增 SchematicIPCBackend，复用 kipy commit + CreateItems | 本仓库 |
| 制造导出 Job 全家桶 | `api/proto/board/board_jobs.proto` | ❌ | ❌ | export 改 IPC-first，SWIG 作离线回退 | 本仓库 |
| RunAction 低层 GUI 动作 | `api/proto/common/commands/editor_commands.proto` | ❌ | ✅ | IPC 后端封装 run_action 映射华秋 zoomView/selectAll | 互补 |
| 设计规则 + 网络类读写 | `api/proto/board/board_commands.proto` | ❌(SWIG✅) | ❌ | Get/SetBoardDesignRules + NetClasses 实时生效 | 本仓库 |
| 网表导入/原理图→板同步 | `board_commands.proto` ImportNetlist | ❌(SWIG✅) | ⚠️ | ImportNetlist(dry_run=True) 先预览再提交 | 本仓库 |
| 层可见性/活动层/外观 | `board_commands.proto` L420-514 | ❌ | ⚠️ | SetVisibleLayers/SetActiveLayer 替代华秋视图控制 | 本仓库 |
| Open/Close/RevertDocument | `project_commands.proto` L85-108 | ❌ | ⚠️ | 可编程开/关/回滚文档 | 本仓库 |
| 原理图层级/连接性查询 | `schematic_commands.proto` | ❌(SWIG✅) | ❌ | GetSchematicNetlist 比解析 .kicad_sch 准确 | 本仓库 |
| 连通性分析（按网络/类） | `board_commands.proto` L197-240 | ❌(SWIG✅) | ❌ | 飞线/布线助手改用 IPC 连通查询 | 本仓库 |
| InteractiveMoveItems | `board_commands.proto` L529-534 | ❌ | ⚠️ | AI 选中→用户 GUI 微调混合工作流 | 互补 |
| ParseAndCreateItemsFromString | `editor_commands.proto` L458-467 | ❌ | ❌ | S-expr 粘贴批量创建复杂图元 | 本仓库 |
| 3D 光追渲染截图 | `board_jobs.proto` L192-224 | ❌(SWIG✅) | ❌ | 比 2D 截图质量高，适合 MCP resource 返回 PNG | 本仓库 |
| Footprint Wizard 插件 | `types/wizards.proto`、`api_plugin.h` | ❌(SWIG✅) | ⚠️ | 调 QFP 等向导比手写 pad 规范 | 本仓库 |
| Spice/对话框/非KiCad导入 | 华秋私有通道，**不在**官方 IPC proto | ❌ | ✅ | 官方 IPC 无对应命令；本仓库可 RunAction 试探 | 华秋独有 |

**可行性：高。** kipy 已封装 Protobuf，扩展主要是映射工作。建议三阶段：P0 文档生命周期+规则+层+导出Job；P1 原理图IPC后端+连通性；P2 PCB RunAction+交互式移动。全量接入约 90+ 命令，可让 60-70 个现有工具走实时 IPC。

---

### 领域 2：C++ SDK / 动作系统扩展（[C++ SDK 评估](7498635b-6f65-4487-a08e-59515c4a6206)）

KiCad 源码动作系统合计 **500+ TOOL_ACTION**，华秋 cpp_sdk 仅封装约 50 个白名单 API。

| 潜在能力 | KiCad 源码位置 | 华秋 | 本仓库 | 优化建议 | 适用 |
|---------|---------------|:----:|:------:|---------|:----:|
| PCB DRC 运行+规则编辑器 | `pcbnew/tools/pcb_actions.h` runDRC | ❌ | ✅ | 华秋 cpp_sdk 封装 runDRC 驱动 GUI | 两者 |
| 敷铜绘制/填充/合并 | `pcb_actions.h` drawZone/zoneFill | ❌ | ✅ | 华秋补参数化 drawZone | 本仓库 |
| Push&Shove 交互布线/差分 | `pcb_actions.h` routeSingleTrack/routeDiffPair | ❌ | ✅(几何) | 依赖鼠标事件，白名单难复刻 | 本仓库 |
| 原理图 Junction/总线入口/规则区 | `eeschema/tools/sch_actions.h` | ❌ | ⚠️ | 华秋补 GUI 动作；本仓库 SWIG 补写入 | 两者 |
| 层级页引脚同步/自动放置 | `sch_actions.h` syncSheetPins | ❌ | ⚠️ | 高价值 GUI 能力，华秋 cpp_sdk 或 RunAction | 华秋 |
| 3D 查看器/测量工具 | `pcb_viewer_tools.cpp` Show3DViewer | ❌ | ❌ | cpp_sdk 封装 show3DViewer；测量返回距离 JSON | 华秋 |
| 网络高亮/飞线/Net Inspector | `pcb_actions.h` highlightNet | ⚠️ | ⚠️ | 交互调试用 cpp_sdk 驱动 highlightNet | 华秋 |
| 通用 RunAction 网关 | `editor_commands.proto` RunAction | ❌ | ⚠️(未暴露) | **关键扩展点**：IPC 后端加 run_kicad_action 网关 | 本仓库+华秋 |
| Symbol/Footprint 编辑器遥控 | `symbol_editor_drawing_tools.*` | ❌ | ⚠️ | 华秋开 symbol/footprint MCP 实例 | 华秋 |
| Spice 仿真执行（非仅开对话框） | `sch_actions.h` runSimulation | ⚠️ | ❌ | cpp_sdk 补 runSimulation/stopSimulation | 华秋 |
| 设计块放置与管理 | `sch_actions.h`+`pcb_actions.h` placeDesignBlock | ⚠️ | ❌ | 模块化复用交互场景 | 华秋 |
| PCB 对齐/分布/相对定位 | `pcb_actions.h` alignTop/distributeHorizontally | ❌ | ✅ | 华秋补 GUI 对齐；本仓库已有算法层 | 两者 |
| IPC 事务 Commit（Undo 友好） | `editor_commands.proto` BeginCommit/EndCommit | ❌ | ⚠️ | 批量写操作包在 BeginCommit→EndCommit | 本仓库 |
| 原理图类标签 | `sch_actions.h` placeClassLabel | ✅ | ❌ | 本仓库可借鉴华秋 MIT 实现 | 华秋已有 |

**华秋 cpp_sdk 天花板**：私有协议无开源服务端，扩展依赖 KiCad 10+华秋后续版本，无法从源码自行扩展。最值得做的两点：① 通用 RunAction 网关（仿 kipy）；② 补齐 symbol/footprint editor 实例。

**本仓库借鉴可行性：高**。华秋 MIT 开源，`kicad_client.py` 可直接移植为 Python 第三后端 `CppSdkBackend`，与 IPC/SWIG 并列。建议三后端：SWIG（离线/CI）→ kipy（稳定数据面+RunAction）→ cpp_sdk（GUI 遥控，KiCad 10 运行时）。

---

### 领域 3：kicad-cli 命令行扩展（[kicad-cli 评估](e0335be2-f778-429a-8783-b33d23cf3da8)）

kicad-cli 是官方 headless 引擎，无需 GUI/SWIG/IPC，CI/Docker 唯一可靠路径。

| CLI 能力 | KiCad 源码位置 | 本仓库 | 华秋 | 优化建议 | 适用 |
|---------|---------------|:------:|:----:|---------|:----:|
| jobset run（批量作业链） | `cli/command_jobset_run.cpp` | ❌ | ❌ | 新增 run_jobset，CI 一键跑完整制造流水线 | 本仓库 |
| pcb render（3D 光追） | `cli/command_pcb_render.cpp` | ❌ | ❌ | 新增 render_pcb_3d 用于 AI 视觉反馈 | 两者 |
| pcb/sch/fp/sym/gerber diff | `cli/command_pcb_diff.h` 等 | ❌ | ❌ | 新增 diff_pcb/diff_schematic 供 PR/CI 回归 | 本仓库 |
| pcb export stats（板统计） | `cli/command_pcb_export_stats.cpp` | ❌ | ❌ | 新增 get_board_stats 供成本估算/CI 门禁 | 本仓库 |
| gerber info/export png/diff | `cli/command_gerber_*.h` | ❌ | ❌ | 制造 QA：验证 Gerber 层数/预览/比对 | 本仓库 |
| sch import（离线导入 Altium等） | `cli/command_sch_import.cpp` | ❌ | ⚠️(GUI) | 本仓库用 kicad-cli sch import 统一格式 | 本仓库 |
| import（顶层自动建工程） | `cli/command_import.cpp` | ❌ | ❌ | 新增 import_project 一步导入板+原理图 | 本仓库 |
| pcb/sym/fp upgrade（schema 升级） | `cli/command_*_upgrade.cpp` | ⚠️(测试用) | ❌ | 新增 upgrade_schematic/board 规范化 S-expr | 本仓库 |
| api-server（无 GUI 启 IPC） | `cli/command_api_server.cpp` | ❌ | ❌ | CI/Docker 用 CLI 启 IPC，实现 headless 实时编辑 | 两者 |
| pcb drc（离线 DRC） | `cli/command_pcb_drc.cpp` | ✅ | ❌ | 华秋直接封装补齐最大短板 | 华秋急需 |
| sch erc（离线 ERC） | `cli/command_sch_erc.cpp` | ✅ | ⚠️(GUI) | 华秋增加 CLI 回退 | 华秋 |
| pcb export gerbers/drill/pos 全套 | `cli/command_pcb_export_*.h` | ✅(部分SWIG) | ❌ | 废弃 SWIG 路径统一走 CLI | 本仓库优化 |
| 扩展 3D 格式（glb/stl/brep/3dpdf等） | `cli/command_pcb_export_3d.h` | ⚠️(STEP/VRML) | ❌ | 按需扩展，GLB/STL 适合 Web 预览 | 本仓库 |
| fp/sym export svg（库渲染） | `cli/command_*_export_svg.h` | ❌ | ❌ | 库预览工具，JLCPCB 选型展示封装 | 本仓库 |

**核心价值**：kicad-cli 不替代交互编辑（SWIG/IPC），而是"离线验证+制造交付+CI 编排"标准后端。本仓库已接约 60% 但 SWIG/CLI 双轨冗余；华秋几乎未接，通过 kicad-cli 可最低成本补齐 DRC/导出/离线 ERC 而不改 GUI 遥控定位。

---

### 领域 4：DRC/ERC/敷铜/布线器核心引擎（[核心引擎评估](e6130adb-1062-4110-816d-900d5ad63aed)）

| 引擎能力 | KiCad 源码位置 | 本仓库 | 华秋 | 优化建议 | 适用 |
|---------|---------------|:------:|:----:|---------|:----:|
| DRC 全量检查（80+ 违规类型） | `pcbnew/drc/drc_item.h`、29 个 drc_test_provider | ✅执行/⚠️规则20% | ❌ | 扩展 .kicad_dru 写入器支持 netclass/差分/长度 | 本仓库 |
| 全局设计规则（15+ 参数） | `pcbnew/board_design_settings.h` | ✅ | ❌ | 补 copperEdgeClearance/silkClearance 的 set 路径 | 本仓库 |
| 自定义 DRC 规则（.kicad_dru DSL） | `pcbnew/drc/drc_rule.h` | ⚠️(4种per-layer) | ❌ | 新增 write_custom_drc_rule 支持 condition/length/skew | 本仓库 |
| 网络类规则（含 tuning_profile） | `pcbnew/netclass.h` | ⚠️(8字段,无tuning) | ❌ | 暴露 tuning_profile 绑定 | 本仓库 |
| 匹配长度/偏斜/差分对 DRC | `drc_test_provider_matched_length.cpp` | ⚠️(可检不可配) | ❌ | 通过 .kicad_dru 或 tuning_profiles 写入 | 本仓库 |
| 阻抗/Tuning Profile | `project/tuning_profiles.h` | ❌ | ❌ | 新增 set_tuning_profile 写 .kicad_pro | 本仓库 |
| **PNS Push-and-Shove 交互布线** | `pcbnew/router/pns_router.h`、`pns_shove.h` | ❌ | ❌ | **最大共同短板**：SWIG/kipy 未暴露 PNS API | 华秋优先/本仓库IPC |
| 长度匹配/蛇形调谐 | `pns_meander_placer.h` | ❌ | ❌ | 需 PNS 引擎；短期用 .kicad_dru length 约束 | 两者 |
| 差分对布线（PNS placer） | `pns_diff_pair_placer.h` | ⚠️(平行直线) | ❌ | 接入 PNS_MODE_ROUTE_DIFF_PAIR | 本仓库 |
| Freerouting 自动布线 | `pcbnew/specctra*.cpp` | ✅ | ❌ | 与 PNS 互补：FR 全局，PNS 局部 | 本仓库独有 |
| 敷铜热释放/焊盘连接模式 | `zone_settings.h` ZONE_CONNECTION | ❌ | ❌ | add_zone 增加 padConnection/thermalGap/spokeWidth | 本仓库 |
| 孤岛删除/最小孤岛面积 | `zone.h` ISLAND_REMOVAL_MODE | ❌ | ❌ | add_zone 暴露 islandRemovalMode/minIslandArea | 本仓库 |
| 规则区域/Keepout | `zone.h` SetIsRuleArea | ❌ | ❌ | 新增 add_rule_area 设 keepout 标志 | 本仓库 |
| 敷铜填充引擎稳定性 | `pcbnew/zone_filler.cpp` | ⚠️(子进程隔离) | ❌ | IPC 后端优先；离线用 kicad-cli 若支持 | 本仓库 |
| ERC 全量检查（40+ 项） | `eeschema/erc/erc.cpp` | ✅(JSON) | ✅(GUI) | 统一 JSON 输出；增加 get_erc_violations 持久化 | 两者 |
| ERC 规则配置/严重级别 | `eeschema/erc/erc_settings.cpp` | ❌ | ❌ | 读写 .kicad_pro 中 erc 节点 | 本仓库 |

**覆盖率**：DRC 本仓库执行✅/规则写入~20%，华秋 0%；ERC 两者执行✅但配置均缺；敷铜本仓库~30%华秋 0%；布线器两者 PNS 均为 0%（仅几何放置）。

**最大未接入能力**：KiCad PNS 路由器（`pcbnew/router/pns_*`）— 推挤/避让/长度调谐/差分对 placer，对 AI 辅助布线价值最高，需 C++ SDK 或 IPC 层突破。

---

### 领域 5：导入导出格式扩展（[导入导出评估](ae615df6-843c-4024-8dc5-01067618ecc7)）

| 格式/能力 | KiCad 源码位置 | 本仓库 | 华秋 | 优化建议 | 适用 |
|---------|---------------|:------:|:----:|---------|:----:|
| Gerber+钻孔 | `pcbnew/plot_board_layers.cpp` | ✅(SWIG+CLI双轨) | ❌ | 华秋封装 kicad-cli；本仓库弱化 legacy 统一 CLI | 两者 |
| IPC-2581 | `pcbnew/pcb_io/ipc2581/` | ⚠️(缺variant/bomRev) | ❌ | 补齐 variant 变体 BOM | 两者 |
| ODB++ | `pcbnew/pcb_io/odbpp/` | ⚠️(缺variant/check-zones) | ❌ | 加 --check-zones、variant | 两者 |
| STEP/3D 网格 | `pcbnew/exporters/step/` | ⚠️(缺stepz/u3d/pdf) | ❌ | 扩展 export_3d_cli 格式列表 | 两者 |
| 3D 光栅渲染（PNG/JPEG） | `3d-viewer/`、`command_pcb_render.cpp` | ❌ | ❌ | 新增 export_pcb_render 用于 AI 视觉审板 | 两者 |
| PCB 层 PNG 导出 | `plot_board_layers.cpp` PLOT_FORMAT::PNG | ❌ | ❌ | 新增 export_pcb_png（dpi/层选/B&W） | 两者 |
| 原理图 BOM（高级） | `eeschema/eeschema_jobs_handler.cpp` | ✅(export_sch_bom完整) | ❌ | 废弃 legacy export_bom，默认 export_sch_bom | 本仓库整合 |
| Python BOM 模板链 | eeschema pythonbom | ✅ | ❌ | 华秋一键封装 | 两者 |
| 网表多格式 | `eeschema/netlist_exporter_*.cpp` | ✅ | ✅(GUI) | 华秋 CLI 封装替代 GUI | 华秋 |
| PCB 多格式导入 | `pcbnew/pcb_io/pcb_io_mgr.h` | ✅(import_pcb) | ❌(仅Eagle) | 华秋复用 kicad-cli pcb import | 华秋 |
| **原理图多格式导入** | `eeschema/sch_io/sch_io_mgr.h` | ❌(仅Eagle自研) | ⚠️(GUI) | **新增 import_sch 封装 CLI**（Altium/LTspice/OrCAD/EasyEDA等10种） | 两者 |
| HPGL | `eeschema/sch_plotter.cpp` | ⚠️(原理图) | ❌ | KiCad 10 已废弃，标记 deprecated | — |
| PostScript | `eeschema/sch_plotter.cpp` | ⚠️(原理图✅/PCB❌) | ❌ | 按需加 export_pcb_ps | 两者 |
| DXF（PCB/原理图） | plot 模块 | ✅ | ❌ | 华秋 CLI 封装 | 华秋 |
| 位置文件/Pick&Place | `pcbnew/exporters/place_file_exporter.h` | ✅ | ❌ | 统一 export_pos；华秋封装 | 华秋 |
| IPC-D-356/GenCAD | `pcbnew/exporters/` | ✅ | ❌ | 华秋按需封装 | 华秋 |
| PCB 统计报告 | `pcbnew/pcbnew_jobs_handler.cpp` stats job | ❌ | ❌ | 新增 export_pcb_stats 供 AI 设计审查 | 两者 |
| 原理图 PNG | `eeschema/sch_plotter.cpp` createPNGFiles | ❌ | ❌ | 新增 export_sch_png（dpi/页选） | 两者 |
| 符号/封装 SVG 导出 | eeschema/pcbnew symsvg/fpsvg job | ❌ | ❌ | 库文档化场景低优先级 | 两者 |

**本仓库主要遗漏**：① 3D 光栅渲染+PCB/原理图 PNG 导出（AI 审图高价值缺口）；② 原理图多格式导入（与 import_pcb 不对称）。

**华秋补齐最佳路径**：直接封装 kicad-cli（无需 GUI、可 CI、维护成本低），而非扩展 cpp_sdk。增加 KicadCliRunner 按 editor-type 路由 pcb/sch export/import。

---

## 三、综合优先级排序

### P0 — 高 ROI、低风险（1-2 周量级）

| # | 能力 | 适用 | 理由 |
|---|------|:----:|------|
| 1 | 本仓库 IPC 后端扩展：文档生命周期+设计规则+网络类+层控制+导出Job | 本仓库 | kipy 已封装，纯映射工作，让 60-70 工具走实时 IPC |
| 2 | 本仓库 SWIG 导出 → kicad-cli 统一 | 本仓库 | 消除 KiCad 版本 API 漂移，废弃 legacy export_gerber/pdf/svg/bom |
| 3 | 华秋接入 pcb drc + 制造导出全套（kicad-cli） | 华秋 | 补齐文档最大差距，不改架构 |
| 4 | 本仓库敷铜高级参数（thermal/island/keepout） | 本仓库 | SWIG ZONE API 现成，提升电源/GND 设计质量 |
| 5 | 本仓库 .kicad_dru 自定义规则写入器扩展 | 本仓库 | 已有 kicad_dru.py 基础，支持差分/长度/netclass 条件规则 |
| 6 | 两者 ERC 结果持久化（get_erc_violations 对标 DRC） | 两者 | CI/Agent 闭环，结构化 JSON |

### P1 — 高价值、中等成本（2-4 周量级）

| # | 能力 | 适用 | 理由 |
|---|------|:----:|------|
| 7 | 本仓库原理图 IPC 后端（CreateItems/UpdateItems 覆盖 27 工具） | 本仓库 | 补齐原理图实时同步，双模一致性 |
| 8 | 本仓库原理图多格式导入（kicad-cli sch import） | 本仓库 | Altium/LTspice/OrCAD/EasyEDA 迁移存量设计 |
| 9 | 两者 3D 光栅渲染 + PCB/原理图 PNG 导出 | 两者 | AI 视觉审板、文档自动化 |
| 10 | 本仓库 jobset run（批量作业链） | 本仓库 | CI 一键跑完整制造+检查流水线 |
| 11 | 两者 pcb/sch diff（PR/CI 回归） | 两者 | 设计变更审查自动化 |
| 12 | 本仓库 IPC 事务 Commit（BeginCommit/EndCommit） | 本仓库 | 批量写操作 Undo 友好 |
| 13 | 华秋 sch erc CLI 回退 + sch import CLI | 华秋 | 无 GUI 时仍可 ERC/导入 |

### P2 — 高价值但需架构决策

| # | 能力 | 适用 | 理由 |
|---|------|:----:|------|
| 14 | **PNS Push-and-Shove 交互布线**（最大共同短板） | 华秋优先/本仓库IPC | SWIG/kipy 未暴露，需 cpp_sdk 或 IPC 新命令突破 |
| 15 | 本仓库引入 cpp_sdk 第三后端（GUI 遥控补齐） | 本仓库 | 华秋 MIT 可移植，三后端并存 |
| 16 | 通用 RunAction 网关（kipy 官方 + cpp_sdk 仿） | 两者 | 一次解锁大部分未封装 GUI 能力（代价：动作名不稳定） |
| 17 | 长度匹配/蛇形调谐/差分对 PNS placer | 两者 | 高速设计刚需，依赖 PNS 引擎 |
| 18 | Tuning Profile/阻抗约束 | 本仓库 | 高速设计，写 .kicad_pro + netclass 联动 |
| 19 | api-server CLI 启动（headless 实时 IPC） | 两者 | CI/Docker 真正 headless 实时编辑 |

### P3 — 按需/低优先级

| # | 能力 | 适用 | 理由 |
|---|------|:----:|------|
| 20 | 扩展 3D 格式（GLB/STL/3DPDF/stepz/u3d） | 本仓库 | 机械协同 niche |
| 21 | PCB stats、GenCAD、IPC-D-356 暴露 | 两者 | 设计审查/测试 |
| 22 | 符号/封装 SVG 导出 | 两者 | 库文档化低需求 |
| 23 | HPGL | — | KiCad 10 已废弃，不宜投入 |
| 24 | 华秋 symbol/footprint editor MCP 实例 | 华秋 | 库编辑天花板 |

---

## 四、关键结论

1. **两种 MCP 都远未到能力天花板**：华秋 cpp_sdk 仅覆盖 500+ 动作中的约 50 个；本仓库 IPC 仅覆盖 90+ 命令中的约 25 个。

2. **互补性远大于替代性**：华秋强 GUI 遥控但工程化天花板低（私有协议无开源服务端）；本仓库强完整流程但 GUI 交互弱。最佳路径是本仓库引入 cpp_sdk 第三后端补 GUI，华秋封装 kicad-cli 补工程化。

3. **最大共同短板是 PNS Push-and-Shove 布线引擎**（`pcbnew/router/pns_*`）：两种 MCP 均仅几何放置，未触及推挤/避让/长度调谐/差分对 placer，这是 AI 辅助布线价值最高的未接入能力，需 C++ SDK 或 IPC 层突破。

4. **kicad-cli 是被低估的第三后端**：无需 GUI/SWIG/IPC，是 CI/Docker/批处理唯一可靠路径。本仓库已接约 60% 但 SWIG/CLI 双轨冗余需统一；华秋几乎未接，通过 kicad-cli 可最低成本补齐 DRC/导出/离线 ERC。

5. **本仓库 IPC 后端扩展可行性最高**：kipy 已封装 Protobuf，从 25 命令扩到 90+ 主要是映射工作，可让 60-70 个现有工具走实时 IPC，原理图实时同步+导出 Job 迁移价值最高。

6. **华秋补齐制造能力的最佳路径是封装 kicad-cli 而非扩展 cpp_sdk**：cpp_sdk 适合 GUI 遥控，制造导出用 CLI 更稳且可 CI；两者并存——华秋守 GUI 交互，CLI 守自动化交付。

---

## 附：三后端架构建议（本仓库演进方向）

```
MCP Client
   │ stdio
   ▼
Node.js MCP Server (TS) ── tools / resources / prompts
   │ JSON-RPC over STDIO
   ▼
python/kicad_interface.py ── Backend Factory
   │
   ├── SWIGBackend     ── pcbnew 文件 IO      （离线/CI/制造，默认）
   ├── IPCBackend      ── kipy 官方 Protobuf   （实时同步，KiCad 运行时，扩到 90+ 命令）
   └── CppSdkBackend   ── pynng 华秋私有通道   （GUI 遥控补充，KiCad 10 运行时，可选）
                            + kicad-cli 子进程  （验证/导出/CI 编排，贯穿三后端）
```

分工：SWIG 守离线编辑与制造交付；kipy 守稳定数据面与实时同步；cpp_sdk 补 GUI 遥控（对话框/面板/缩放/Spice）；kicad-cli 贯穿全程负责验证与 CI 编排。
