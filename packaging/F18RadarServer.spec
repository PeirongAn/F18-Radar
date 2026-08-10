# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

import setuptools


ROOT = Path(SPECPATH).resolve().parent
SERVER = ROOT / "server"
TOBII = SERVER / "tobii"
SETUPTOOLS_VENDOR = Path(setuptools.__file__).resolve().parent / "_vendor"

datas = []
binaries = []
hiddenimports = [
    "backports",
    "backports.tarfile",
    "backports.tarfile.compat",
    "backports.tarfile.compat.py38",
    "tobii_research",
    "tobiiresearch",
]

for module_path in (TOBII / "tobiiresearch").rglob("*.py"):
    relative = module_path.relative_to(TOBII).with_suffix("")
    if relative.name == "__init__":
        relative = relative.parent
    module_name = ".".join(relative.parts)
    if module_name and module_name not in hiddenimports:
        hiddenimports.append(module_name)

hiddenimports.append("tobiiresearch.interop.python3.tobii_research_interop")

a = Analysis(
    [str(SERVER / "main.py")],
    pathex=[str(SERVER), str(TOBII), str(SETUPTOOLS_VENDOR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "vitest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="F18RadarServer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="F18RadarServer",
)
