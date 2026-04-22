"""Run this file to build the portable .exe:  python build_config.py"""
import PyInstaller.__main__
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))

ICON_PATH = os.path.join(ROOT, "assets", "icons", "app.ico")
LOGO_PATH = os.path.join(ROOT, "assets", "icons", "logo.png")


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

    # App icon — use app.ico if it exists
    if os.path.exists(ICON_PATH):
        args.append(f"--icon={ICON_PATH}")
        print(f"[build] Using icon: {ICON_PATH}")
    else:
        print("[build] No icon found — run  python create_icon.py  first to add the logo.")
        print(f"        (expected: {ICON_PATH})")

    PyInstaller.__main__.run(args)
    print("\nBuild complete — exe is at:  dist/CallAnalyzer.exe")


if __name__ == "__main__":
    build()
