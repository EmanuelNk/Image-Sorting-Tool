import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt


def apply_dark_palette(app: QApplication):
    app.setStyle("Fusion")
    p = QPalette()
    bg       = QColor(30,  30,  30)
    bg_alt   = QColor(38,  38,  38)
    base     = QColor(20,  20,  20)
    text     = QColor(200, 200, 200)
    disabled = QColor(80,  80,  80)
    btn      = QColor(50,  50,  50)
    highlight = QColor(42, 100, 180)

    p.setColor(QPalette.ColorRole.Window,          bg)
    p.setColor(QPalette.ColorRole.WindowText,       text)
    p.setColor(QPalette.ColorRole.Base,             base)
    p.setColor(QPalette.ColorRole.AlternateBase,    bg_alt)
    p.setColor(QPalette.ColorRole.ToolTipBase,      QColor(50, 50, 50))
    p.setColor(QPalette.ColorRole.ToolTipText,      text)
    p.setColor(QPalette.ColorRole.Text,             text)
    p.setColor(QPalette.ColorRole.Button,           btn)
    p.setColor(QPalette.ColorRole.ButtonText,       text)
    p.setColor(QPalette.ColorRole.BrightText,       QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Link,             QColor(80, 140, 220))
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
