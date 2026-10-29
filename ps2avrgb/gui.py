"""Qt front end over the same protocol and document API as the CLI."""

import datetime
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import documents, keys, protocol
from .layout import matrix_position

LAYER_NAMES = ("Normal", "FN", "FN2", "FN3")


class Signals(QObject):
    """Qt signals a worker uses to report its result back to the GUI thread."""

    finished = Signal(object)
    failed = Signal(str)


class ReadWorker(QRunnable):
    """Background job: read and double-verify the keyboard into a snapshot."""

    def __init__(self, path):
        """Read the keyboard at HID ``path``."""
        super().__init__()
        self.path = path
        self.signals = Signals()

    def run(self):
        """Read the device; emit ``finished`` with the snapshot or ``failed`` with the error."""
        try:
            with protocol.Keyboard(self.path) as device:
                result = documents.snapshot(device.read_state())
            self.signals.finished.emit(result)
        except Exception as error:
            self.signals.failed.emit(str(error))


class FlashWorker(QRunnable):
    """Background job: run the full keymap programming transaction."""

    def __init__(self, data, path):
        """Program snapshot ``data`` to the keyboard at HID ``path``."""
        super().__init__()
        self.data = data
        self.path = path
        self.signals = Signals()

    def run(self):
        """Run ``flashing.operation``; emit ``finished`` with its receipt or ``failed``."""
        try:
            from .flashing import operation

            self.signals.finished.emit(operation(self.data, self.path))
        except Exception as error:
            self.signals.failed.emit(str(error))


