import html
import sqlite3
import sys

import requests
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


OLLAMA_URL = "http://localhost:11434/api/chat"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


class ChatDatabase:
    def __init__(self):
        self.init_db()

    def init_db(self):
        with sqlite3.connect("chat_history.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    def create_conversation(self, title="Новый диалог"):
        with sqlite3.connect("chat_history.db") as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO conversations (title) VALUES (?)", (title,))
            return cursor.lastrowid

    def get_all_conversations(self):
        with sqlite3.connect("chat_history.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title FROM conversations ORDER BY created_at DESC")
            return cursor.fetchall()

    def save_message(self, conv_id, role, content):
        with sqlite3.connect("chat_history.db") as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
                (conv_id, role, content),
            )

    def get_messages(self, conv_id):
        with sqlite3.connect("chat_history.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
                (conv_id,),
            )
            return [{"role": role, "content": content} for role, content in cursor.fetchall()]

    def clear_messages(self, conv_id):
        with sqlite3.connect("chat_history.db") as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))

    def delete_conversation(self, conv_id):
        with sqlite3.connect("chat_history.db") as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))

    def save_setting(self, key, value):
        with sqlite3.connect("chat_history.db") as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

    def get_setting(self, key):
        with sqlite3.connect("chat_history.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else ""


class ResponseWorker(QThread):
    response_ready = pyqtSignal(str)

    def __init__(self, messages, model_name, api_key):
        super().__init__()
        self.messages = messages
        self.model_name = model_name
        self.api_key = api_key

    def run(self):
        if self.model_name == "Локальная Ollama":
            text = self.ask_ollama()
        else:
            text = self.ask_openai()
        self.response_ready.emit(text)

    def ask_ollama(self):
        try:
            response = requests.post(
                OLLAMA_URL,
                json={"model": "llama2", "messages": self.messages, "stream": False},
                timeout=120,
            )
            if response.status_code == 200:
                return response.json().get("message", {}).get("content", "Ollama вернула пустой ответ.")
            return "Ollama не готова. Проверьте, что запущена Ollama и установлена модель llama2."
        except requests.RequestException:
            return "Нет подключения к Ollama. Установите Ollama, выполните ollama pull llama2 и повторите запрос."

    def ask_openai(self):
        if not self.api_key:
            return "Для OpenAI-режима сначала укажите API-ключ в настройках."
        if not self.api_key.startswith("sk-"):
            return "API-ключ выглядит неверно. Проверьте ключ в настройках."

        model = "gpt-4" if self.model_name == "GPT-4" else "gpt-3.5-turbo"
        try:
            response = requests.post(
                OPENAI_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": model, "messages": self.messages, "temperature": 0.7},
                timeout=60,
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            if response.status_code == 401:
                return "OpenAI вернул ошибку 401. Проверьте API-ключ."
            return f"OpenAI вернул ошибку HTTP {response.status_code}."
        except requests.RequestException:
            return "Не удалось подключиться к OpenAI API."


class SettingsDialog(QDialog):
    def __init__(self, current_key, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        title = QLabel("OpenAI API-ключ")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))

        self.api_input = QLineEdit()
        self.api_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_input.setPlaceholderText("sk-...")
        self.api_input.setText(current_key)

        note = QLabel("Оставьте поле пустым, если хотите использовать только локальную Ollama.")
        note.setWordWrap(True)

        buttons = QHBoxLayout()
        save_btn = QPushButton("Сохранить")
        cancel_btn = QPushButton("Отмена")
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)

        layout.addWidget(title)
        layout.addWidget(self.api_input)
        layout.addWidget(note)
        layout.addLayout(buttons)

    @property
    def api_key(self):
        return self.api_input.text().strip()


