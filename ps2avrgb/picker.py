"""On-screen key/function selection; never injects desktop keypresses."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .keys import NAMES


class KeyPicker(QDialog):
    """Dialog for choosing a firmware key index from on-screen buttons."""

    def __init__(self, parent=None):
        """Build the tabbed key/function picker."""
        super().__init__(parent)
        self.selected = None
        self.buttons = []
        self.setWindowTitle("Choose a key or function")
        self.resize(1120, 490)
        root = QVBoxLayout(self)
        root.addWidget(
            QLabel(
                "Click a key to assign it to the selected keypad position. "
                "This does not type into other applications."
            )
        )
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search: F23, Shift, volume, FN, macro, or 0x…")
        root.addWidget(self.search)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        index = {v: k for k, v in NAMES.items()}
        self.add_tab(
            "Keyboard",
            [
                ["Escape"] + ["F" + str(i) for i in range(1, 13)],
                ["Grave"] + list("1234567890") + ["Minus", "Equal", "Backspace"],
                ["Tab"] + list("QWERTYUIOP") + ["LeftBracket", "RightBracket", "Backslash"],
                ["CapsLock"] + list("ASDFGHJKL") + ["Semicolon", "Quote", "Enter"],
                ["LeftShift"] + list("ZXCVBNM") + ["Comma", "Period", "Slash", "RightShift"],
                [
                    "LeftCtrl",
                    "LeftGUI",
                    "LeftAlt",
                    "Space",
                    "RightAlt",
                    "Menu",
                    "RightGUI",
                    "RightCtrl",
                ],
            ],
            index,
        )
        self.add_tab(
            "Extended / keypad",
            [
                ["F" + str(i) for i in range(13, 25)],
                [
                    "PrintScreen",
                    "ScrollLock",
                    "Pause",
                    "Insert",
                    "Delete",
                    "Home",
                    "End",
                    "PageUp",
                    "PageDown",
                ],
                ["Up", "Down", "Left", "Right"],
                [
                    "NumLock",
                    "KPDivide",
                    "KPMultiply",
                    "KPMinus",
                    "KPPlus",
                    "KPEnter",
                    "KPDecimal",
                    "KPComma",
                    "KPEqual",
                ],
                ["KP" + str(i) for i in range(10)],
            ],
            index,
        )
        for title, codes in [
            ("Media / system", range(113, 139)),
            ("Layers / lighting", range(241, 255)),
            ("Macros", range(189, 213)),
            ("Dual action", range(214, 238)),
        ]:
            names = [NAMES[c] for c in codes if c in NAMES]
            self.add_tab(title, [names[i : i + 6] for i in range(0, len(names), 6)], index)
        self.add_tab("Other", [[NAMES[c] for c in [0, 141, 142, 143, 144, 158, 176]]], index)
        self.search.textChanged.connect(self.filter)
        cancel = QDialogButtonBox(QDialogButtonBox.Cancel)
        cancel.rejected.connect(self.reject)
        root.addWidget(cancel)

    def add_tab(self, title, rows, index):
        """Add a tab of key buttons laid out in ``rows`` of key names."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        grid = QGridLayout(body)
        grid.setAlignment(Qt.AlignTop)
        scroll.setWidget(body)
        tab = self.tabs.addTab(scroll, title)
        for row, names in enumerate(rows):
            for col, name in enumerate(names):
                code = index[name]
                button = QPushButton(name)
                button.setMinimumHeight(42)
                button.setToolTip(f"{name}: firmware index {code} / 0x{code:02X}")
                button.clicked.connect(lambda checked=False, c=code: self.choose(c))
                grid.addWidget(button, row, col)
                self.buttons.append((tab, name, code, button))

    def choose(self, code):
        """Record ``code`` as the selection and close the dialog."""
        self.selected = code
        self.accept()

    def filter(self, text):
        """Show only buttons matching ``text`` (name, decimal or 0x index)."""
        text = text.casefold().strip()
        first = None
        for tab, name, code, button in self.buttons:
            show = not text or text in name.casefold() or text in (str(code), f"0x{code:02x}")
            button.setVisible(show)
            if show and first is None:
                first = tab
        if text and first is not None:
            self.tabs.setCurrentIndex(first)
