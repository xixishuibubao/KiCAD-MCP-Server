# Freerouting + Java dependencies (local, not tracked by git)

This folder is the recommended place to drop the external binaries used by the
`autoroute` / `check_freerouting` MCP tools. **The binaries themselves are NOT
tracked by git** (GitHub fork repos cannot push Git LFS objects, and committing
~170 MB of binaries directly would bloat the repo). Only this README is
tracked. Each user downloads the files locally after cloning.

## What to place here (optional, local only)

| File | Size | Purpose |
| --- | --- | --- |
| `freerouting.jar` | ~55 MB | Freerouting autorouter (headless CLI) |
| `OpenJDK25U-jdk_x64_windows_hotspot_*.msi` | ~111 MB | Eclipse Temurin JDK 25 (Windows x64) installer — Freerouting 2.2.4 requires Java 25+ |

These paths are gitignored (`resources/freerouting/*.jar`, `*.msi`), so they
will never be committed accidentally.

## Download

```bash
# Freerouting jar (pick a release; 2.2.4 needs Java 25, older 2.2.x work with Java 21)
curl -L -o resources/freerouting/freerouting.jar \
  https://github.com/freerouting/freerouting/releases/download/v2.2.4/freerouting-2.2.4-executable.jar

# Windows JDK 25 installer (optional, only if no Java 25+ on PATH)
# Download from https://adoptium.net/temurin/releases/?version=25&os=windows&arch=x64&package=jdk
```

## How the MCP finds the jar

`python/commands/freerouting.py` resolves the Freerouting JAR in this order:

1. `FREEROUTING_JAR` environment variable
2. Local copy at `resources/freerouting/freerouting.jar` (if you downloaded it here)
3. `~/.kicad-mcp/freerouting.jar` (legacy download location)

So if you place the jar here, `check_freerouting` reports `jar_found: true`
with no extra configuration. If you don't, just download it to
`~/.kicad-mcp/freerouting.jar` as before.

## Installing Java from the MSI (Windows, one-time)

Only needed if the host machine has no Java 25+ on PATH. Install silently:

```powershell
msiexec /i "resources\freerouting\OpenJDK25U-jdk_x64_windows_hotspot_25.0.4_7.msi" /qb ADDLOCAL=FeatureJava,FeatureEnvironment,FeatureJavaHome
```

Then verify: `java -version` should report `25.x`.

## Licenses

- Freerouting: GPL-3.0 — https://github.com/freerouting/freerouting
- Eclipse Temurin JDK: GPL-2.0 with Classpath Exception — https://adoptium.net
