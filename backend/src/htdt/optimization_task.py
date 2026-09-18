from __future__ import annotations

from collections.abc import Callable
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot


class _SearchTask(QObject):
    completed = Signal(object, object, object)

    def __init__(self, key: str, operation: Callable[[Event], object]) -> None:
        super().__init__()
        self.key = key
        self.operation = operation
        self.cancel_event = Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
        if self.cancel_event.is_set():
            self.completed.emit(self.key, None, 'cancelled')
            return
        try:
            result = self.operation(self.cancel_event)
        except Exception as exc:
            if self.cancel_event.is_set():
                self.completed.emit(self.key, None, 'cancelled')
            else:
                self.completed.emit(self.key, None, str(exc))
        else:
            if self.cancel_event.is_set():
                self.completed.emit(self.key, None, 'cancelled')
            else:
                self.completed.emit(self.key, result, None)
