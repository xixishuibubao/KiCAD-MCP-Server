# 华秋 kicad-mcp 与本仓库（KiCAD-MCP-Server）对比分析

> 对比对象
> - **华秋版**：`C:\Program Files\KiCad\10.0\bin\kicad-mcp`（PyPI 包 `kicad-mcp` v0.1.6，作者 Ethan Chien，仓库 Huaqiu-Electronics/kicad-mcp）
> - **本仓库**：`KiCAD-MCP-Server`（TypeScript + Python 混合，v2.2.3）
>
> 生成日期：2026-08-01

---

## 1. 总体定位

| 维度 | 华秋 kicad-mcp | 本仓库 KiCAD-MCP-Server |
|------|----------------|--------------------------|
| 一句话定位 | KiCad GUI 的"远程遥控器" | 端到端 PCB 设计自动化平台 |
| 设计哲学 | 驱动运行中的 KiCad 界面操作 | 离线文件操作 + 实时 UI 双模 |
| 目标用户 | 在 KiCad 界面里配合 AI 做交互式编辑 | 全流程自动化（建工程→原理图→PCB→导出→选型→布线） |
| 是否需 KiCad 运行 | **必须**运行，按 PID 发现进程 | 可不运行（SWIG 文件级），运行时走 IPC 实时同步 |

---

## 2. 技术架构

### 华秋版（纯 Python，单层）

```
MCP Client (Claude/VSCode/Cherry Studio)
        │ stdio
        ▼
FastMCP (mcp[cli] 1.3+)  ──  typechat + OpenAI（意图解析）
        │
        ▼
KiCadClient  ── pynng (NNG Req0)
        │  ipc://kicad_sdk_pair-{pid}-{editor}
        ▼
运行中的 KiCad C++ SDK（内置 IPC 服务端）
```

- 单进程、单语言，`uvx kicad-mcp --editor-type schematic` 即可运行
- 按 `--editor-type` 分实例（schematic / pcb / symbol / footprint），每个实例独占一个 socket
- 通过 `psutil` 扫描 `kicad.exe/pcbnew.exe/eeschema.exe` 进程 PID 拼接 socket URL
- 所有工具最终走 `cpp_sdk_action(api_name, params)` 调 KiCad C++ SDK 接口

### 本仓库（TS 前端 + Python 后端，双层）

```
MCP Client
   │ stdio (JSON-RPC)
   ▼
Node.js MCP Server (TypeScript)  ── tools / resources / prompts
   │ spawn + JSON-RPC over STDIO
   ▼
python/kicad_interface.py
   │
   ├── IPCBackend  ── kipy（官方 kicad-python，Protobuf over UNIX socket）→ 运行中的 KiCad
   └── SWIGBackend ── pcbnew Python 绑定 → 直接读写 .kicad_pcb 文件
```

- 前端 TypeScript 处理 MCP 协议、工具注册、资源/提示原语
- 后端 Python 执行实际 KiCad 操作，**双后端自动切换**：IPC 优先，不可用时回退 SWIG
- SWIG 后端可在 KiCad 未运行时离线操作文件，改完自动保存

---

## 3. 与 KiCad 的通信方式（核心差异）

| 项 | 华秋版 | 本仓库 |
|----|--------|--------|
| 传输库 | `pynng`（NNG） | `kipy` / `kicad-python`（官方）+ `pcbnew` SWIG |
| 协议 | KiCad C++ SDK JSON（`cmd`/`params`） | Protobuf over UNIX socket（IPC）+ Python 对象 API（SWIG） |
| Socket 定址 | `ipc://kicad_sdk_pair-{pid}-{editor}`，按 PID+editor | 由 kipy 自动发现（IPC）/ 直接文件 IO（SWIG） |
| 实时 UI 同步 | ✅ 原生（直发 GUI 命令） | ✅ IPC 后端支持；SWIG 后端需手动 reload |
| 离线操作 | ❌ 无 KiCad 即不可用 | ✅ SWIG 后端完整离线 |
| 回退机制 | 无（连不上即失败） | IPC→SWIG 自动降级 |
| 连接超时控制 | pynng 30s 收发超时 | IPC 连接 5s 硬上限，超时快速回退 SWIG |

