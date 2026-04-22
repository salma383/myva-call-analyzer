"""Run this file to build the portable .exe:  python build_config.py"""
import PyInstaller.__main__
import os
import shutil
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))

ICON_SRC = os.path.join(ROOT, "assets", "icons", "app.ico")


def _stage_icon() -> str | None:
    """
    PyInstaller silently fails to embed icons when the path contains spaces.
    Copy the icon to a temp path without spaces and return that.
    """
    if not os.path.exists(ICON_SRC):
        return None
    staged = os.path.join(tempfile.gettempdir(), "myva_app.ico")
    shutil.copyfile(ICON_SRC, staged)
    return staged


def build():
    # Clean previous build artefacts
    for folder in ("dist", "build"):
        target = os.path.join(ROOT, folder)
        if os.path.exists(target):
            shutil.rmtree(target)

    args = [
        "main.py",
        "--name=CallAnalyzer",
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",

        # ── Exclude heavy scientific libs ──────────────────────────────────
        "--exclude-module=numpy",
        "--exclude-module=scipy",
        "--exclude-module=matplotlib",
        "--exclude-module=pandas",
        "--exclude-module=sklearn",
        "--exclude-module=torch",
        "--exclude-module=tensorflow",

        # ── Bundle data folders ────────────────────────────────────────────
        f"--add-data={os.path.join(ROOT, 'shared')}{os.pathsep}shared",
        f"--add-data={os.path.join(ROOT, 'assets')}{os.pathsep}assets",

        # ── Hidden / collected imports ─────────────────────────────────────
        "--hidden-import=tkinterdnd2",
        "--hidden-import=customtkinter",
        "--hidden-import=PIL._tkinter_finder",
        "--collect-all=customtkinter",
        "--collect-all=tkinterdnd2",
    ]

    staged_icon = _stage_icon()
    if staged_icon:
        args.append(f"--icon={staged_icon}")
        print(f"[build] Staged icon: {staged_icon}")
    else:
        print(f"[build] No icon found — expected at {ICON_SRC}")

    PyInstaller.__main__.run(args)
    print("\nBuild complete — exe is at:  dist/CallAnalyzer.exe")


if __name__ == "__main__":
    build()
