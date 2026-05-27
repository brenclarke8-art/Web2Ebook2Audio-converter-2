# src/ebook_app/main.py
"""Application entry point."""

import os
import sys

# ---------------------------------------------------------------------------
# Prevent ONNX Runtime / OpenMP threads from saturating all CPU cores.
#
# By default ONNX Runtime uses spin-wait (busy-loop) threads that peg every
# core at 100 % even when idle.  This starves the OS network stack and causes
# apparent loss of internet connectivity while TTS inference is running.
#
# OMP_WAIT_POLICY=PASSIVE switches idle threads to OS sleep instead of spin.
# Capping thread counts leaves at least two cores free for the OS / network.
# ---------------------------------------------------------------------------
_cpu_count: int = os.cpu_count() or 4
_onnx_threads: str = str(max(1, _cpu_count - 2))
os.environ.setdefault("OMP_NUM_THREADS", _onnx_threads)
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("MKL_NUM_THREADS", _onnx_threads)
os.environ.setdefault("OPENBLAS_NUM_THREADS", _onnx_threads)
os.environ.setdefault("ONNXRUNTIME_THREADPOOL_SIZE", _onnx_threads)

from PySide6.QtWidgets import QApplication

from ebook_app.ui.main_window import MainWindow
from ebook_app.core.settings_manager import SettingsManager


def main() -> None:
    """Launch the Ebook Audio Studio application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Ebook Audio Studio")
    app.setOrganizationName("EbookAudioStudio")

    settings = SettingsManager()
    window = MainWindow(settings)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