> 注：两者都依赖 KiCad 的 IPC 能力，但华秋走的是 **C++ SDK 私有 socket**（按 editor 分通道），本仓库走的是 **官方 kipy 公共 API**。前者更贴近 GUI 动作，后者更稳定且跨版本。

---

## 4. 工具规模与覆盖

### 数量对比

| | 华秋版 | 本仓库 |
|---|--------|--------|
| 工具总数 | **76** | **122** |
| 类别数 | 3（common/schematic/pcb） | **16** |
| MCP 原语 | 仅 `tools` | `tools` + `resources` + `prompts` |

### 华秋版 76 个工具分布

- **common_tools（25）**：GUI 框架控制（openFrame/closeFrame/saveFrame/saveAs）、对话框（打印/绘图/页面设置/查找替换）、面板切换（属性/搜索/层级/网络导航/设计块）、视图缩放、图元绘制（圆/弧/贝塞尔/矩形）、选择/删除
- **schematic_tools（30）**：放置符号、画线/总线、层级页、各类标签（本地/全局/层级/类）、文本框/表格/文本、符号库查询/创建/引脚、移动/旋转/改值/改位号、导入非 KiCad 原理图/矢量图、导出网表、ERC、Spice 仿真、总线语法帮助
- **pcb_tools（21）**：走线/过孔/焊盘创建、焊盘移动/旋转/改编号/改尺寸/改钻孔/改形状/改位置、层名查询、封装信息查询/移动/改位号/设位置/旋转

### 本仓库 122 个工具 / 16 类别

| 类别 | 数量 | 说明 |
|------|------|------|
| Project Management | 5 | 创建/打开/保存/信息/快照 |
| Board Setup | 12 | 尺寸/外框/层/安装孔/敷铜/文本/2D 视图/SVG 导入 |
| Component Placement | 16 | 放置/移动/旋转/删除/编辑/查找/焊盘/阵列/对齐/复制 |
| Routing | 13 | 走线/过孔/焊盘到焊盘/差分对/网络类/复制布线模式 |
| Design Rules / DRC | 8 | 设置/获取规则、DRC、网络类、间距检查 |
| Export | 8 | Gerber/PDF/SVG/3D/BOM/网表/位置文件/VRML |
| Schematic | 27 | 元件/连线/网络标签/连接/ERC/导出/同步到板 |
| Footprint Libraries | 4 | 列表/搜索/浏览/信息 |
| Symbol Libraries | 4 | 列表/搜索/浏览/信息 |
| Footprint Creator | 4 | 自建封装/编辑焊盘/注册库 |
| Symbol Creator | 4 | 自建符号/注册库 |
| Datasheet Tools | 2 | LCSC 数据手册富化 |
| JLCPCB Integration | 5 | 本地库/搜索/详情/统计/替代料 |
| Freerouting | 4 | 自动布线/DSN 导出/SES 导入/可用性检查 |
| UI Management | 2 | 检查/启动 KiCad |
| Router Tools | 4 | 类别浏览/工具搜索/执行 |

### 覆盖差异要点

- **华秋独有的 GUI 驱动能力**：打开/关闭/保存对话框、面板切换、视图缩放、图元绘制（圆/弧/贝塞尔/矩形）、Spice 仿真、查找替换、导入矢量图/非 KiCad 原理图——这些是"操作界面"的工具，本仓库基本没有
- **本仓库独有的工程化能力**：工程创建、DRC、Gerber/3D/BOM/位置文件导出、JLCPCB 选型与本地数据库、Freerouting 自动布线、数据手册富化、封装/符号自建、层级原理图、网络类、敷铜——这些是"完整设计流程"的工具，华秋没有
- **重合区**：原理图元件放置/连线/标签、PCB 走线/过孔/焊盘/封装移动旋转——但本仓库走 SWIG 文件级，华秋走 GUI 实时

### 功能对照矩阵（逐项）

> 图例：✅ 支持 / ⚠️ 部分 / ❌ 无

