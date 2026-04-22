import sys
import os

# Make sure shared/ and project root are importable when frozen by PyInstaller
if getattr(sys, "frozen", False):
    base = sys._MEIPASS
else:
    base = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, base)

from config import api_manager, settings
from ui.main_window import MainWindow


def main():
    app = MainWindow()

    # Check for updates in the background — silent if no internet / URL not set
    try:
        from utils.updater import check_for_updates
        check_for_updates(app)
    except Exception:
        pass

    app.mainloop()


if __name__ == "__main__":
    main()