class AIAssistant(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Danil AI 2.0")
        self.setMinimumSize(1100, 720)

        self.db = ChatDatabase()
        self.current_conversation_id = None
        self.worker = None
        self.api_key = self.db.get_setting("api_key")

        self.init_ui()
        self.load_conversations()
        if self.conv_list.count() == 0:
            self.new_conversation()
        else:
            self.conv_list.setCurrentRow(0)
            self.switch_conversation(self.conv_list.item(0))

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main = QHBoxLayout(central)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(12)

        sidebar = QVBoxLayout()
        sidebar_box = QWidget()
        sidebar_box.setFixedWidth(280)
        sidebar_box.setLayout(sidebar)

        title = QLabel("Danil AI 2.0")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))

        new_btn = QPushButton("Новый диалог")
        delete_btn = QPushButton("Удалить диалог")
        settings_btn = QPushButton("Настройки")
        new_btn.clicked.connect(self.new_conversation)
        delete_btn.clicked.connect(self.delete_conversation)
        settings_btn.clicked.connect(self.open_settings)

        self.conv_list = QListWidget()
        self.conv_list.itemClicked.connect(self.switch_conversation)

        sidebar.addWidget(title)
        sidebar.addWidget(new_btn)
        sidebar.addWidget(delete_btn)
        sidebar.addWidget(QLabel("Диалоги:"))
        sidebar.addWidget(self.conv_list, 1)
        sidebar.addWidget(settings_btn)

        content = QVBoxLayout()

        toolbar = QHBoxLayout()
        model_label = QLabel("Модель:")
        self.model_combo = QComboBox()
        self.model_combo.addItems(["Локальная Ollama", "GPT-3.5 Turbo", "GPT-4"])
        self.model_combo.setMinimumWidth(230)
        self.model_combo.setMinimumHeight(36)

        clear_btn = QPushButton("Очистить диалог")
        clear_btn.clicked.connect(self.clear_conversation)

        toolbar.addWidget(model_label)
        toolbar.addWidget(self.model_combo)
        toolbar.addStretch()
        toolbar.addWidget(clear_btn)

        self.chat_view = QTextBrowser()
        self.chat_view.setMinimumHeight(360)
        self.chat_view.setStyleSheet(
            "QTextBrowser { background: white; color: black; border: 1px solid black; padding: 10px; font-size: 14px; }"
        )

        self.input_field = QTextEdit()
        self.input_field.setFixedHeight(110)
        self.input_field.setPlaceholderText("Введите сообщение...")
        self.input_field.setStyleSheet(
            "QTextEdit { background: white; color: black; border: 1px solid black; font-size: 14px; padding: 8px; }"
        )

        bottom = QHBoxLayout()
        self.status_label = QLabel("Готово. AI отвечает только после нажатия Отправить.")
        self.send_btn = QPushButton("Отправить")
        self.send_btn.setMinimumWidth(140)
        self.send_btn.clicked.connect(self.send_message)
        bottom.addWidget(self.status_label)
        bottom.addStretch()
        bottom.addWidget(self.send_btn)

        content.addLayout(toolbar)
        content.addWidget(self.chat_view, 1)
        content.addWidget(self.input_field)
        content.addLayout(bottom)

        main.addWidget(sidebar_box)
        main.addLayout(content, 1)

        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self.send_message)
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.new_conversation)

    def append_message(self, author, text):
        self.chat_view.append(f"<p><b>{html.escape(author)}:</b><br>{html.escape(text).replace(chr(10), '<br>')}</p>")
        self.chat_view.verticalScrollBar().setValue(self.chat_view.verticalScrollBar().maximum())

    def load_conversations(self):
        self.conv_list.clear()
        for conv_id, title in self.db.get_all_conversations():
            item = QListWidgetItem(title)
            item.setData(256, conv_id)
            self.conv_list.addItem(item)

    def select_current_conversation(self):
        for i in range(self.conv_list.count()):
            item = self.conv_list.item(i)
            if item.data(256) == self.current_conversation_id:
                self.conv_list.setCurrentItem(item)
                return

    def new_conversation(self):
        conv_id = self.db.create_conversation("Новый диалог")
        self.current_conversation_id = conv_id
        self.load_conversations()
        self.select_current_conversation()
        self.chat_view.setHtml(
            "<b>Новый диалог.</b><br>"
            "Выберите модель сверху, введите сообщение и нажмите <b>Отправить</b>."
        )

    def switch_conversation(self, item):
        self.current_conversation_id = item.data(256)
        self.chat_view.clear()
        messages = self.db.get_messages(self.current_conversation_id)
        if not messages:
            self.chat_view.setHtml("<b>Диалог пуст.</b><br>Введите сообщение и нажмите Отправить.")
            return
        for msg in messages:
            self.append_message("Вы" if msg["role"] == "user" else "Danil AI", msg["content"])

    def delete_conversation(self):
        if not self.current_conversation_id:
            return
        reply = QMessageBox.question(self, "Удаление", "Удалить текущий диалог?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_conversation(self.current_conversation_id)
        self.current_conversation_id = None
        self.load_conversations()
        if self.conv_list.count() == 0:
            self.new_conversation()
        else:
            self.conv_list.setCurrentRow(0)
            self.switch_conversation(self.conv_list.item(0))

    def clear_conversation(self):
        if not self.current_conversation_id:
            return
        reply = QMessageBox.question(self, "Очистка", "Очистить сообщения текущего диалога?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.db.clear_messages(self.current_conversation_id)
        self.chat_view.setHtml("<b>Диалог очищен.</b><br>Введите новое сообщение.")

    def open_settings(self):
        dialog = SettingsDialog(self.api_key, self)
        if dialog.exec():
            self.api_key = dialog.api_key
            self.db.save_setting("api_key", self.api_key)
            self.status_label.setText("Настройки сохранены.")

    def send_message(self):
        if self.worker and self.worker.isRunning():
            return

        text = self.input_field.toPlainText().strip()
        if not text:
            self.status_label.setText("Введите сообщение перед отправкой.")
            return
        if not self.current_conversation_id:
            self.new_conversation()

        if "Диалог пуст" in self.chat_view.toPlainText() or "Новый диалог" in self.chat_view.toPlainText():
            self.chat_view.clear()

        self.input_field.clear()
        self.db.save_message(self.current_conversation_id, "user", text)
        self.append_message("Вы", text)

        messages = self.db.get_messages(self.current_conversation_id)
        self.status_label.setText("Генерация ответа...")
        self.send_btn.setEnabled(False)

        self.worker = ResponseWorker(messages, self.model_combo.currentText(), self.api_key)
        self.worker.response_ready.connect(self.show_response)
        self.worker.finished.connect(lambda: self.send_btn.setEnabled(True))
        self.worker.start()

    def show_response(self, text):
        if self.current_conversation_id:
            self.db.save_message(self.current_conversation_id, "assistant", text)
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
    window = AIAssistant()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