#### A. 工程与项目管理

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| 新建工程（.kicad_pro + sch + pcb） | ❌ | ✅ | 本仓库可一键建工程并写入正确 schema 版本 |
| 打开/保存工程 | ⚠️ 仅 saveFrame/saveAsFrame（GUI） | ✅ | 本仓库 open/save/save_as 独立命令 |
| 工程信息查询 | ❌ | ✅ | get_project_info / snapshot_project |
| 工程脏标记/丢弃重载 | ❌ | ✅ | is_dirty / discard_or_reload |
| 板尺寸/原点设置 | ❌ | ✅ | set_board_size / set_board_origin |

#### B. 原理图 — 元件与符号

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| 放置符号 | ✅ place_symbol | ✅ add_schematic_component | 华秋走 GUI 实时 |
| 移动/旋转符号 | ✅ | ✅ | 两者均有 |
| 改元件值/位号 | ✅ modify_symbol_value/reference | ✅ edit_schematic_component | |
| 删除元件 | ❌ | ✅ delete_schematic_component | |
| 查询符号引脚 | ✅ query_symbol_pin | ✅ get_schematic_pin_locations | |
| 符号库查询/浏览 | ✅ query_symbol_library | ✅ list_symbol_libraries/search_symbols | |
| 创建符号库/符号/引脚 | ✅ create_symbol_library/pin | ✅ create_symbol + symbol_creator | 本仓库更完整 |
| 从库更新符号 | ❌ | ✅ update_symbol_from_library | |
| 批量加元件/连线 | ❌ | ✅ batch_add_components/batch_connect | 本仓库支持批量 |

#### C. 原理图 — 连线与标签

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| 画线/总线 | ✅ draw_multi_wires/buses | ✅ add_schematic_wire | |
| 本地/全局/层级标签 | ✅ | ✅ add_schematic_net_label/hierarchical_label | |
| 类标签 | ✅ create_class_label | ❌ | 华秋独有 |
| 放置网络标签（批量） | ✅ place_all_net_labels | ✅ add_schematic_net_label | |
| 层级页/层级引脚 | ✅ create_hier_sheet | ✅ add_hierarchical_sheet/add_sheet_pin | |
| 不连接标记 | ❌ | ✅ add_no_connect | |
| 连接性查询 | ❌ | ✅ get_net_connections/get_wire_connections | |

#### D. 原理图 — 文本与图元

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| 文本框/表格/普通文本 | ✅ create_textbox/table/common_text | ✅ add_schematic_text | 华秋支持表格，本仓库无表格 |
| 图元绘制（圆/弧/贝塞尔/矩形） | ✅ draw_circle/arc/bezier/rectangle | ❌ | **华秋独有** |
| 文本字段自动布局 | ❌ | ✅ autoplace_schematic_fields | |
| 原理图美化/去乱 | ❌ | ✅ suggest_schematic_declutter/lint | |

#### E. 原理图 — 检查与导入导出

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| ERC 检查 | ✅ runERCCheck | ✅ run_erc | |
| Spice 仿真 | ✅ showSpiceSimulator | ❌ | **华秋独有** |
| 导入非 KiCad 原理图 | ✅ importNonKicadSchematic | ❌ | **华秋独有** |
| 导入矢量图（SVG） | ✅ importVectorGraphicsFile | ⚠️ PCB 端有 import_svg_logo | 原理图端华秋独有 |
| 导出网表 | ✅ exportNetlist | ✅ export_netlist/generate_netlist | |
| 导出原理图 PDF/SVG/DXF | ❌ | ✅ export_sch_pdf/svg/dxf | **本仓库独有** |
| 同步原理图到 PCB | ❌ | ✅ sync_schematic_to_board/create_board_from_schematic | **本仓库独有** |
| 网表到板/ERC→板联动 | ❌ | ✅ | |

