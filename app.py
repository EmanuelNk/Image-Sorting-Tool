import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt


def apply_dark_palette(app: QApplication):
    app.setStyle("Fusion")
    p = QPalette()
    bg        = QColor(28,  28,  30)   # #1C1C1E — Apple system background
    bg_alt    = QColor(44,  44,  46)   # #2C2C2E — secondary background
    base      = QColor(18,  18,  20)   # input field base
    text      = QColor(235, 235, 245)  # #EBEBF5 — Apple primary label
    disabled  = QColor(99,  99,  102)  # #636366 — tertiary label
    btn       = QColor(44,  44,  46)   # #2C2C2E
    highlight = QColor(10,  132, 255)  # #0A84FF — Apple system blue

    p.setColor(QPalette.ColorRole.Window,          bg)
    p.setColor(QPalette.ColorRole.WindowText,       text)
    p.setColor(QPalette.ColorRole.Base,             base)
    p.setColor(QPalette.ColorRole.AlternateBase,    bg_alt)
    p.setColor(QPalette.ColorRole.ToolTipBase,      bg_alt)
    p.setColor(QPalette.ColorRole.ToolTipText,      text)
    p.setColor(QPalette.ColorRole.Text,             text)
    p.setColor(QPalette.ColorRole.Button,           btn)
    p.setColor(QPalette.ColorRole.ButtonText,       text)
    p.setColor(QPalette.ColorRole.BrightText,       QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Link,             highlight)
    p.setColor(QPalette.ColorRole.Highlight,        highlight)
    p.setColor(QPalette.ColorRole.HighlightedText,  QColor(255, 255, 255))

    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       disabled)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)

    app.setPalette(p)


def main():
    # Retina / HiDPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Photo Sorter")

    apply_dark_palette(app)

    from main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
