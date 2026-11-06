"""
run_dashboard.py
----------------
Launcher for Service 2: Native Desktop GUI Application.
Renders the OpenGL Multi-Line Relative Strength Chart, Synchronized Heatmap, and Surge Radar.

Usage:
    python run_dashboard.py
"""

from pathlib import Path
import sys
from PySide6 import QtWidgets

from gui.app import RelativeStrengthDashboard
from core.logger import configure_logger

PROJECT_ROOT = Path(__file__).resolve().parent


def main():
    logger = configure_logger(
        project_name="relative_strength_dashboard",
        project_root=PROJECT_ROOT,
        show_logs_on_terminal=True,
        store_logs_in_file=True,
        log_level="INFO",
    )

    logger.info("Starting PySide6 Native Desktop Dashboard...")
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")

    dashboard = RelativeStrengthDashboard()
    dashboard.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