#### F. PCB — 元件与封装

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| 放置元件 | ❌ | ✅ place_component | 本仓库独有 |
| 移动/旋转/删除元件 | ⚠️ 移动/旋转封装 | ✅ 全 | 本仓库含删除/编辑/查找 |
| 批量移动/阵列/对齐/复制 | ❌ | ✅ batch_move/array/align/duplicate | **本仓库独有** |
| 封装信息查询 | ✅ query_pcb_footprint_info | ✅ get_component_properties/get_component_list | |
| 移动/旋转/改位号/设位置 | ✅ | ✅ | |
| 替换封装 | ❌ | ✅ replace_component | |
| 分组 | ❌ | ✅ group_components | |
| 焊盘创建 | ✅ create_pcb_pad | ⚠️ 通过封装创建器 | 华秋可独立建焊盘 |
| 焊盘移动/旋转/改编号/尺寸/钻孔/形状/位置 | ✅ 全套 | ⚠️ 封装创建器内 edit_footprint_pad | **华秋焊盘操作更细** |
| 查询层名 | ✅ query_pcb_layer_names | ✅ get_layer_list | |
| 查询焊盘位置/几何 | ❌ | ✅ get_component_pads/get_pad_position/get_component_geometry | |

#### G. PCB — 布线

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| 创建走线 | ✅ create_pcb_track | ✅ route_trace/route_pad_to_pad | |
| 创建过孔 | ✅ create_pcb_via | ✅ add_via | |
| 圆弧走线 | ❌ | ✅ route_arc_trace | 本仓库独有 |
| 差分对走线 | ❌ | ✅ route_differential_pair | **本仓库独有** |
| 修改/删除走线 | ❌ | ✅ modify_trace/delete_trace | |
| 查询走线 | ❌ | ✅ query_traces | |
| 复制布线模式 | ❌ | ✅ copy_routing_pattern | **本仓库独有** |
| GND 打桩过孔 | ❌ | ✅ add_gnd_stitching_vias | **本仓库独有** |
| 网络类创建/分配 | ❌ | ✅ create_netclass/assign_net_to_class | **本仓库独有** |
| 添加网络 | ❌ | ✅ add_net | |
| 网络列表/飞线/连接 | ❌ | ✅ get_nets_list/get_ratsnest/estimate_airwire_lengths | |

#### H. PCB — 板设置与敷铜

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| 板外框 | ❌ | ✅ add_board_outline/replace/clear | |
| 安装孔 | ❌ | ✅ add_mounting_hole | |
| 敷铜区 | ❌ | ✅ add_zone/refill_zones/query_zones | **本仓库独有** |
| 添加层 | ❌ | ✅ add_layer/set_active_layer | |
| 板文本 | ❌ | ✅ add_board_text | |
| 2D 视图截图 | ❌ | ✅ get_board_2d_view | |
| SVG 导入做 Logo | ❌ | ✅ import_svg_logo | |
| 板范围查询 | ❌ | ✅ get_board_extents | |

#### I. 设计规则与 DRC

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| 设置/获取设计规则 | ❌ | ✅ set/get_design_rules | **本仓库独有** |
| 运行 DRC | ❌ | ✅ run_drc/get_drc_violations | **本仓库独有** |
| 层约束/间距检查 | ❌ | ✅ set_layer_constraints/check_clearance | |
| 布局间距检查 | ❌ | ✅ check_placement_clearance/check_courtyard_overlaps | |

#### J. 导出（制造文件）

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| Gerber | ❌ | ✅ export_gerber/gerbers/single | **本仓库独有** |
| 钻孔文件 | ❌ | ✅ export_drill | |
| PDF（PCB/原理图） | ❌ | ✅ export_pcb_pdf/export_sch_pdf | |
| SVG | ❌ | ✅ export_svg/export_pcb_svg/export_sch_svg | |
| 3D / VRML | ❌ | ✅ export_3d/export_3d_cli/export_vrml | |
| BOM | ❌ | ✅ export_bom/export_sch_bom/python_bom | |
| 网表 | ✅ exportNetlist | ✅ export_netlist | |
| 位置文件 | ❌ | ✅ export_position_file/export_pos | |
| IPC-2581 / ODB / IPC-D-356 / GenCAD | ❌ | ✅ 全套 | **本仓库独有** |
| DXF（PCB/原理图） | ❌ | ✅ export_pcb_dxf/export_sch_dxf | |

