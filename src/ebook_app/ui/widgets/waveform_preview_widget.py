# src/ebook_app/ui/widgets/waveform_preview_widget.py

from __future__ import annotations

import numpy as np
import wave

from PySide6.QtCore import (
    Qt, QRectF, QPointF, Signal, Slot, QUrl
)
from PySide6.QtGui import (
    QPainter, QColor, QPen
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QHBoxLayout
)
from PySide6.QtMultimedia import (
    QMediaPlayer, QAudioOutput
)


class WaveformPreviewWidget(QWidget):
    """
    Displays a waveform for a WAV file with:
        - Zoom (mouse wheel)
        - Scrubbing (click + drag)
        - Playback cursor
        - Play / Pause / Stop buttons
        - Qt Multimedia backend

    Emits:
        play_started()
        play_paused()
        play_stopped()
        scrubbed(position_ms)
    """

    play_started = Signal()
    play_paused = Signal()
    play_stopped = Signal()
    scrubbed = Signal(int)  # position in ms

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumHeight(140)

        # Audio backend
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

        # Waveform data
        self.samples = np.array([])
        self.sample_rate = 44100
        self.duration_ms = 0

        # Viewport
        self.zoom = 1.0
        self.offset = 0.0  # 0.0 → start, 1.0 → end

        # Scrubbing
        self.scrubbing = False

        # UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Controls
        controls = QHBoxLayout()
        layout.addLayout(controls)

        self.btn_play = QPushButton("Play")
        self.btn_pause = QPushButton("Pause")
        self.btn_stop = QPushButton("Stop")

        controls.addWidget(self.btn_play)
        controls.addWidget(self.btn_pause)
        controls.addWidget(self.btn_stop)
        controls.addStretch()

        self.btn_play.clicked.connect(self._play)
        self.btn_pause.clicked.connect(self._pause)
        self.btn_stop.clicked.connect(self._stop)

        # Waveform canvas
        self.canvas = _WaveformCanvas(self)
        layout.addWidget(self.canvas, 1)

        # Connect canvas scrubbing to player
        self.canvas.scrubbed.connect(self._on_canvas_scrub)

        # Sync playback cursor
        self.player.positionChanged.connect(self._on_position_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_wav(self, path: str):
        """Load a WAV file and extract waveform."""
        try:
            with wave.open(path, "rb") as wf:
                self.sample_rate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
                samples = np.frombuffer(frames, dtype=np.int16)

                # If stereo → convert to mono
                if wf.getnchannels() == 2:
                    samples = samples.reshape(-1, 2).mean(axis=1)

                self.samples = samples.astype(np.float32)
                self.duration_ms = int((len(self.samples) / self.sample_rate) * 1000)

        except Exception as e:
            print("Waveform load error:", e)
            self.samples = np.array([])
            self.duration_ms = 0

        # Load into player
        self.player.setSource(QUrl.fromLocalFile(path))

        # Update canvas
        self.canvas.set_waveform(self.samples, self.sample_rate)
        self.canvas.update()

    # ------------------------------------------------------------------
    # Playback controls
    # ------------------------------------------------------------------
    def _play(self):
        self.player.play()
        self.play_started.emit()

    def _pause(self):
        self.player.pause()
        self.play_paused.emit()

    def _stop(self):
        self.player.stop()
        self.play_stopped.emit()
        self.canvas.set_playback_position(0)

    # ------------------------------------------------------------------
    # Sync playback cursor
    # ------------------------------------------------------------------
    def _on_position_changed(self, pos_ms: int):
        self.canvas.set_playback_position(pos_ms)

    # ------------------------------------------------------------------
    # Scrubbing from canvas
    # ------------------------------------------------------------------
    @Slot(int)
    def _on_canvas_scrub(self, pos_ms: int):
        self.player.setPosition(pos_ms)
        self.scrubbed.emit(pos_ms)


# ======================================================================
# Internal Canvas Widget
# ======================================================================

class _WaveformCanvas(QWidget):
    scrubbed = Signal(int)  # position in ms

    def __init__(self, parent=None):
        super().__init__(parent)

        self.samples = np.array([])
        self.sample_rate = 44100
        self.duration_ms = 0

        self.zoom = 1.0
        self.offset = 0.0

        self.playback_pos_ms = 0

        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    def set_waveform(self, samples: np.ndarray, sample_rate: int):
        self.samples = samples
        self.sample_rate = sample_rate
        self.duration_ms = int((len(samples) / sample_rate) * 1000)
        self.update()

    def set_playback_position(self, pos_ms: int):
        self.playback_pos_ms = pos_ms
        self.update()

    # ------------------------------------------------------------------
    # Zoom with mouse wheel
    # ------------------------------------------------------------------
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 0.9
        self.zoom = max(1.0, min(20.0, self.zoom * factor))
        self.update()

    # ------------------------------------------------------------------
    # Scrubbing
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._scrub_at(event.position().x())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._scrub_at(event.position().x())

    def _scrub_at(self, x: float):
        if self.duration_ms <= 0:
            return

        ratio = x / max(1, self.width())
        pos_ms = int(ratio * self.duration_ms)
        self.scrubbed.emit(pos_ms)
        self.set_playback_position(pos_ms)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1e1e1e"))

        if self.samples.size == 0:
            painter.setPen(QColor("#888"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No audio loaded")
            return

        w = self.width()
        h = self.height()

        # Determine visible sample range
        total_samples = len(self.samples)
        visible_samples = int(total_samples / self.zoom)

        start = int(self.offset * (total_samples - visible_samples))
        end = start + visible_samples
        end = min(end, total_samples)

        segment = self.samples[start:end]

        # Normalize
        if segment.size > 0:
            segment = segment / max(1, np.max(np.abs(segment)))

        # Draw waveform
        mid = h / 2
        x_scale = w / max(1, len(segment))

        pen = QPen(QColor("#4fc3f7"))
        pen.setWidth(1)
        painter.setPen(pen)

        for i in range(len(segment) - 1):
            x1 = i * x_scale
            y1 = mid - segment[i] * (h / 2)
            x2 = (i + 1) * x_scale
            y2 = mid - segment[i + 1] * (h / 2)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Draw playback cursor
        if self.duration_ms > 0:
            ratio = self.playback_pos_ms / self.duration_ms
            x = ratio * w
            painter.setPen(QPen(QColor("#ff4081"), 2))
            painter.drawLine(x, 0, x, h)
