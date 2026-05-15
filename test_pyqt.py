from PyQt6.QtCore import pyqtSignal, QObject
from PyQt6.QtWidgets import QApplication

app = QApplication([])

class Sender(QObject):
    sig = pyqtSignal(object, int, int, object, int)

class Receiver(QObject):
    def _on_rows_moved(self, *args):
        print("Args handled:", args)

s = Sender()
r = Receiver()

s.sig.connect(r._on_rows_moved)
s.sig.emit(None, 1, 2, None, 3)