#### K. 库管理

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| 封装库列表/搜索/浏览/信息 | ❌ | ✅ list_footprint_libraries/search_footprints/list_library_footprints/get_footprint_info | |
| 符号库列表/搜索/浏览/信息 | ✅ query_symbol_library | ✅ list_symbol_libraries/search_symbols | |
| 动态符号加载 | ❌ | ✅ dynamic_symbol_loader | |
| 创建封装/3D 模型 | ❌ | ✅ create_footprint/add_footprint_3d_model/import_3d_model | **本仓库独有** |
| 注册封装/符号库 | ✅ create_symbol_library | ✅ register_footprint_library/register_symbol_library | |

#### L. 供应链与外部集成

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| JLCPCB 元件库下载/搜索/详情/统计/替代料 | ❌ | ✅ 全套（2.5M+ 元件） | **本仓库独有** |
| LCSC 数据手册富化/URL | ❌ | ✅ enrich_datasheets/get_datasheet_url | **本仓库独有** |
| parts-registry 下载/查询 | ❌ | ✅ search_parts_registry/get_registry_part | |
| Freerouting 自动布线 | ❌ | ✅ autoroute/export_dsn/import_ses/check_freerouting | **本仓库独有** |
| Eagle 工程导入 | ❌ | ✅ import_eagle_project | **本仓库独有** |
| PCB 导入 | ❌ | ✅ import_pcb | |

#### M. GUI 遥控与界面操作

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| 打开/关闭/保存框架 | ✅ openFrame/closeFrame/saveFrame/saveAsFrame | ❌ | **华秋独有** |
| 页面设置/打印/绘图对话框 | ✅ openPageSettingDlg/openPrintDlg/openPlotDlg | ❌ | **华秋独有** |
| 查找/查找替换对话框 | ✅ openFindDialog/openFindAndReplaceDialog | ❌ | **华秋独有** |
| 面板切换（属性/搜索/层级/网络导航/设计块） | ✅ 5 个 toggle | ❌ | **华秋独有** |
| 视图缩放 | ✅ zoomView | ❌ | **华秋独有** |
| 选择全部/取消选择/删除工具 | ✅ selectAllItems/unSelectAllItems/deleteTool | ❌ | **华秋独有** |
| 编辑文本/图形属性对话框 | ✅ openEditTextAndGraphicPropertyDialog | ❌ | **华秋独有** |
| 打开原理图设置对话框 | ✅ openSchematicSetupDlg | ❌ | **华秋独有** |
| 打开符号库浏览器 | ✅ openSymbolLibraryBrowser | ❌ | **华秋独有** |
| 总线语法帮助 | ✅ showBusSyntaxHelp | ❌ | **华秋独有** |
| 检查/启动 KiCad UI | ❌ | ✅ check_kicad_ui/launch_kicad_ui | 本仓库独有 |

#### N. 智能与意图

| 功能 | 华秋版 | 本仓库 | 备注 |
|------|:------:|:------:|------|
| LLM 意图解析（typechat） | ✅ | ❌ | 华秋内置，本仓库留给客户端 |
| 向量检索（chromadb） | ✅ | ❌ | |
| 布局建议 | ❌ | ✅ suggest_placement | 本仓库独有 |
| 原理图去乱建议 | ❌ | ✅ suggest_schematic_declutter | |

### 功能差异小结

- **华秋独有（约 20 项，集中在 GUI 遥控 + 原理图图元/表格/Spice/导入）**：对话框与面板操控、视图缩放、图元绘制（圆/弧/贝塞尔/矩形）、表格、Spice 仿真、导入非 KiCad 原理图与矢量图、焊盘细粒度操作、类标签
- **本仓库独有（约 80+ 项，集中在完整设计流程 + 供应链 + 制造导出）**：工程创建、DRC、敷铜、网络类、差分对、圆弧走线、复制布线、GND 打桩、Gerber/钻孔/BOM/3D/IPC-2581/ODB 全套制造导出、JLCPCB 选型与本地库、LCSC 数据手册、Freerouting 自动布线、Eagle 导入、封装/符号自建、层级原理图、批量操作、布局建议
- **两者重合（约 15 项）**：符号放置/移动/旋转/改值改位号、连线/总线、各类标签、走线/过孔、封装移动旋转、ERC、网表导出、符号库查询