class Window(QMainWindow):
    """Main editor window: read, edit, review and write keymaps."""

    def __init__(self, path=None):
        """Build the window and optionally open the snapshot at ``path``."""
        super().__init__()
        self.data = None
        self.worker = None
        self.original_path = None
        self.dirty = False
        self.busy = False
        self.baseline = None
        self.history = []
        self.setWindowTitle("ps2avrGB Native — Keymap Inspector & Editor")
        self.resize(1120, 750)
        root = QWidget()
        layout = QVBoxLayout(root)
        self.setCentralWidget(root)
        self.note = QLabel(
            "Read your keyboard or open a snapshot, then click a key to choose its function. "
            "Review changes before writing them. A backup is saved automatically."
        )
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        top = QHBoxLayout()
        layout.addLayout(top)
        self.devices = QComboBox()
        self.devices.setMinimumWidth(300)
        top.addWidget(self.devices, 1)
        refresh = QPushButton("Refresh devices")
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        self.read = QPushButton("Read & back up keyboard")
        self.read.clicked.connect(self.read_keyboard)
        top.addWidget(self.read)
        open_button = QPushButton("Open snapshot…")
        open_button.clicked.connect(self.open_snapshot)
        top.addWidget(open_button)
        self.identity = QLabel("No snapshot loaded")
        layout.addWidget(self.identity)
        edit = QHBoxLayout()
        layout.addLayout(edit)
        edit.addWidget(QLabel("Layer"))
        self.layer = QComboBox()
        self.layer.addItems(["0 · Normal", "1 · FN", "2 · FN2", "3 · FN3"])
        self.layer.currentIndexChanged.connect(self.render)
        edit.addWidget(self.layer)
        self.view = QComboBox()
        self.view.addItems(["23-key keypad", "Firmware matrix"])
        self.view.setToolTip(
            "23-key view matches this keypad; firmware matrix exposes all stored positions."
        )
        self.view.currentIndexChanged.connect(self.render)
        advanced = QPushButton("Advanced")
        advanced.setCheckable(True)
        edit.addWidget(advanced)
        self.advanced = QWidget()
        advanced_edit = QHBoxLayout(self.advanced)
        advanced_edit.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.advanced)
        self.advanced.hide()
        advanced.toggled.connect(self.advanced.setVisible)
        advanced_edit.addWidget(self.view)
        self.key = QComboBox()
        self.key.setEditable(True)
        for code in range(256):
            self.key.addItem(f"{keys.label(code)}  [0x{code:02X}]", code)
        advanced_edit.addWidget(self.key, 1)
        apply = QPushButton("Assign to selected cell")
        apply.clicked.connect(self.assign)
        advanced_edit.addWidget(apply)
        picker = QPushButton("Choose function…")
        picker.clicked.connect(self.pick_key)
        edit.addWidget(picker)
        self.undo = QPushButton("Undo")
        self.undo.setEnabled(False)
        self.undo.clicked.connect(self.undo_edit)
        edit.addWidget(self.undo)
        self.changes = QLabel("")
        layout.addWidget(self.changes)
        self.table = QTableWidget(15, 8)
        self.table.setHorizontalHeaderLabels([f"Column {i}" for i in range(8)])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setSelectionBehavior(QTableWidget.SelectItems)
        self.table.cellClicked.connect(self.click_key)
        layout.addWidget(self.table, 1)
        bottom = QHBoxLayout()
        layout.addLayout(bottom)
        save = QPushButton("Save edited snapshot…")
        save.clicked.connect(self.save_snapshot)
        bottom.addWidget(save)
        export = QPushButton("Export Bootmapper keymap HEX…")
        export.clicked.connect(self.export_hex)
        bottom.addWidget(export)
        review = QPushButton("Review changes…")
        review.clicked.connect(self.review_changes)
        bottom.addWidget(review)
        write = QPushButton("Write keymap to keyboard…")
        write.clicked.connect(self.flash_keymap)
        bottom.addWidget(write)
        bottom.addStretch()
        self.statusBar().showMessage(
            "23-key layout: bottom-right wide key uses matrix row 3, column 5."
        )
        self.refresh()
        if path:
            self.load(path)

    @Slot()
    def refresh(self):
        """Repopulate the device list from connected ps2avrGB control interfaces."""
        self.devices.clear()
        try:
            for device in protocol.devices():
                path = device["path"].decode(errors="replace")
                self.devices.addItem(f"{device.get('product_string', 'Keyboard')} · {path}", path)
            if not self.devices.count():
                self.devices.addItem("No ps2avrGB control interface detected", None)
        except Exception as error:
            self.error(str(error))

    @Slot()
    def read_keyboard(self):
        """Start a background read of the selected keyboard."""
        path = self.devices.currentData()
        if not path:
            return
        if not self.confirm_discard():
            return
        self.busy = True
        self.centralWidget().setEnabled(False)
        self.read.setEnabled(False)
        self.statusBar().showMessage("Reading keymaps and macros twice for verification…")
        self.worker = ReadWorker(path)
        self.worker.signals.finished.connect(self.read_finished)
        self.worker.signals.failed.connect(self.read_failed)
        QThreadPool.globalInstance().start(self.worker)

    @Slot(object)
    def read_finished(self, data):
        """Save the verified read as a new backup and load it as the editing baseline."""
        self.busy = False
        self.centralWidget().setEnabled(True)
        self.read.setEnabled(True)
        try:
            backup = (
                Path.home()
                / "Backups/ps2avrgb"
                / datetime.datetime.now().strftime("keyboard-%Y%m%d-%H%M%S.json")
            )
            documents.save(data, backup)
            self.original_path = backup
            self.data = data
            self.baseline = data
            self.history = []
            self.dirty = False
            self.render()
            self.statusBar().showMessage("Verified original backup saved: " + str(backup))
        except Exception as error:
            self.error(str(error))

    @Slot(str)
    def read_failed(self, message):
        """Re-enable the window and show the read error."""
        self.busy = False
        self.centralWidget().setEnabled(True)
        self.read.setEnabled(True)
        self.error(message)

    def confirm_discard(self):
        """Return True if there are no unsaved edits or the user agrees to discard them."""
        return (
            not self.dirty
            or QMessageBox.question(
                self,
                "Unsaved edits",
                "Discard unsaved edits?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )

    @Slot()
    def open_snapshot(self):
        """Ask for a snapshot file and load it."""
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open snapshot", str(Path.home() / "Backups"), "Snapshots (*.json)"
        )
        if path:
            self.load(path)

    def load(self, path):
        """Load a snapshot file as the new baseline, clearing undo history."""
        try:
            self.data = documents.load(path)
            self.baseline = self.data
            self.history = []
            self.original_path = Path(path)
            self.dirty = False
            self.render()
        except Exception as error:
            self.error(str(error))

    def render(self, *_):
        """Redraw the key table for the current layer and view, highlighting changes."""
        if self.data is None:
            return
        info = self.data["options"]
        layer = self.layer.currentIndex()
        raw = bytes.fromhex(self.data["keymap"][layer])
        changes = self.change_lines()
        self.changes.setText(
            f"{len(changes)} changed assignment(s) across all layers. "
            "Highlighted keys differ from the loaded or last-written snapshot."
        )
        self.undo.setEnabled(bool(self.history))
        self.identity.setText(
            f"{info['name']} · firmware {info['version']} · {info['rows']} × 8 matrix · four layers"
            + (" · edited" if self.dirty else "")
        )
        selected = (self.table.currentRow(), self.table.currentColumn())
        physical = self.view.currentIndex() == 0
        self.table.horizontalHeader().setVisible(not physical)
        self.table.verticalHeader().setVisible(not physical)
        rows, columns = (4, 6) if physical else (info["rows"], 8)
        self.table.clearSpans()
        self.table.clearContents()
        self.table.setRowCount(rows)
        self.table.setColumnCount(columns)
        self.table.setHorizontalHeaderLabels([f"Column {i}" for i in range(columns)])
        self.table.setVerticalHeaderLabels([f"Row {i}" for i in range(rows)])
        for row in range(rows):
            for col in range(columns):
                if physical and row == 3 and col == 5:
                    continue
                mr, mc = matrix_position(row, col, physical)
                value = raw[mr * 8 + mc]
                item = QTableWidgetItem(keys.label(value))
                item.setTextAlignment(Qt.AlignCenter)
                item.setToolTip(
                    f"Layer {layer}, matrix row {mr}, column {mc} · firmware index 0x{value:02X}"
                )
                if (
                    self.baseline
                    and value != bytes.fromhex(self.baseline["keymap"][layer])[mr * 8 + mc]
                ):
                    item.setBackground(QColor("#235377"))
                    item.setForeground(QColor("#ffffff"))
                self.table.setItem(row, col, item)
        if physical:
            self.table.setSpan(3, 4, 1, 2)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch if physical else QHeaderView.Interactive
        )
        for col in range(columns):
            self.table.setColumnWidth(col, 130 if physical else 110)
        for row in range(rows):
            self.table.setRowHeight(row, 85 if physical else 30)
        if 0 <= selected[0] < rows and 0 <= selected[1] < columns:
            self.table.setCurrentCell(*selected)

    def select(self, row, col):
        """Show the key at table cell (``row``, ``col``) in the Advanced key box."""
        if self.data:
            mr, mc = matrix_position(row, col, self.view.currentIndex() == 0)
            value = bytes.fromhex(self.data["keymap"][self.layer.currentIndex()])[mr * 8 + mc]
            self.key.setCurrentIndex(value)

    def click_key(self, row, col):
        """Select the clicked key and open the function picker."""
        self.select(row, col)
        if self.data is not None:
            self.pick_key()

    def change_lines(self):
        """Return one description per key that differs from the baseline, across all layers."""
        if not self.baseline or not self.data:
            return []
        changes = []
        layers = zip(self.baseline["keymap"], self.data["keymap"], strict=True)
        for layer, (before, after) in enumerate(layers):
            cells = zip(bytes.fromhex(before), bytes.fromhex(after), strict=True)
            for position, (old, new) in enumerate(cells):
                if old != new:
                    row, col = divmod(position, 8)
                    changes.append(
                        f"{LAYER_NAMES[layer]} · matrix ({row}, {col}): "
                        f"{keys.label(old)} → {keys.label(new)}"
                    )
        return changes

    @Slot()
    def review_changes(self):
        """Show a dialog listing every changed assignment."""
        changes = self.change_lines()
        message = QMessageBox(self)
        message.setWindowTitle("Review keymap changes")
        message.setText(
            f"{len(changes)} assignment(s) changed since loading or last writing."
            if self.data
            else "Read your keyboard or open a snapshot first."
        )
        message.setInformativeText("Matrix coordinates are zero based. The wide key is (3, 5).")
        if changes:
            message.setDetailedText("\n".join(changes))
        message.exec()

    @Slot()
    def undo_edit(self):
        """Revert the most recent assignment, on whichever layer it was made."""
        if self.history:
            self.data = self.history.pop()
            self.dirty = True
            self.render()

    @Slot()
    def pick_key(self):
        """Open the on-screen picker and assign the chosen function to the selected key."""
        if self.data is None or self.table.currentRow() < 0:
            self.error("Select a keypad key first.")
            return
        from .picker import KeyPicker

        dialog = KeyPicker(self)
        if dialog.exec() and dialog.selected is not None:
            self.key.setCurrentIndex(dialog.selected)
            self.assign()

    @Slot()
    def assign(self):
        """Assign the Advanced key box value to the selected key (an offline edit only)."""
        row, col = self.table.currentRow(), self.table.currentColumn()
        if self.data is None or min(row, col) < 0:
            return
        try:
            text = self.key.currentText()
            selected = self.key.currentIndex()
            value = (
                self.key.currentData()
                if selected >= 0 and text == self.key.itemText(selected)
                else keys.parse_key(text)
            )
            if value is None:
                value = keys.parse_key(text)
            mr, mc = matrix_position(row, col, self.view.currentIndex() == 0)
            if bytes.fromhex(self.data["keymap"][self.layer.currentIndex()])[mr * 8 + mc] == value:
                return
            self.history.append(self.data)
            self.data = documents.set_key(self.data, self.layer.currentIndex(), mr, mc, value)
            self.dirty = True
            self.render()
            self.statusBar().showMessage("Offline edit applied. Keyboard hardware is unchanged.")
        except Exception as error:
            self.error(str(error))

    @Slot()
    def save_snapshot(self):
        """Save the edited snapshot to a new file, refusing to overwrite the original."""
        if self.data is None:
            return
        suggested = Path.home() / "Backups/ps2avrgb/edited-keymap.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save edited snapshot", str(suggested), "Snapshots (*.json)"
        )
        if not path:
            return
        if self.original_path and Path(path).resolve() == self.original_path.resolve():
            self.error("Choose a different filename to preserve the original snapshot.")
            return
        try:
            documents.save(self.data, path)
            self.dirty = False
            self.render()
            self.statusBar().showMessage("Saved " + path)
        except Exception as error:
            self.error(str(error))

    @Slot()
    def flash_keymap(self):
        """Confirm with the user, then program the keymap in the background."""
        if self.data is None:
            return
        path = self.devices.currentData()
        if not path:
            self.error("Select a connected ps2avrGB keyboard first.")
            return
        from .flashing import plan

        try:
            plan(self.data)
        except Exception as error:
            self.error(str(error))
            return
        answer = QMessageBox.question(
            self,
            "Write keymap",
            "Write the four keymap layers to this keyboard?\n\n"
            "The keypad will briefly disconnect while in bootloader mode. Keep it plugged in.\n"
            "A fresh backup is saved first; the keymap is read back afterward.\n"
            "Existing firmware, macros and settings are preserved.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.busy = True
        self.centralWidget().setEnabled(False)
        self.statusBar().showMessage("Backing up, programming keymap and verifying…")
        self.worker = FlashWorker(self.data, path)
        self.worker.signals.finished.connect(self.flash_finished)
        self.worker.signals.failed.connect(self.flash_failed)
        QThreadPool.globalInstance().start(self.worker)

    @Slot(object)
    def flash_finished(self, result):
        """Make the written keymap the new baseline and report the backup location."""
        self.busy = False
        self.centralWidget().setEnabled(True)
        self.dirty = False
        self.baseline = self.data
        self.history = []
        self.render()
        self.statusBar().showMessage("Keymap written and verified. Backup: " + result["backup"])
        QMessageBox.information(
            self,
            "Keymap verified",
            "Keymap written and read back successfully.\nBackup: " + result["backup"],
        )

    @Slot(str)
    def flash_failed(self, message):
        """Re-enable the window and show the programming error and its recovery details."""
        self.busy = False
        self.centralWidget().setEnabled(True)
        self.error(message)

    @Slot()
    def export_hex(self):
        """Export the four keymap layers to an Intel HEX file."""
        if self.data is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export keymap HEX", str(Path.home() / "keymap.hex"), "Intel HEX (*.hex)"
        )
        if path:
            try:
                Path(path).write_text(documents.intel_hex(self.data))
            except Exception as error:
                self.error(str(error))

    def error(self, message):
        """Show ``message`` in the status bar and in a warning dialog."""
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, "ps2avrGB Native", message)

    def closeEvent(self, event):
        """Block closing during device operations; otherwise confirm unsaved edits."""
        if self.busy or (self.worker is not None and not self.read.isEnabled()):
            QMessageBox.information(
                self,
                "Device operation in progress",
                "Wait for the keyboard operation to finish before closing.",
            )
            event.ignore()
        elif self.confirm_discard():
            event.accept()
        else:
            event.ignore()


def run(path=None):
    """Start the Qt application, optionally opening ``path``; return its exit code."""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = Window(path)
    window.show()
    return app.exec()
