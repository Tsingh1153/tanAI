# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec that freezes the tanAI backend into a self-contained onedir
# executable. Run from the backend/ directory:  pyinstaller tanai-backend.spec

from PyInstaller.utils.hooks import collect_all, collect_submodules

hiddenimports: list[str] = []
datas: list = []
binaries: list = []

# Follow every submodule of our own package and uvicorn (uvicorn resolves its
# loop/protocol implementations dynamically, so static analysis misses them).
for pkg in ("app", "uvicorn"):
    hiddenimports += collect_submodules(pkg)

# Packages with compiled parts or data files that need everything collected.
for pkg in ("pydantic", "pydantic_core"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Async SQLite driver + the SQLAlchemy dialect that loads it.
hiddenimports += [
    "aiosqlite",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.aiosqlite",
]

a = Analysis(
    ["run_server.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="tanai-backend",
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="tanai-backend",
)