> 一句话：**华秋强在"操作 KiCad 界面"，本仓库强在"完成 PCB 设计全流程"**。华秋适合在 GUI 里交互编辑，本仓库适合离线/批处理/制造交付。

---

## 5. 依赖与技术栈

| | 华秋版 | 本仓库 |
|---|--------|--------|
| 运行时 | Python 3.11+ | Node.js 18+ & Python 3.10+ |
| 包管理 | `uv`（uv.lock） | pnpm（前端）+ pip（后端） |
| 分发 | `uvx kicad-mcp`（PyPI 即取即用） | 源码 clone + 构建 + 配置 mcp.json |
| MCP SDK | `mcp[cli]>=1.3.0` (FastMCP) | `@modelcontextprotocol/sdk` (TS) |
| KiCad 通信 | `pynng` | `kicad-python` (kipy) + `pcbnew` SWIG |
| LLM 集成 | ✅ `typechat` + `langchain` + `chromadb`（意图解析/向量） | ❌ 无（纯工具执行） |
| 其他重依赖 | beautifulsoup4、httpx、psutil | express（HTTP 模式可选） |

> 华秋引入了 langchain + chromadb + typechat 一整套 LLM/向量栈，体量更重；本仓库保持轻量，把"智能"留给 MCP 客户端。

---

## 6. 部署与配置

### 华秋版

```json
{
  "mcpServers": {
    "Kicad-Schematic-MCP": {
      "command": "uvx",
      "args": ["kicad-mcp", "--editor-type", "schematic"]
    },
    "Kicad-PCB-MCP": {
      "command": "uvx",
      "args": ["kicad-mcp", "--editor-type", "pcb"]
    }
  }
}
```

- 一行 `uvx` 即装即用，无需 clone 源码
- 需配置多个 server 实例对应不同 editor
- 需 KiCad 运行且启用 IPC

### 本仓库

```json
{
  "mcpServers": {
    "kicad": {
      "command": "node",
      "args": ["C:\\path\\to\\KiCAD-MCP-Server\\dist\\index.js"],
      "env": {
        "KICAD_PYTHON": "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe",
        "PYTHONPATH": "C:\\Program Files\\KiCad\\10.0\\bin\\Lib\\site-packages"
      }
    }
  }
}
```

- 需 `pnpm install && pnpm build` 产出 `dist/`
- 单 server 实例覆盖全部能力，后端自动选 IPC/SWIG
- 环境变量较多（Python 路径、PYTHONPATH、日志级别等）

---

## 7. 优劣势总结

### 华秋 kicad-mcp 的优势

- **零安装**：`uvx` 一键运行，随 KiCad 10.0 内置分发
- **GUI 遥控强**：能开/关对话框、切面板、缩放、画图元，交互式编辑体验好
- **实时性原生**：直连 C++ SDK，操作即时反映到界面
- **LLM 意图解析**：typechat + langchain 可把自然语言转结构化 API 调用

### 华秋的劣势

- **强依赖 KiCad 运行**：不启动 KiCad 完全不可用
- **无工程级流程**：缺工程创建、DRC、导出、选型、自动布线
- **无离线/批处理**：无法在无界面环境跑脚本化设计
- **重依赖**：langchain/chromadb 拖慢首启
- **按 editor 分实例**：跨原理图+PCB 协同需配两个 server

### 本仓库的优势

- **流程完整**：从建工程到 Gerber/BOM/JLCPCB 选型一条龙
- **离线可用**：SWIG 后端无需 KiCad 运行，适合 CI/批处理
- **双后端容错**：IPC 失败自动回退 SWIG，稳定性高
- **MCP 全原语**：tools + resources + prompts，客户端可富化交互
- **跨平台**：Linux/Windows/macOS 均验证

### 本仓库的劣势

