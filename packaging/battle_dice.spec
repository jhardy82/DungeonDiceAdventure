# PyInstaller spec for the standalone Battle Dice build (one-folder, windowed).
#
# Build from the repository root, with the game installed in the active environment:
#
#     python -m pip install ".[package]"
#     python -m PyInstaller packaging/battle_dice.spec --noconfirm
#
# The result is dist/BattleDice/ containing BattleDice(.exe) and its _internal folder.
# Verify a build without opening a window:  dist/BattleDice/BattleDice --smoke-test

import os

from PyInstaller.utils.hooks import collect_data_files

# JSON fixtures and the schema ship inside the battle_dice package; the JSON Schema
# meta-schemas ship inside jsonschema_specifications.
datas = (
    collect_data_files("battle_dice")
    + collect_data_files("jsonschema")
    + collect_data_files("jsonschema_specifications")
)

analysis = Analysis(  # noqa: F821 - provided by PyInstaller when it executes the spec
    [os.path.join(SPECPATH, "battle_dice_entry.py")],  # noqa: F821
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "mypy", "ruff"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="BattleDice",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
collection = COLLECT(  # noqa: F821
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="BattleDice",
)
