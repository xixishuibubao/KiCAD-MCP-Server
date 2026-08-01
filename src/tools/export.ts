/**
 * Export tools for KiCAD MCP server
 *
 * These tools handle exporting PCB data to various formats
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { logger } from "../logger.js";

// Command function type for KiCAD script calls
type CommandFunction = (command: string, params: Record<string, unknown>) => Promise<any>;

/**
 * Register export tools with the MCP server
 *
 * @param server MCP server instance
 * @param callKicadScript Function to call KiCAD script commands
 */
export function registerExportTools(server: McpServer, callKicadScript: CommandFunction): void {
  logger.info("Registering export tools");

  // ------------------------------------------------------
  // Export Gerber Tool [DEPRECATED — forwards to kicad-cli export_gerbers]
  // ------------------------------------------------------
  server.tool(
    "export_gerber",
    "[DEPRECATED] Use `export_gerbers` (kicad-cli) for the full Plot-dialog option set. This legacy wrapper now forwards to kicad-cli `pcb export gerbers` (+ `pcb export drill` when generateDrillFiles is set), reading the last SAVED .kicad_pcb, so the board must be saved before calling.",
    {
      outputDir: z.string().describe("Directory to save Gerber files"),
      layers: z
        .array(z.string())
        .optional()
        .describe("Optional array of layer names to export (default: all)"),
      useProtelExtensions: z
        .boolean()
        .optional()
        .describe("Whether to use Protel filename extensions"),
      generateDrillFiles: z.boolean().optional().describe("Whether to generate drill files"),
      generateMapFile: z.boolean().optional().describe("Whether to generate a map file"),
      useAuxOrigin: z.boolean().optional().describe("Whether to use auxiliary axis as origin"),
    },
    async ({
      outputDir,
      layers,
      useProtelExtensions,
      generateDrillFiles,
      generateMapFile,
      useAuxOrigin,
    }) => {
      logger.debug(`Exporting Gerber files to: ${outputDir} (via kicad-cli)`);
      const gerberResult = await callKicadScript("export_gerbers", {
        outputDir,
        layers,
        noProtelExt: useProtelExtensions === false,
        useDrillFileOrigin: useAuxOrigin,
        boardPlotParams: true,
      });
      let drillResult: any = null;
      if (generateDrillFiles) {
        drillResult = await callKicadScript("export_drill", { outputDir });
      }
      const result = {
        ...gerberResult,
        drill: drillResult,
        _deprecated: "Use export_gerbers (+ export_drill) for full options.",
      };

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export PDF Tool [DEPRECATED — forwards to kicad-cli export_pcb_pdf]
  // ------------------------------------------------------
  server.tool(
    "export_pdf",
    "[DEPRECATED] Use `export_pcb_pdf` (kicad-cli) for the full layer-plot option set. This legacy wrapper now forwards to kicad-cli `pcb export pdf`, reading the last SAVED .kicad_pcb, so the board must be saved before calling.",
    {
      outputPath: z.string().describe("Path to save the PDF file"),
      layers: z
        .array(z.string())
        .optional()
        .describe("Optional array of layer names to include (default: all)"),
      blackAndWhite: z.boolean().optional().describe("Whether to export in black and white"),
      frameReference: z.boolean().optional().describe("Whether to include frame reference"),
      pageSize: z
        .enum(["A4", "A3", "A2", "A1", "A0", "Letter", "Legal", "Tabloid"])
        .optional()
        .describe("Page size (ignored by kicad-cli PDF; use export_pcb_svg for page-size control)"),
    },
    async ({ outputPath, layers, blackAndWhite, frameReference, pageSize }) => {
      logger.debug(`Exporting PDF to: ${outputPath} (via kicad-cli)`);
      const result = await callKicadScript("export_pcb_pdf", {
        outputPath,
        layers,
        blackAndWhite,
        includeBorderTitle: frameReference,
        modeSingle: true,
      });
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export SVG Tool [DEPRECATED — forwards to kicad-cli export_pcb_svg]
  // ------------------------------------------------------
  server.tool(
    "export_svg",
    "[DEPRECATED] Use `export_pcb_svg` (kicad-cli) for the full layer-plot option set. This legacy wrapper now forwards to kicad-cli `pcb export svg`, reading the last SAVED .kicad_pcb, so the board must be saved before calling.",
    {
      outputPath: z.string().describe("Path to save the SVG file"),
      layers: z
        .array(z.string())
        .optional()
        .describe("Optional array of layer names to include (default: all)"),
      blackAndWhite: z.boolean().optional().describe("Whether to export in black and white"),
      includeComponents: z.boolean().optional().describe("Whether to include component outlines"),
    },
    async ({ outputPath, layers, blackAndWhite, includeComponents }) => {
      logger.debug(`Exporting SVG to: ${outputPath} (via kicad-cli)`);
      const result = await callKicadScript("export_pcb_svg", {
        outputPath,
        layers,
        blackAndWhite,
        modeSingle: true,
      });
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export 3D Model Tool [DEPRECATED — forwards to kicad-cli export_3d_cli]
  // ------------------------------------------------------
  server.tool(
    "export_3d",
    "[DEPRECATED] Use `export_3d_cli` (kicad-cli) for the full 3D option set (step/glb/stl/ply/brep/xao/vrml). This legacy wrapper now forwards to kicad-cli, reading the last SAVED .kicad_pcb, so the board must be saved before calling.",
    {
      outputPath: z.string().describe("Path to save the 3D model file"),
      format: z.enum(["STEP", "STL", "VRML", "OBJ"]).describe("3D model format"),
      includeComponents: z.boolean().optional().describe("Whether to include 3D component models"),
      includeCopper: z.boolean().optional().describe("Whether to include copper layers"),
      includeSolderMask: z.boolean().optional().describe("Whether to include solder mask"),
      includeSilkscreen: z.boolean().optional().describe("Whether to include silkscreen"),
    },
    async ({
      outputPath,
      format,
      includeComponents,
      includeCopper,
      includeSolderMask,
      includeSilkscreen,
    }) => {
      logger.debug(`Exporting 3D model to: ${outputPath} (via kicad-cli)`);
      const fmtMap: Record<string, string> = {
        STEP: "step",
        STL: "stl",
        VRML: "vrml",
        OBJ: "glb",
      };
      const result = await callKicadScript("export_3d_cli", {
        outputPath,
        format: fmtMap[format] ?? format.toLowerCase(),
        noComponents: includeComponents === false,
        includeTracks: includeCopper,
        includeZones: includeCopper,
        includeSoldermask: includeSolderMask,
        includeSilkscreen,
      });
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export BOM Tool [DEPRECATED — KiCad BOM is a schematic export]
  // ------------------------------------------------------
  server.tool(
    "export_bom",
    "[DEPRECATED] KiCad's BOM is a schematic export (`sch export bom`), not a PCB export — the PCB path lacks MPN/LCSC fields. Use `export_sch_bom` (kicad-cli) with a schematicPath. This legacy PCB-BOM wrapper is kept for compatibility but reads only footprint value/ref from the board.",
    {
      outputPath: z.string().describe("Path to save the BOM file"),
      format: z.enum(["CSV", "XML", "HTML", "JSON"]).describe("BOM file format"),
      groupByValue: z.boolean().optional().describe("Whether to group components by value"),
      includeAttributes: z
        .array(z.string())
        .optional()
        .describe("Optional array of additional attributes to include"),
    },
    async ({ outputPath, format, groupByValue, includeAttributes }) => {
      logger.debug(`Exporting BOM to: ${outputPath} (legacy PCB path)`);
      const result = await callKicadScript("export_bom", {
        outputPath,
        format,
        groupByValue,
        includeAttributes,
      });
      if (result && typeof result === "object") {
        result._deprecated =
          "PCB BOM lacks schematic fields. Prefer export_sch_bom with a schematicPath.";
      }
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export Netlist Tool
  // ------------------------------------------------------
  server.tool(
    "export_netlist",
    "Export the schematic netlist to a file using kicad-cli. Supports KiCad XML (default), Spice (for simulation), Cadstar, and OrcadPCB2 formats. Use this when you need to write a netlist file to disk — for example to produce a SPICE file for simulation or to diff against a reference. To get net/component data inline without writing a file, use generate_netlist instead.",
    {
      schematicPath: z.string().describe("Absolute path to the .kicad_sch schematic file"),
      outputPath: z.string().describe("Absolute path for the output file (e.g. /tmp/design.spice)"),
      format: z
        .enum(["KiCad", "Spice", "Cadstar", "OrcadPCB2"])
        .optional()
        .describe("Netlist format (default: KiCad)"),
    },
    async ({ schematicPath, outputPath, format }) => {
      logger.debug(`Exporting netlist to: ${outputPath}`);
      const result = await callKicadScript("export_netlist", {
        schematicPath,
        outputPath,
        format,
      });

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export Position File Tool [DEPRECATED — forwards to kicad-cli export_pos]
  // ------------------------------------------------------
  server.tool(
    "export_position_file",
    "[DEPRECATED] Use `export_pos` (kicad-cli) for the full pick-and-place option set. This legacy wrapper now forwards to kicad-cli `pcb export pos`, reading the last SAVED .kicad_pcb, so the board must be saved before calling.",
    {
      outputPath: z.string().describe("Path to save the position file"),
      format: z.enum(["CSV", "ASCII"]).optional().describe("File format (default: CSV)"),
      units: z.enum(["mm", "mil", "inch"]).optional().describe("Units to use (default: mm)"),
      side: z
        .enum(["top", "bottom", "both"])
        .optional()
        .describe("Which board side to include (default: both)"),
    },
    async ({ outputPath, format, units, side }) => {
      logger.debug(`Exporting position file to: ${outputPath} (via kicad-cli)`);
      const sideMap: Record<string, string> = { top: "front", bottom: "back", both: "both" };
      const unitsMap: Record<string, string> = { mm: "mm", inch: "in", mil: "in" };
      const result = await callKicadScript("export_pos", {
        outputPath,
        format: format ? format.toLowerCase() : undefined,
        units: units ? unitsMap[units] ?? "mm" : undefined,
        side: side ? sideMap[side] ?? side : undefined,
      });
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export VRML Tool [DEPRECATED — forwards to kicad-cli export_3d_cli]
  // ------------------------------------------------------
  server.tool(
    "export_vrml",
    "[DEPRECATED] Use `export_3d_cli` with format='vrml' (kicad-cli) for the full VRML option set (units, models-dir, models-relative). This legacy wrapper now forwards to kicad-cli, reading the last SAVED .kicad_pcb, so the board must be saved before calling.",
    {
      outputPath: z.string().describe("Path to save the VRML file"),
      includeComponents: z.boolean().optional().describe("Whether to include 3D component models"),
      useRelativePaths: z
        .boolean()
        .optional()
        .describe("Whether to use relative paths for 3D models"),
    },
    async ({ outputPath, includeComponents, useRelativePaths }) => {
      logger.debug(`Exporting VRML to: ${outputPath} (via kicad-cli)`);
      const result = await callKicadScript("export_3d_cli", {
        outputPath,
        format: "vrml",
        noComponents: includeComponents === false,
        modelsRelative: useRelativePaths,
      });
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export Gerbers Tool (kicad-cli, full option set)
  // ------------------------------------------------------
  server.tool(
    "export_gerbers",
    "Plot Gerber files for a PCB via kicad-cli, exposing the full Plot-dialog option set (X2, netlist attributes, DNP handling, soldermask subtraction, precision, drill-file origin, stored board plot settings, etc). Reads the board from disk, so it reflects the last SAVED state of the .kicad_pcb.",
    {
      outputDir: z.string().describe("Output directory for the Gerber files"),
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
      layers: z
        .array(z.string())
        .optional()
        .describe("Layers to plot, untranslated names e.g. ['F.Cu','B.Cu','Edge.Cuts']"),
      commonLayers: z
        .array(z.string())
        .optional()
        .describe("Layers to include on every plot (e.g. ['Edge.Cuts'])"),
      drawingSheet: z.string().optional().describe("Path to a drawing sheet override"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      excludeRefdes: z.boolean().optional().describe("Exclude reference designator text"),
      excludeValue: z.boolean().optional().describe("Exclude value text"),
      includeBorderTitle: z.boolean().optional().describe("Include border and title block"),
      sketchPadsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Draw pad outlines and numbers on fab layers"),
      hideDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Don't plot DNP footprint text/graphics on fab layers"),
      sketchDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Plot DNP footprints in sketch mode on fab layers"),
      crossoutDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Plot an 'X' over DNP footprint courtyards and strike out their refdes"),
      noX2: z.boolean().optional().describe("Do not use the extended X2 Gerber format"),
      noNetlist: z.boolean().optional().describe("Do not generate netlist attributes"),
      subtractSoldermask: z.boolean().optional().describe("Subtract soldermask from silkscreen"),
      disableApertureMacros: z.boolean().optional().describe("Disable aperture macros"),
      useDrillFileOrigin: z.boolean().optional().describe("Use the drill/place file origin"),
      noProtelExt: z
        .boolean()
        .optional()
        .describe("Use KiCad Gerber file extensions instead of Protel"),
      boardPlotParams: z
        .boolean()
        .optional()
        .describe("Use the Gerber plot settings already stored in the board file"),
      precision: z.number().optional().describe("Gerber coordinate precision: 5 or 6 (default 6)"),
    },
    async (args) => {
      logger.debug(`Exporting Gerbers to: ${args.outputDir}`);
      const result = await callKicadScript("export_gerbers", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export Drill Files Tool (kicad-cli)
  // ------------------------------------------------------
  server.tool(
    "export_drill",
    "Generate drill files for a PCB via kicad-cli, exposing the full Excellon/Gerber drill option set (format, drill origin, zero suppression, oval format, units, mirror-Y, minimal header, separate PTH/NPTH files, drill map + map format). Reads the last SAVED state of the .kicad_pcb.",
    {
      outputDir: z.string().describe("Output directory for the drill files"),
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
      format: z
        .enum(["excellon", "gerber"])
        .optional()
        .describe("Drill file format (default excellon)"),
      drillOrigin: z
        .enum(["absolute", "plot"])
        .optional()
        .describe("Drill coordinate origin (default absolute)"),
      excellonZerosFormat: z
        .enum(["decimal", "suppressleading", "suppresstrailing", "keep"])
        .optional()
        .describe("Excellon zero-suppression format (default decimal)"),
      excellonOvalFormat: z
        .enum(["route", "alternate"])
        .optional()
        .describe("Excellon oval hole format (default alternate)"),
      excellonUnits: z.enum(["in", "mm"]).optional().describe("Excellon output units (default mm)"),
      excellonMirrorY: z.boolean().optional().describe("Mirror the Y axis (Excellon)"),
      excellonMinHeader: z.boolean().optional().describe("Use a minimal Excellon header"),
      excellonSeparateTh: z
        .boolean()
        .optional()
        .describe("Generate independent files for NPTH and PTH holes"),
      generateMap: z.boolean().optional().describe("Generate a drill map / summary file"),
      mapFormat: z
        .enum(["pdf", "gerberx2", "ps", "dxf", "svg"])
        .optional()
        .describe("Drill map format when generateMap is set (default pdf)"),
      gerberPrecision: z
        .number()
        .optional()
        .describe("Gerber coordinate precision (5 or 6) when format=gerber"),
    },
    async (args) => {
      logger.debug(`Exporting drill files to: ${args.outputDir}`);
      const result = await callKicadScript("export_drill", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export IPC-2581 Tool (kicad-cli)
  // ------------------------------------------------------
  server.tool(
    "export_ipc2581",
    "Export the PCB in IPC-2581 format via kicad-cli. Single-file MES/CAD interchange carrying placement, nets and BOM part data inline. The bomCol* params map schematic fields to the embedded BOM columns (e.g. internal P/N, manufacturer P/N) — useful for assembly/MES imports. Reads the last SAVED state of the .kicad_pcb.",
    {
      outputPath: z.string().describe("Output .xml file path"),
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
      drawingSheet: z.string().optional().describe("Path to a drawing sheet override"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      precision: z.number().optional().describe("Coordinate precision (default 6)"),
      compress: z.boolean().optional().describe("Compress the output"),
      version: z.string().optional().describe("IPC-2581 standard version (default 'C')"),
      units: z.enum(["mm", "in"]).optional().describe("Units (default mm)"),
      bomColIntId: z
        .string()
        .optional()
        .describe("Schematic field to use for the BOM Internal Id column"),
      bomColMfgPn: z
        .string()
        .optional()
        .describe("Schematic field to use for the BOM Manufacturer Part Number column"),
      bomColMfg: z
        .string()
        .optional()
        .describe("Schematic field to use for the BOM Manufacturer column"),
      bomColDistPn: z
        .string()
        .optional()
        .describe("Schematic field to use for the BOM Distributor Part Number column"),
      bomColDist: z.string().optional().describe("Value to insert into the BOM Distributor column"),
      bomRev: z
        .string()
        .optional()
        .describe("BOM revision to use in the output file (defaults to the schematic revision)"),
      variant: z
        .array(z.string())
        .optional()
        .describe("Assembly variant name(s); use ${VARIANT} in outputPath for per-variant files"),
      timeoutSec: z.number().optional().describe("kicad-cli timeout in seconds (default 180, clamped 30-1800)"),
    },
    async (args) => {
      logger.debug(`Exporting IPC-2581 to: ${args.outputPath}`);
      const result = await callKicadScript("export_ipc2581", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export ODB++ Tool (kicad-cli)
  // ------------------------------------------------------
  server.tool(
    "export_odb",
    "Export the PCB in ODB++ format via kicad-cli. Single job archive (copper, drill, placement, components, nets, outline) widely used by CAM/MES/assembly. Reads the last SAVED state of the .kicad_pcb.",
    {
      outputPath: z.string().describe("Output file path (archive or directory per compression)"),
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
      drawingSheet: z.string().optional().describe("Path to a drawing sheet override"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      precision: z.number().optional().describe("Coordinate precision (default 2)"),
      compression: z
        .enum(["zip", "tgz", "none"])
        .optional()
        .describe("Output container/compression mode (default zip)"),
      units: z.enum(["mm", "in"]).optional().describe("Units (default mm)"),
      checkZones: z
        .boolean()
        .optional()
        .describe("Check and refill zones if required before export"),
      variant: z
        .array(z.string())
        .optional()
        .describe("Assembly variant name(s); use ${VARIANT} in outputPath for per-variant files"),
      timeoutSec: z.number().optional().describe("kicad-cli timeout in seconds (default 180, clamped 30-1800)"),
    },
    async (args) => {
      logger.debug(`Exporting ODB++ to: ${args.outputPath}`);
      const result = await callKicadScript("export_odb", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export IPC-D-356 Netlist Tool (kicad-cli)
  // ------------------------------------------------------
  server.tool(
    "export_ipcd356",
    "Generate an IPC-D-356 bare-board electrical-test netlist via kicad-cli. Consumed by flying-probe and bed-of-nails testers. Reads the last SAVED state of the .kicad_pcb.",
    {
      outputPath: z.string().describe("Output .ipc / netlist file path"),
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
    },
    async (args) => {
      logger.debug(`Exporting IPC-D-356 netlist to: ${args.outputPath}`);
      const result = await callKicadScript("export_ipcd356", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export GenCAD Tool (kicad-cli)
  // ------------------------------------------------------
  server.tool(
    "export_gencad",
    "Export the PCB in GenCAD format via kicad-cli. Assembly/test interchange format. Exposes padstack flip, unique pin/footprint shape generation, drill-file origin, and store-origin-coordinate options. Reads the last SAVED state of the .kicad_pcb.",
    {
      outputPath: z.string().describe("Output .cad file path"),
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      flipBottomPads: z.boolean().optional().describe("Flip bottom footprint padstacks"),
      uniquePins: z.boolean().optional().describe("Generate unique pin names"),
      uniqueFootprints: z
        .boolean()
        .optional()
        .describe("Generate a new shape for each footprint instance (do not reuse shapes)"),
      useDrillOrigin: z.boolean().optional().describe("Use drill/place file origin as origin"),
      storeOriginCoord: z.boolean().optional().describe("Save the origin coordinates in the file"),
    },
    async (args) => {
      logger.debug(`Exporting GenCAD to: ${args.outputPath}`);
      const result = await callKicadScript("export_gencad", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export Position File Tool (kicad-cli, full option set)
  // ------------------------------------------------------
  server.tool(
    "export_pos",
    "Generate a component placement (position / pick-and-place) file via kicad-cli, exposing the full CLI option set (side, format, units, bottom-negate-X, drill-file origin, SMD-only, exclude through-hole / DNP, gerber board edge). Rich CLI sibling of export_position_file. Reads the last SAVED state of the .kicad_pcb.",
    {
      outputPath: z.string().describe("Output position file path"),
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
      side: z
        .enum(["front", "back", "both"])
        .optional()
        .describe("Board side (gerber format only supports front or back; default both)"),
      format: z
        .enum(["ascii", "csv", "gerber"])
        .optional()
        .describe("Output format (default ascii)"),
      units: z
        .enum(["in", "mm"])
        .optional()
        .describe("Output units; ascii or csv format only (default in)"),
      bottomNegateX: z
        .boolean()
        .optional()
        .describe("Use negative X coordinates for bottom-layer footprints (ascii/csv only)"),
      useDrillFileOrigin: z
        .boolean()
        .optional()
        .describe("Use drill/place file origin (ascii/csv only)"),
      smdOnly: z.boolean().optional().describe("Include only SMD footprints (ascii/csv only)"),
      excludeFpTh: z
        .boolean()
        .optional()
        .describe("Exclude all footprints with through-hole pads (ascii/csv only)"),
      excludeDnp: z
        .boolean()
        .optional()
        .describe("Exclude all footprints with the Do Not Populate flag set"),
      gerberBoardEdge: z.boolean().optional().describe("Include board edge layer (Gerber only)"),
    },
    async (args) => {
      logger.debug(`Exporting position file to: ${args.outputPath}`);
      const result = await callKicadScript("export_pos", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export PCB PDF Tool (kicad-cli, full layer-plot option set)
  // ------------------------------------------------------
  server.tool(
    "export_pcb_pdf",
    "Plot the PCB layout to PDF via kicad-cli, exposing the full layer-plot option set (layer + common-layer lists, mirror, refdes/value exclusion, border+title, soldermask subtraction, DNP fab-layer modes, negative, black-and-white, theme, drill shape, and single/separate/multipage output modes). Rich CLI sibling of export_pdf. Reads the last SAVED state of the .kicad_pcb.",
    {
      outputPath: z.string().describe("Output PDF file path (or directory in separate mode)"),
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
      layers: z
        .array(z.string())
        .optional()
        .describe("Layers to plot, untranslated names e.g. ['F.Cu','B.Cu','Edge.Cuts']"),
      commonLayers: z
        .array(z.string())
        .optional()
        .describe("Layers to include on every plot (e.g. ['Edge.Cuts'])"),
      drawingSheet: z.string().optional().describe("Path to a drawing sheet override"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      mirror: z.boolean().optional().describe("Mirror the board (to show bottom layers)"),
      excludeRefdes: z.boolean().optional().describe("Exclude reference designator text"),
      excludeValue: z.boolean().optional().describe("Exclude value text"),
      includeBorderTitle: z.boolean().optional().describe("Include the border and title block"),
      subtractSoldermask: z.boolean().optional().describe("Subtract soldermask from silkscreen"),
      sketchPadsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Draw pad outlines and numbers on fab layers"),
      hideDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Don't plot DNP footprint text/graphics on fab layers"),
      sketchDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Plot DNP footprints in sketch mode on fab layers"),
      crossoutDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Plot an 'X' over DNP footprint courtyards and strike out their refdes"),
      negative: z.boolean().optional().describe("Plot as negative"),
      blackAndWhite: z.boolean().optional().describe("Black and white only"),
      theme: z.string().optional().describe("Color theme to use (default: PCB editor settings)"),
      drillShapeOpt: z
        .number()
        .optional()
        .describe("Pad/via drill shape option (0 none, 1 small, 2 actual; default 2)"),
      modeSingle: z
        .boolean()
        .optional()
        .describe("Single file; output path is full path; LAYER_LIST controls all layers"),
      modeSeparate: z.boolean().optional().describe("Plot the layers to individual PDF files"),
      modeMultipage: z.boolean().optional().describe("Plot the layers to a single multi-page PDF"),
    },
    async (args) => {
      logger.debug(`Exporting PCB PDF to: ${args.outputPath}`);
      const result = await callKicadScript("export_pcb_pdf", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export PCB SVG Tool (kicad-cli, full layer-plot option set)
  // ------------------------------------------------------
  server.tool(
    "export_pcb_svg",
    "Plot the PCB layout to SVG via kicad-cli, exposing the full layer-plot option set (layer + common-layer lists, mirror, soldermask subtraction, negative, black-and-white, theme, DNP fab-layer modes, page-size mode, fit-page-to-board, exclude-drawing-sheet, drill shape, single/multi output modes). Rich CLI sibling of export_svg. Reads the last SAVED state of the .kicad_pcb.",
    {
      outputPath: z.string().describe("Output SVG file path (or directory in multi mode)"),
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
      layers: z
        .array(z.string())
        .optional()
        .describe("Layers to plot, untranslated names e.g. ['F.Cu','B.Cu','Edge.Cuts']"),
      commonLayers: z
        .array(z.string())
        .optional()
        .describe("Layers to include on every plot (e.g. ['Edge.Cuts'])"),
      drawingSheet: z.string().optional().describe("Path to a drawing sheet override"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      subtractSoldermask: z.boolean().optional().describe("Subtract soldermask from silkscreen"),
      mirror: z.boolean().optional().describe("Mirror the board (to show bottom layers)"),
      negative: z.boolean().optional().describe("Plot as negative"),
      blackAndWhite: z.boolean().optional().describe("Black and white only"),
      theme: z.string().optional().describe("Color theme to use (default: PCB editor settings)"),
      sketchPadsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Draw pad outlines and numbers on fab layers"),
      hideDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Don't plot DNP footprint text/graphics on fab layers"),
      sketchDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Plot DNP footprints in sketch mode on fab layers"),
      crossoutDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Plot an 'X' over DNP footprint courtyards and strike out their refdes"),
      pageSizeMode: z
        .number()
        .optional()
        .describe("Page sizing mode (0 frame+title block, 1 current page size, 2 board area only)"),
      fitPageToBoard: z.boolean().optional().describe("Fit the page to the board"),
      excludeDrawingSheet: z.boolean().optional().describe("No drawing sheet"),
      drillShapeOpt: z
        .number()
        .optional()
        .describe("Pad/via drill shape option (0 none, 1 small, 2 actual; default 2)"),
      modeSingle: z
        .boolean()
        .optional()
        .describe("Single file; output path is full path; LAYER_LIST controls all layers"),
      modeMulti: z
        .boolean()
        .optional()
        .describe("Multi output; output path is a directory (GUI-like plotting)"),
    },
    async (args) => {
      logger.debug(`Exporting PCB SVG to: ${args.outputPath}`);
      const result = await callKicadScript("export_pcb_svg", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export PCB DXF Tool (kicad-cli, full layer-plot option set)
  // ------------------------------------------------------
  server.tool(
    "export_pcb_dxf",
    "Plot the PCB layout to DXF via kicad-cli, exposing the full layer-plot option set (layer + common-layer lists, refdes/value exclusion, soldermask subtraction, use-contours, use-drill-origin, border+title, output units, DNP fab-layer modes, drill shape, single/multi output modes). Reads the last SAVED state of the .kicad_pcb.",
    {
      outputPath: z.string().describe("Output DXF file path (or directory in multi mode)"),
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
      layers: z
        .array(z.string())
        .optional()
        .describe("Layers to plot, untranslated names e.g. ['F.Cu','B.Cu','Edge.Cuts']"),
      commonLayers: z
        .array(z.string())
        .optional()
        .describe("Layers to include on every plot (e.g. ['Edge.Cuts'])"),
      drawingSheet: z.string().optional().describe("Path to a drawing sheet override"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      excludeRefdes: z.boolean().optional().describe("Exclude reference designator text"),
      excludeValue: z.boolean().optional().describe("Exclude value text"),
      sketchPadsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Draw pad outlines and numbers on fab layers"),
      hideDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Don't plot DNP footprint text/graphics on fab layers"),
      sketchDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Plot DNP footprints in sketch mode on fab layers"),
      crossoutDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Plot an 'X' over DNP footprint courtyards and strike out their refdes"),
      subtractSoldermask: z.boolean().optional().describe("Subtract soldermask from silkscreen"),
      useContours: z.boolean().optional().describe("Plot graphic items using their contours"),
      useDrillOrigin: z.boolean().optional().describe("Plot using the drill/place file origin"),
      includeBorderTitle: z.boolean().optional().describe("Include the border and title block"),
      outputUnits: z.enum(["mm", "in"]).optional().describe("Output units (default in)"),
      drillShapeOpt: z
        .number()
        .optional()
        .describe("Pad/via drill shape option (0 none, 1 small, 2 actual; default 2)"),
      modeSingle: z
        .boolean()
        .optional()
        .describe("Single file; output path is full path; LAYER_LIST controls all layers"),
      modeMulti: z
        .boolean()
        .optional()
        .describe("Multi output; output path is a directory (GUI-like plotting)"),
    },
    async (args) => {
      logger.debug(`Exporting PCB DXF to: ${args.outputPath}`);
      const result = await callKicadScript("export_pcb_dxf", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export Single Gerber Tool (kicad-cli, full Plot option set)
  // ------------------------------------------------------
  server.tool(
    "export_gerber_single",
    "Plot the given layers to a SINGLE Gerber file via kicad-cli (`pcb export gerber`). Singular sibling of export_gerbers. Exposes the full single-file Plot option set (X2, netlist attributes, DNP fab-layer modes, soldermask subtraction, aperture macros, drill-file origin, precision, Protel extension). Reads the last SAVED state of the .kicad_pcb.",
    {
      outputPath: z.string().describe("Output Gerber file path"),
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
      layers: z
        .array(z.string())
        .optional()
        .describe("Layers to plot, untranslated names e.g. ['F.Cu','B.Cu','Edge.Cuts']"),
      commonLayers: z
        .array(z.string())
        .optional()
        .describe("Layers to include on every plot (e.g. ['Edge.Cuts'])"),
      drawingSheet: z.string().optional().describe("Path to a drawing sheet override"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      excludeRefdes: z.boolean().optional().describe("Exclude reference designator text"),
      excludeValue: z.boolean().optional().describe("Exclude value text"),
      includeBorderTitle: z.boolean().optional().describe("Include the border and title block"),
      sketchPadsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Draw pad outlines and numbers on fab layers"),
      hideDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Don't plot DNP footprint text/graphics on fab layers"),
      sketchDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Plot DNP footprints in sketch mode on fab layers"),
      crossoutDnpFootprintsOnFabLayers: z
        .boolean()
        .optional()
        .describe("Plot an 'X' over DNP footprint courtyards and strike out their refdes"),
      noX2: z.boolean().optional().describe("Do not use the extended X2 Gerber format"),
      noNetlist: z.boolean().optional().describe("Do not generate netlist attributes"),
      subtractSoldermask: z.boolean().optional().describe("Subtract soldermask from silkscreen"),
      disableApertureMacros: z.boolean().optional().describe("Disable aperture macros"),
      useDrillFileOrigin: z.boolean().optional().describe("Use the drill/place file origin"),
      noProtelExt: z
        .boolean()
        .optional()
        .describe("Use KiCad Gerber file extensions instead of Protel"),
      precision: z.number().optional().describe("Gerber coordinate precision: 5 or 6 (default 6)"),
    },
    async (args) => {
      logger.debug(`Exporting single Gerber to: ${args.outputPath}`);
      const result = await callKicadScript("export_gerber_single", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export 3D Model Tool (kicad-cli, format dispatch + full flag union)
  // ------------------------------------------------------
  server.tool(
    "export_3d_cli",
    "Export a 3D model of the PCB via kicad-cli. The `format` param selects the subcommand (step, glb, stl, ply, brep, xao, vrml); only flags valid for that subcommand are forwarded. STEP/glb/stl/ply/brep/xao share the geometry/include flag set (no-board-body, include-tracks/pads/zones/inner-copper/silkscreen/soldermask, fuse-shapes, fill-all-vias, component/net filters, min-distance, etc.; no-optimize-step is STEP-only); vrml uses units + models-dir/models-relative instead. Rich CLI sibling of export_3d and export_vrml. Reads the last SAVED state of the .kicad_pcb.",
    {
      outputPath: z.string().describe("Output 3D model file path"),
      format: z
        .enum(["step", "glb", "stl", "ply", "brep", "xao", "vrml"])
        .describe("3D output format (selects the kicad-cli subcommand)"),
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      // common to all formats
      force: z.boolean().optional().describe("Overwrite output file"),
      noUnspecified: z
        .boolean()
        .optional()
        .describe("Exclude 3D models for components with 'Unspecified' footprint type"),
      noDnp: z
        .boolean()
        .optional()
        .describe("Exclude 3D models for components with 'Do not populate' attribute"),
      userOrigin: z
        .string()
        .optional()
        .describe("User-specified output origin e.g. '1x1in', '25.4x25.4mm' (default unit mm)"),
      // mesh subcommands only (step/glb/stl/ply/brep/xao)
      gridOrigin: z.boolean().optional().describe("Use Grid Origin for output origin"),
      drillOrigin: z.boolean().optional().describe("Use Drill Origin for output origin"),
      substModels: z
        .boolean()
        .optional()
        .describe("Substitute STEP/IGS models in place of VRML models"),
      boardOnly: z.boolean().optional().describe("Only generate a board with no components"),
      cutViasInBody: z
        .boolean()
        .optional()
        .describe("Cut via holes in board body even if conductor layers not exported"),
      noBoardBody: z.boolean().optional().describe("Exclude board body"),
      noComponents: z.boolean().optional().describe("Exclude 3D models for components"),
      componentFilter: z
        .string()
        .optional()
        .describe("Only include component models matching this refdes list (comma, wildcards)"),
      includeTracks: z.boolean().optional().describe("Export tracks and vias"),
      includePads: z.boolean().optional().describe("Export pads"),
      includeZones: z.boolean().optional().describe("Export zones"),
      includeInnerCopper: z.boolean().optional().describe("Export elements on inner copper layers"),
      includeSilkscreen: z
        .boolean()
        .optional()
        .describe("Export silkscreen graphics as flat faces"),
      includeSoldermask: z.boolean().optional().describe("Export soldermask layers as flat faces"),
      fuseShapes: z.boolean().optional().describe("Fuse overlapping geometry together"),
      fillAllVias: z.boolean().optional().describe("Don't cut via holes in conductor layers"),
      minDistance: z
        .string()
        .optional()
        .describe("Min distance between points to treat as separate (default '0.01mm')"),
      netFilter: z
        .string()
        .optional()
        .describe("Only include copper items belonging to nets matching this wildcard"),
      // STEP only
      noOptimizeStep: z
        .boolean()
        .optional()
        .describe("Do not optimize STEP file (enables writing parametric curves; STEP only)"),
      // VRML only
      units: z
        .enum(["mm", "m", "in", "tenths"])
        .optional()
        .describe("Output units (VRML only; default in)"),
      modelsDir: z
        .string()
        .optional()
        .describe("Folder to store 3D models in (VRML only; empty = embed in main file)"),
      modelsRelative: z
        .boolean()
        .optional()
        .describe("Use relative model paths with modelsDir (VRML only)"),
    },
    async (args) => {
      logger.debug(`Exporting 3D model (${args.format}) to: ${args.outputPath}`);
      const result = await callKicadScript("export_3d_cli", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export PCB 3D Render Tool (kicad-cli pcb render)
  // ------------------------------------------------------
  server.tool(
    "export_pcb_render",
    "Render the PCB in 3D to a PNG or JPEG image via kicad-cli `pcb render` (ray-traced 3D view). This is the KiCad-native way to produce a board image — there is no `pcb export png`. Supports width/height, side (top/bottom/left/right/front/back), background, quality (basic/high/user/job_settings), preset, perspective, zoom/pan/pivot/rotate, light intensities, board-stackup colors and floor. Reads the last SAVED .kicad_pcb.",
    {
      outputPath: z.string().describe("Output image file path (.png or .jpg/.jpeg)"),
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      variant: z
        .array(z.string())
        .optional()
        .describe("Variant name(s); use ${VARIANT} in outputPath to emit per-variant files"),
      width: z.number().optional().describe("Image width in pixels (default 1600)"),
      height: z.number().optional().describe("Image height in pixels (default 900)"),
      side: z
        .enum(["top", "bottom", "left", "right", "front", "back"])
        .optional()
        .describe("Render side (default top)"),
      background: z
        .enum(["default", "transparent", "opaque"])
        .optional()
        .describe("Image background (default transparent for PNG, opaque for JPEG)"),
      quality: z
        .enum(["basic", "high", "user", "job_settings"])
        .optional()
        .describe("Render quality (default basic)"),
      preset: z
        .string()
        .optional()
        .describe("Appearance preset: follow_pcb_editor, follow_plot_settings, or a user preset name"),
      useBoardStackupColors: z
        .boolean()
        .optional()
        .describe("Use colors defined in the board stackup instead of the preset"),
      floor: z
        .boolean()
        .optional()
        .describe("Enable floor, shadows and post-processing even if disabled in quality"),
      perspective: z.boolean().optional().describe("Use perspective projection instead of orthogonal"),
      zoom: z.number().optional().describe("Camera zoom (default 1)"),
      pan: z
        .string()
        .optional()
        .describe("Pan camera 'X,Y,Z' e.g. '3,0,0'"),
      pivot: z
        .string()
        .optional()
        .describe("Pivot point relative to board center in cm 'X,Y,Z' e.g. '-10,2,0'"),
      rotate: z
        .string()
        .optional()
        .describe("Rotate board 'X,Y,Z' degrees e.g. '-45,0,45' for isometric"),
      lightTop: z
        .string()
        .optional()
        .describe("Top light intensity 'R,G,B' or single number 0-1"),
      lightBottom: z
        .string()
        .optional()
        .describe("Bottom light intensity 'R,G,B' or single number 0-1"),
      lightSide: z
        .string()
        .optional()
        .describe("Side lights intensity 'R,G,B' or single number 0-1"),
      lightCamera: z
        .string()
        .optional()
        .describe("Camera light intensity 'R,G,B' or single number 0-1"),
      lightSideElevation: z
        .number()
        .optional()
        .describe("Side lights elevation angle in degrees 0-90 (default 60)"),
      timeoutSec: z.number().optional().describe("kicad-cli timeout in seconds (default 300, clamped 30-1800)"),
    },
    async (args) => {
      logger.debug(`Rendering PCB 3D image to: ${args.outputPath}`);
      const result = await callKicadScript("export_pcb_render", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Get Board Stats Tool (kicad-cli pcb export stats)
  // ------------------------------------------------------
  server.tool(
    "get_board_stats",
    "Generate a board statistics report via kicad-cli `pcb export stats`: board/copper area, hole count, footprint count, net count, etc. Useful for cost estimation and CI gate checks. Output JSON (default, returned parsed) or a human-readable report. Reads the last SAVED .kicad_pcb.",
    {
      boardPath: z.string().optional().describe("Path to the .kicad_pcb (default: current board)"),
      outputPath: z
        .string()
        .optional()
        .describe("Output file path; if omitted and format=json, a temp file is used and parsed inline"),
      format: z
        .enum(["json", "report"])
        .optional()
        .describe("Output format (default json; report returns stdout text)"),
      units: z.enum(["in", "mm"]).optional().describe("Report units (default mm)"),
      excludeFootprintsWithoutPads: z
        .boolean()
        .optional()
        .describe("Exclude footprints without pads"),
      subtractHolesFromBoard: z
        .boolean()
        .optional()
        .describe("Subtract holes from the board area"),
      subtractHolesFromCopper: z
        .boolean()
        .optional()
        .describe("Subtract holes from copper areas"),
      timeoutSec: z.number().optional().describe("kicad-cli timeout in seconds (default 120, clamped 10-1800)"),
    },
    async (args) => {
      logger.debug(`Getting board stats`);
      const result = await callKicadScript("get_board_stats", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Run Jobset Tool (kicad-cli jobset run)
  // ------------------------------------------------------
  server.tool(
    "run_jobset",
    "Run a KiCad jobset (.kicad_jobset) via kicad-cli `jobset run`, executing the full job chain (DRC/ERC, Gerber/drill/PDF/3D exports, etc.) in one shot — ideal for CI/CD manufacturing delivery. INPUT_FILE is the .kicad_pro project. Reads the last SAVED project.",
    {
      projectPath: z.string().describe("Path to the .kicad_pro project file (required)"),
      jobsetFile: z
        .string()
        .optional()
        .describe("Path to a .kicad_jobset file (default: the project's stored jobset)"),
      output: z
        .string()
        .optional()
        .describe("Name of a single jobset output to generate (default: all outputs in the jobset)"),
      stopOnError: z
        .boolean()
        .optional()
        .describe("Stop processing jobs on the first failure"),
      timeoutSec: z.number().optional().describe("kicad-cli timeout in seconds (default 600, clamped 30-3600)"),
    },
    async (args) => {
      logger.debug(`Running jobset for: ${args.projectPath}`);
      const result = await callKicadScript("run_jobset", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Upgrade Schematic Tool (kicad-cli sch upgrade)
  // ------------------------------------------------------
  server.tool(
    "upgrade_schematic",
    "Upgrade a .kicad_sch file's format to the latest via kicad-cli `sch upgrade`, resaving in the current KiCad S-expression format. Use force to resave regardless of versioning. Useful to normalize older files before editing and to reduce kicad-skip compatibility issues.",
    {
      inputPath: z.string().describe("Path to the .kicad_sch file (required)"),
      force: z
        .boolean()
        .optional()
        .describe("Force resave regardless of versioning"),
      timeoutSec: z.number().optional().describe("kicad-cli timeout in seconds (default 180, clamped 15-1800)"),
    },
    async (args) => {
      logger.debug(`Upgrading schematic: ${args.inputPath}`);
      const result = await callKicadScript("upgrade_schematic", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Upgrade Board Tool (kicad-cli pcb upgrade)
  // ------------------------------------------------------
  server.tool(
    "upgrade_board",
    "Upgrade a .kicad_pcb file's format to the latest via kicad-cli `pcb upgrade`, resaving in the current KiCad S-expression format. Use force to resave regardless of versioning. Useful to normalize older files before editing and to reduce kicad-skip compatibility issues.",
    {
      inputPath: z.string().describe("Path to the .kicad_pcb file (required)"),
      force: z
        .boolean()
        .optional()
        .describe("Force resave regardless of versioning"),
      timeoutSec: z.number().optional().describe("kicad-cli timeout in seconds (default 180, clamped 15-1800)"),
    },
    async (args) => {
      logger.debug(`Upgrading board: ${args.inputPath}`);
      const result = await callKicadScript("upgrade_board", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export Schematic BOM Tool (kicad-cli, full option set)
  // ------------------------------------------------------
  server.tool(
    "export_sch_bom",
    "Generate a Bill of Materials from a schematic via kicad-cli (`sch export bom`), exposing the full option set (presets, field/label lists, grouping, sorting, filtering, DNP/excluded-from-BOM handling, and field/string/ref delimiters). schematicPath is REQUIRED.",
    {
      schematicPath: z.string().describe("Path to the .kicad_sch (required)"),
      outputPath: z.string().describe("Output BOM file path"),
      preset: z
        .string()
        .optional()
        .describe("Named BOM preset from the schematic, e.g. 'Grouped By Value'"),
      formatPreset: z
        .string()
        .optional()
        .describe("Named BOM format preset from the schematic, e.g. 'CSV'"),
      fields: z
        .string()
        .optional()
        .describe("Ordered comma list of fields to export (supports special substitutions)"),
      labels: z
        .string()
        .optional()
        .describe("Ordered comma list of labels to apply to the exported fields"),
      groupBy: z
        .string()
        .optional()
        .describe("Fields to group references by when field values match"),
      sortField: z.string().optional().describe("Field name to sort by (default Reference)"),
      sortAsc: z.string().optional().describe("Sort ascending ('true') or descending ('false')"),
      filter: z.string().optional().describe("Filter string to remove output lines"),
      excludeDnp: z.boolean().optional().describe("Exclude symbols marked Do-Not-Populate"),
      includeExcludedFromBom: z
        .boolean()
        .optional()
        .describe("Include symbols marked 'Exclude from BOM'"),
      fieldDelimiter: z
        .string()
        .optional()
        .describe("Separator between output fields/columns (default ',')"),
      stringDelimiter: z
        .string()
        .optional()
        .describe("Character to surround fields with (default '\"')"),
      refDelimiter: z
        .string()
        .optional()
        .describe("Character between individual references (default ',')"),
      refRangeDelimiter: z
        .string()
        .optional()
        .describe("Character for reference ranges; blank disables ranges (default '-')"),
      keepTabs: z.boolean().optional().describe("Keep tab characters from input fields"),
      keepLineBreaks: z
        .boolean()
        .optional()
        .describe("Keep line break characters from input fields"),
    },
    async (args) => {
      logger.debug(`Exporting schematic BOM to: ${args.outputPath}`);
      const result = await callKicadScript("export_sch_bom", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export Schematic PDF Tool (kicad-cli, full option set)
  // ------------------------------------------------------
  server.tool(
    "export_sch_pdf",
    "Export a schematic to PDF via kicad-cli (`sch export pdf`), exposing the full option set (drawing-sheet override, theme, black-and-white, exclude-drawing-sheet, default-font, the PDF property-popup / hierarchical-link / metadata excludes, no-background-color, and page selection). schematicPath is REQUIRED.",
    {
      schematicPath: z.string().describe("Path to the .kicad_sch (required)"),
      outputPath: z.string().describe("Output PDF file path"),
      drawingSheet: z.string().optional().describe("Path to a drawing sheet override"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      theme: z.string().optional().describe("Color theme to use (default: schematic settings)"),
      blackAndWhite: z.boolean().optional().describe("Black and white only"),
      excludeDrawingSheet: z.boolean().optional().describe("No drawing sheet"),
      defaultFont: z.string().optional().describe("Default font name"),
      excludePdfPropertyPopups: z
        .boolean()
        .optional()
        .describe("Do not generate property popups in PDF"),
      excludePdfHierarchicalLinks: z
        .boolean()
        .optional()
        .describe("Do not generate clickable links for hierarchical elements in PDF"),
      excludePdfMetadata: z
        .boolean()
        .optional()
        .describe("Do not generate PDF metadata from AUTHOR and SUBJECT variables"),
      noBackgroundColor: z
        .boolean()
        .optional()
        .describe("Avoid setting a background color (regardless of theme)"),
      pages: z
        .string()
        .optional()
        .describe("Comma list of page numbers to print (blank = all pages)"),
    },
    async (args) => {
      logger.debug(`Exporting schematic PDF to: ${args.outputPath}`);
      const result = await callKicadScript("export_sch_pdf", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export Schematic SVG Tool (kicad-cli, full option set)
  // ------------------------------------------------------
  server.tool(
    "export_sch_svg",
    "Export a schematic to SVG via kicad-cli (`sch export svg`), one SVG per page into a directory. Exposes drawing-sheet override, theme, black-and-white, exclude-drawing-sheet, default-font, no-background-color, and page selection. schematicPath is REQUIRED.",
    {
      schematicPath: z.string().describe("Path to the .kicad_sch (required)"),
      outputDir: z.string().describe("Output directory for the SVG files"),
      drawingSheet: z.string().optional().describe("Path to a drawing sheet override"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      theme: z.string().optional().describe("Color theme to use (default: schematic settings)"),
      blackAndWhite: z.boolean().optional().describe("Black and white only"),
      excludeDrawingSheet: z.boolean().optional().describe("No drawing sheet"),
      defaultFont: z.string().optional().describe("Default font name"),
      noBackgroundColor: z
        .boolean()
        .optional()
        .describe("Avoid setting a background color (regardless of theme)"),
      pages: z
        .string()
        .optional()
        .describe("Comma list of page numbers to print (blank = all pages)"),
    },
    async (args) => {
      logger.debug(`Exporting schematic SVG to: ${args.outputDir}`);
      const result = await callKicadScript("export_sch_svg", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export Schematic DXF Tool (kicad-cli, full option set)
  // ------------------------------------------------------
  server.tool(
    "export_sch_dxf",
    "Export a schematic to DXF via kicad-cli (`sch export dxf`), one DXF per page into a directory. Exposes drawing-sheet override, theme, black-and-white, exclude-drawing-sheet, default-font, and page selection. schematicPath is REQUIRED.",
    {
      schematicPath: z.string().describe("Path to the .kicad_sch (required)"),
      outputDir: z.string().describe("Output directory for the DXF files"),
      drawingSheet: z.string().optional().describe("Path to a drawing sheet override"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      theme: z.string().optional().describe("Color theme to use (default: schematic settings)"),
      blackAndWhite: z.boolean().optional().describe("Black and white only"),
      excludeDrawingSheet: z.boolean().optional().describe("No drawing sheet"),
      defaultFont: z.string().optional().describe("Default font name"),
      pages: z
        .string()
        .optional()
        .describe("Comma list of page numbers to print (blank = all pages)"),
    },
    async (args) => {
      logger.debug(`Exporting schematic DXF to: ${args.outputDir}`);
      const result = await callKicadScript("export_sch_dxf", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export Schematic HPGL Tool (kicad-cli, full option set)
  // ------------------------------------------------------
  server.tool(
    "export_sch_hpgl",
    "Export a schematic to HPGL via kicad-cli (`sch export hpgl`), one plot per page into a directory. Exposes drawing-sheet override, exclude-drawing-sheet, default-font, page selection, pen size, and the origin/scale mode. schematicPath is REQUIRED.",
    {
      schematicPath: z.string().describe("Path to the .kicad_sch (required)"),
      outputDir: z.string().describe("Output directory for the HPGL files"),
      drawingSheet: z.string().optional().describe("Path to a drawing sheet override"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      excludeDrawingSheet: z.boolean().optional().describe("No drawing sheet"),
      defaultFont: z.string().optional().describe("Default font name"),
      pages: z
        .string()
        .optional()
        .describe("Comma list of page numbers to print (blank = all pages)"),
      penSize: z.number().optional().describe("Pen size in mm (default 0.5)"),
      origin: z
        .number()
        .optional()
        .describe("Origin and scale: 0 bottom left, 1 centered, 2 page fit, 3 content fit"),
    },
    async (args) => {
      logger.debug(`Exporting schematic HPGL to: ${args.outputDir}`);
      const result = await callKicadScript("export_sch_hpgl", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export Schematic PostScript Tool (kicad-cli, full option set)
  // ------------------------------------------------------
  server.tool(
    "export_sch_ps",
    "Export a schematic to PostScript via kicad-cli (`sch export ps`), one PS per page into a directory. Exposes drawing-sheet override, theme, black-and-white, exclude-drawing-sheet, default-font, no-background-color, and page selection. schematicPath is REQUIRED.",
    {
      schematicPath: z.string().describe("Path to the .kicad_sch (required)"),
      outputDir: z.string().describe("Output directory for the PostScript files"),
      drawingSheet: z.string().optional().describe("Path to a drawing sheet override"),
      defineVar: z
        .array(z.string())
        .optional()
        .describe("Project variable overrides as 'KEY=VALUE' strings"),
      theme: z.string().optional().describe("Color theme to use (default: schematic settings)"),
      blackAndWhite: z.boolean().optional().describe("Black and white only"),
      excludeDrawingSheet: z.boolean().optional().describe("No drawing sheet"),
      defaultFont: z.string().optional().describe("Default font name"),
      noBackgroundColor: z
        .boolean()
        .optional()
        .describe("Avoid setting a background color (regardless of theme)"),
      pages: z
        .string()
        .optional()
        .describe("Comma list of page numbers to print (blank = all pages)"),
    },
    async (args) => {
      logger.debug(`Exporting schematic PostScript to: ${args.outputDir}`);
      const result = await callKicadScript("export_sch_ps", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  // ------------------------------------------------------
  // Export Schematic Python-BOM Tool (kicad-cli)
  // ------------------------------------------------------
  server.tool(
    "export_sch_python_bom",
    "Export the legacy Python-BOM intermediate XML from a schematic via kicad-cli (`sch export python-bom`). This is the XML netlist consumed by the schematic editor's Python BOM scripts. Minimal option set (output + input only). schematicPath is REQUIRED.",
    {
      schematicPath: z.string().describe("Path to the .kicad_sch (required)"),
      outputPath: z.string().describe("Output XML file path"),
    },
    async (args) => {
      logger.debug(`Exporting schematic Python-BOM to: ${args.outputPath}`);
      const result = await callKicadScript("export_sch_python_bom", args);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result),
          },
        ],
      };
    },
  );

  logger.info("Export tools registered");
}
