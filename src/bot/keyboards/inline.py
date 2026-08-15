"""
Inline keyboard builders for interactive bot actions.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def build_author_pages_keyboard(author_id: str, total_pages: int) -> InlineKeyboardMarkup:
    """Builds interactive page selection buttons for an author download request."""
    buttons = [
        [
            InlineKeyboardButton(text="📄 下载第 1 页 (最新)", callback_data=f"author_dl:{author_id}:1-1")
        ],
        [
            InlineKeyboardButton(text="📚 下载前 3 页", callback_data=f"author_dl:{author_id}:1-3"),
            InlineKeyboardButton(text="📚 下载前 5 页", callback_data=f"author_dl:{author_id}:1-5"),
        ],
        [
            InlineKeyboardButton(text=f"📦 全部下载 (共 {total_pages} 页)", callback_data=f"author_dl:{author_id}:1-{total_pages}")
        ],
        [
            InlineKeyboardButton(text="✏️ 自定义页码范围", callback_data=f"author_custom:{author_id}"),
            InlineKeyboardButton(text="❌ 取消", callback_data="cancel_action")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_openlist_button(openlist_url: str) -> InlineKeyboardMarkup:
    """Builds a direct link button pointing to OpenList folder."""
    buttons = [
        [
            InlineKeyboardButton(text="📂 在 OpenList 中查看", url=openlist_url)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