- **部署重**：需 clone + 构建 + 配环境变量，门槛高
- **GUI 遥控弱**：不能驱动对话框/面板/缩放等界面操作
- **无 LLM 集成**：纯工具执行，意图理解完全靠客户端
- **IPC 后端实验性**：仅 21 命令实现实时同步，其余走 SWIG 需手动 reload

---

## 8. 互补与借鉴建议

1. **GUI 遥控工具可借鉴华秋**：本仓库可考虑引入 `openFrame/closeFrame/zoomView/togglePanel` 等工具，补齐"操作界面"短板（需 IPC 后端扩展）
2. **C++ SDK socket 通道值得评估**：华秋的 `cpp_sdk_action` 通道能做 kipy 未暴露的 GUI 动作，可作为本仓库 IPC 后端的高级补充
3. **分发可借鉴 uvx**：本仓库若能发布 npm 包或提供 `npx` 一键运行，可大幅降低部署门槛
4. **华秋可借鉴本仓库的工程化**：DRC、导出、JLCPCB、Freerouting 等是华秋缺失的硬实力
5. **两者并非替代关系**：华秋适合"在 KiCad 里配 AI 做交互"，本仓库适合"脱离 KiCad 跑自动化流程"，可并存使用

---

## 附：华秋版源码文件清单

```
kicad-mcp/
├── pyproject.toml          # uv 项目定义，依赖 mcp[cli]/langchain/chromadb/pynng
├── uv.lock                 # 617KB 锁文件
├── README.md
├── LICENSE                 # MIT
└── kicad_mcp/
    ├── server.py           # FastMCP("kicad-mcp") 单例
    ├── run_server.py       # 入口：解析 --editor-type，发现 PID，建 socket
    ├── kicad_client.py     # pynng Req0 客户端，cpp_sdk_action 统一调用
    ├── utils.py            # 日志/typechat LLM/进程扫描/socket URL
    ├── schema.py           # API 参数类型
    ├── valid_editors.py    # schematic/pcb/symbol/footprint
    ├── sdk_api_params.py   # 53KB 全部 API 参数 TypedDict
    ├── common_tools.py     # 25 个 GUI 框架/对话框/图元工具
    ├── schematic_tools.py  # 30 个原理图工具
    └── pcb_tools.py        # 21 个 PCB 工具
```

---

## 附：开源状态确认（2026-08-01 核实）

华秋 `kicad-mcp` 为**完全开源项目**，经 GitHub 公开 API 核实：

| 项 | 值 |
|----|-----|
| 仓库地址 | https://github.com/Huaqiu-Electronics/kicad-mcp |
| 可见性 | `public`（公开） |
| 许可证 | **MIT License**（SPDX: MIT） |
| 允许 fork | ✅ |
| 所有者 | `Huaqiu-Electronics` 组织（华秋电子官方） |
| 主语言 | Python |
| Stars / Forks | 13 / 4 |
| 创建时间 | 2026-02-08 |
| 最后推送 | 2026-04-20（v0.1.6 发布日） |
| 默认分支 | main |

**结论：**

1. **开源且可自由使用** —— MIT 是最宽松的开源协议之一，允许商用、修改、分发、私有化使用，仅需保留版权声明。
2. **源码完整可获取** —— PyPI 上的 `kicad-mcp` v0.1.6 与 GitHub 仓库源码一致；本地 `C:\Program Files\KiCad\10.0\bin\kicad-mcp` 里的 `kicad_mcp/` 即为该源码（editable 安装，`.pth` 指向源码目录）。
3. **可 fork 与贡献** —— 仓库开放 issues/PR，允许 fork。
4. **随 KiCad 10.0 内置分发** —— 华秋将此 MCP 随 KiCad 10.0 安装包分发（位于 `bin/kicad-mcp`），版权仍属华秋电子，遵循 MIT。

**对本仓库的启示：** 既然华秋版开源（MIT），本仓库若要借鉴其 GUI 遥控工具（`openFrame/closeFrame/zoomView/togglePanel/draw_circle` 等），可直接参考其 `common_tools.py` 与 `kicad_client.py` 的 `cpp_sdk_action` 通道实现，只需在衍生代码处注明来源并保留 MIT 版权声明即可。

