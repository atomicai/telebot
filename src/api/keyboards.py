from typing import Optional
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from src.running.restore import RethinkDocStore  # Импортируем класс работы с БД


class KeyboardManager:
    def __init__(self, store: RethinkDocStore):
        self.store = store

    def get_main_menu_keyboard(
        self,
        context,
        selected_thread: Optional[dict] = None,
        active_thread: Optional[dict] = None
    ) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
        """Создает главное меню для управления чатами"""
        if not context.user_data.get("menu_active", False):
            return ReplyKeyboardRemove()

        if selected_thread:
            is_active = selected_thread["id"] == (active_thread["id"] if active_thread else None)
            first_button_text = f"✅ {selected_thread['title']}" if is_active else f"◻️ {selected_thread['title']}"
            buttons = [
                [
                    KeyboardButton(first_button_text),
                    KeyboardButton("💬 Сообщения"),
                ],
                [
                    KeyboardButton("✏️ Отредактировать"),
                    KeyboardButton("🗑️ Удалить"),
                ],
                [
                    KeyboardButton("📜 Чаты"),
                    KeyboardButton("➕ Новый чат"),
                ],
            ]
        else:
            buttons = [
                [
                    KeyboardButton("📜 Чаты"),
                    KeyboardButton("➕ Новый чат"),
                ]
            ]

        return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

    async def generate_thread_keyboard(self, user: dict, limit=10, offset=0) -> InlineKeyboardMarkup:
        """Генерирует клавиатуру со списком чатов пользователя"""
        threads, total = await self.store.get_user_threads(user["id"], limit=limit, offset=offset)
        offset = int(offset)

        keyboard = [
            [
                InlineKeyboardButton(
                    text=f"{t['title']}{' ✅' if t['id'] == user.get('active_thread_id') else ' ◻️'}",
                    callback_data=f"thread_{t['id']}",
                )
            ]
            for t in threads
        ]

        pagination_buttons = []

        if offset > 0:
            pagination_buttons.append(
                InlineKeyboardButton("⬅️", callback_data=f"page_{max(0, offset - limit)}")
            )

        pagination_buttons.append(InlineKeyboardButton("➕", callback_data="create_new_chat"))

        if offset + limit < total:
            pagination_buttons.append(
                InlineKeyboardButton("➡️", callback_data=f"page_{offset + limit}")
            )

        keyboard.append(pagination_buttons)
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_delete_confirmation_keyboard(thread_id: int) -> InlineKeyboardMarkup:
        """Клавиатура для подтверждения удаления чата"""
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Да", callback_data=f"confirm_delete_{thread_id}"),
                    InlineKeyboardButton("❌ Нет", callback_data="cancel_delete"),
                ]
            ]
        )

    @staticmethod
    def get_rating_keyboard(message_id: int) -> InlineKeyboardMarkup:
        """Клавиатура для оценки сообщений"""
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("👍", callback_data=f"rate_{message_id}_like"),
                    InlineKeyboardButton("👎", callback_data=f"rate_{message_id}_dislike"),
                ]
            ]
        )

