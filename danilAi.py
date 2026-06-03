import html
import sys

import requests
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama2"


class ResponseWorker(QThread):
    response_ready = pyqtSignal(str)

    def __init__(self, messages):
        super().__init__()
        self.messages = messages

    def run(self):
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "messages": self.messages,
                    "stream": False,
                },
                timeout=120,
            )
            if response.status_code == 200:
                text = response.json().get("message", {}).get("content", "")
                if not text:
                    text = "Ollama вернула пустой ответ."
            else:
                text = (
                    "Ollama не готова к работе.\n"
                    "Проверьте, что Ollama запущена и модель llama2 установлена."
                )
        except requests.RequestException:
            text = (
                "Нет подключения к Ollama.\n"
                "1. Установите Ollama.\n"
                "2. Выполните команду: ollama pull llama2\n"
                "3. Запустите Ollama и отправьте сообщение снова."
            )

        self.response_ready.emit(text)


class DanilAssistant(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Danil AI 1.0")
        self.setMinimumSize(1000, 700)

        self.messages = []
        self.worker = None

        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("Danil AI 1.0")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))

        info = QLabel(
            "Версия 1.0 работает только с локальной Ollama. "
            "Перед отправкой сообщения установите Ollama и выполните: ollama pull llama2"
        )
        info.setWordWrap(True)

        self.chat_view = QTextBrowser()
        self.chat_view.setMinimumHeight(360)
        self.chat_view.setStyleSheet(
            "QTextBrowser { background: white; color: black; border: 1px solid black; padding: 10px; font-size: 14px; }"
        )
        self.chat_view.setHtml(
            "<b>Чат пуст.</b><br>"
            "Введите сообщение снизу и нажмите <b>Отправить</b>. "
            "Программа не обращается к AI сама по себе."
        )

        self.input_field = QTextEdit()
        self.input_field.setFixedHeight(110)
        self.input_field.setPlaceholderText("Введите сообщение...")
        self.input_field.setStyleSheet(
            "QTextEdit { background: white; color: black; border: 1px solid black; font-size: 14px; padding: 8px; }"
        )

        buttons = QHBoxLayout()
        self.status_label = QLabel("Готово. Ожидаю сообщение пользователя.")

        clear_btn = QPushButton("Очистить чат")
        clear_btn.clicked.connect(self.clear_chat)

        self.send_btn = QPushButton("Отправить")
        self.send_btn.setMinimumWidth(140)
        self.send_btn.clicked.connect(self.send_message)

        buttons.addWidget(self.status_label)
        buttons.addStretch()
        buttons.addWidget(clear_btn)
        buttons.addWidget(self.send_btn)

        root.addWidget(title)
        root.addWidget(info)
        root.addWidget(self.chat_view, 1)
        root.addWidget(self.input_field)
        root.addLayout(buttons)

        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self.send_message)

    def append_message(self, author, text):
        safe_author = html.escape(author)
        safe_text = html.escape(text).replace("\n", "<br>")
        self.chat_view.append(f"<p><b>{safe_author}:</b><br>{safe_text}</p>")
        self.chat_view.verticalScrollBar().setValue(self.chat_view.verticalScrollBar().maximum())

    def clear_chat(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Подождите", "Сначала дождитесь завершения ответа.")
            return
        self.messages.clear()
        self.chat_view.setHtml("<b>Чат очищен.</b><br>Введите новое сообщение.")
        self.status_label.setText("Чат очищен.")

    def send_message(self):
        if self.worker and self.worker.isRunning():
            return

        text = self.input_field.toPlainText().strip()
        if not text:
            self.status_label.setText("Введите сообщение перед отправкой.")
            return

        if not self.messages:
            self.chat_view.clear()

        self.input_field.clear()
        self.messages.append({"role": "user", "content": text})
        self.append_message("Вы", text)

        self.status_label.setText("Отправляю запрос в Ollama...")
        self.send_btn.setEnabled(False)

        self.worker = ResponseWorker(self.messages.copy())
        self.worker.response_ready.connect(self.show_response)
        self.worker.finished.connect(lambda: self.send_btn.setEnabled(True))
        self.worker.start()

    def show_response(self, text):
        self.messages.append({"role": "assistant", "content": text})
        self.append_message("Danil AI", text)
        self.status_label.setText("Готово.")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Подождите", "Сначала дождитесь завершения ответа.")
            event.ignore()
            return
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = DanilAssistant()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
