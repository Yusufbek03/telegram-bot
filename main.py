# main.py

import os
import re
from datetime import datetime
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from telegram import (
    Update, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    ContextTypes, CallbackQueryHandler, filters
)
import warnings
from telegram.warnings import PTBUserWarning
from gspread.exceptions import APIError, WorksheetNotFound
import json

# ── Google Sheets ID normalizatsiyasi ────────────────────────────────────────
def _normalize_spreadsheet_id(value: str) -> str:
    """Accepts either a pure ID or a full Google Sheets URL and returns the ID."""
    if not value:
        return ""
    v = value.strip()
    # If user pasted full URL, extract between '/d/' and next '/'
    if "docs.google.com" in v and "/d/" in v:
        try:
            part = v.split("/d/")[1]
            return part.split("/")[0]
        except Exception:
            return v
    return v

# ── .env dan yuklash ──────────────────────────────────────────────────────────
# Railway muhitida .env mavjud bo'lmasligi mumkin
try:
    load_dotenv(".env")
except:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN")
raw_sheet_id = os.getenv("SPREADSHEET_ID")
SPREADSHEET_ID = _normalize_spreadsheet_id(raw_sheet_id or "")
SHEET_NAME = os.getenv("SHEET_NAME", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@topicnowbot")

# Google Service Account credentials from environment
GOOGLE_PRIVATE_KEY = os.getenv("GOOGLE_PRIVATE_KEY", "")
GOOGLE_CLIENT_EMAIL = os.getenv("GOOGLE_CLIENT_EMAIL", "")
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID", "")
warnings.filterwarnings("ignore", category=PTBUserWarning)

# If user pasted full URL, inform about normalization
if raw_sheet_id and raw_sheet_id != SPREADSHEET_ID and "docs.google.com" in raw_sheet_id:
    pass  # Normalization applied

# ── Suhbat holatlari (Conversation states) ───────────────────────────────────
ASK_NAME, ASK_PHONE, ASK_ADDRESS, CONFIRM, EDIT_INPUT = range(5)

# ── Telefon formati: qat'iy "+998 94 999 99 99" ──────────────────────────────
PHONE_RE = re.compile(r'^\+998 \d{2} \d{3} \d{2} \d{2}$')

# ── Lotin yozuvidagi matnni tekshirish (kirill bo‘lsa ogohlantiramiz) ────────

def format_phone_number(raw: str) -> str:
    """
    Kiruvchi raqamni +998 XX XXX XX XX ko'rinishiga normallashtiradi.
    Qabul qilinadigan variantlar:
      +998939999999, 998939999999, 89399999999, 939999999
    Aks holda — asl matnni qaytaradi.
    """
    s = (raw or "").strip()
    digits = re.sub(r"\D", "", s)

    def fmt(d: str) -> str:
        # d: '998' + 9 raqam (jami 12 raqam)
        return f"+998 {d[3:5]} {d[5:8]} {d[8:10]} {d[10:12]}"

    # 1) +998XXXXXXXXX yoki 998XXXXXXXXX  => 12 raqam '998' + 9
    if digits.startswith("998") and len(digits) == 12:
        return fmt(digits)

    # 2) 8XXXXXXXXXX (11 raqam, eski prefiks 8) => 998 + qolgan 10 dan faqat so'nggi 9 raqam
    if digits.startswith("8") and len(digits) == 11:
        d = "998" + digits[1:]
        return fmt(d)

    # 3) XXYYYYYYY (faqat 9 raqam — operator + raqamlar)
    if len(digits) == 9:
        d = "998" + digits
        return fmt(d)

    # Aks holda formatlashni iloji yo'q — aslini qaytaramiz
    return s

CYRILLIC_RE = re.compile(r'[\u0400-\u04FF]')
def is_latin_text(text: str) -> bool:
    """Matnda kirill bo‘lmasligi kerak (faqat lotin, raqam, belgilar)."""
    return not CYRILLIC_RE.search(text or "")

# ── Tugmalar ─────────────────────────────────────────────────────────────────
def summary_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ FIO-ni tahrirlash", callback_data="edit_name")],
        [InlineKeyboardButton("✏️ Telefonni tahrirlash", callback_data="edit_phone")],
        [InlineKeyboardButton("✏️ Manzilni tahrirlash", callback_data="edit_address")],
        [InlineKeyboardButton("🔄 Hammasini boshidan", callback_data="edit_all")],
        [InlineKeyboardButton("✅ Saqlash", callback_data="save"),
         InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")]
    ])

async def show_summary(update_or_cb, context: ContextTypes.DEFAULT_TYPE):
    d = context.user_data  # type: ignore
    text = (
        "Iltimos, ma'lumotlarni tekshiring:\n"
        f"• FIO: {d.get('name')}\n"  # type: ignore
        f"• Telefon: {d.get('phone')}\n"  # type: ignore
        f"• Manzil: {d.get('address')}\n\n"  # type: ignore
        "Kerakli amalni tanlang:"
    )
    if isinstance(update_or_cb, Update) and update_or_cb.callback_query:
        await update_or_cb.callback_query.edit_message_text(text, reply_markup=summary_keyboard())
    else:
        await update_or_cb.message.reply_text(text, reply_markup=summary_keyboard())  # type: ignore

# ── Google Sheets yordamchi funktsiyalari ────────────────────────────────────
def _get_worksheet():
    """Service account orqali avtorizatsiya va worksheet qaytarish."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    
    # Create credentials from environment variables
    credentials_info = {
        "type": "service_account",
        "project_id": GOOGLE_PROJECT_ID,
        "private_key": GOOGLE_PRIVATE_KEY.replace('\\n', '\n'),
        "client_email": GOOGLE_CLIENT_EMAIL,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    
    creds = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    client = gspread.authorize(creds)

    try:
        sh = client.open_by_key(SPREADSHEET_ID)
    except APIError as e:
        status = getattr(e.response, "status_code", None)
        if status == 404:
            sa_email = GOOGLE_CLIENT_EMAIL
            raise RuntimeError(
                "Google API 404: Spreadsheet topilmadi yoki ruxsat yo'q. "
                f"SPREADSHEET_ID: {SPREADSHEET_ID}. "
                f"Jadvalni quyidagi service account bilan baham ko'ring: {sa_email}"
            )
        raise

    # Worksheet tanlash yoki yaratish
    if SHEET_NAME:
        try:
            return sh.worksheet(SHEET_NAME)
        except WorksheetNotFound:
            # Agar nomlangan list topilmasa, avtomatik yaratamiz
            return sh.add_worksheet(title=SHEET_NAME, rows=1000, cols=10)
    else:
        return sh.sheet1

def _append_to_sheet(payload: dict):
    """
    Bir qatorni Google Sheet ga qo'shish.
    Qaytaradi: (ok: bool, error: str)
    """
    try:
        ws = _get_worksheet()
        # Name, Phone, address, Telegram nickname, Telegram Id, Time
        row_data = [
            payload.get("name", ""),
            payload.get("phone", ""),
            payload.get("address", ""),
            payload.get("username", ""),
            str(payload.get("user_id", "")),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]
        
        ws.append_row(
            row_data,
            value_input_option="RAW"  # type: ignore
        )
        return True, ""
    except APIError as e:
        status = getattr(e.response, "status_code", None)
        if status == 404:
            return False, (
                "Google API 404: Spreadsheet topilmadi yoki ruxsat berilmagan. "
                "SPREADSHEET_ID noto'g'ri bo'lishi mumkin yoki service accountga kirish bermagansiz."
            )
        return False, f"Google API xatosi: {e}"
    except WorksheetNotFound:
        return False, (
            "SHEET_NAME noto'g'ri: ko'rsatilgan list mavjud emas va yaratib bo'lmadi."
        )
    except Exception as e:
        return False, str(e)

async def send_notification_to_channel(context: ContextTypes.DEFAULT_TYPE, payload: dict):
    """
    Kanalga yangi foydalanuvchi haqida xabar yuborish.
    """
    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notification_text = (
            "🔔 Yangi foydalanuvchi qo'shildi:\n\n"
            f"👤 FIO: {payload.get('name', 'N/A')}\n"
            f"📞 Номер: {payload.get('phone', 'N/A')}\n"
            f"🏠 Адрес: {payload.get('address', 'N/A')}\n"
            f"🏷 Никнайм: @{payload.get('username', 'N/A')}\n"
            f"🆔 ИД номер: {payload.get('user_id', 'N/A')}\n"
            f"⏰ Время: {current_time}\n\n"
            "✅ Человек занесен в базу данных"
        )
        
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=notification_text
        )
        return True
    except Exception as e:
        print(f"Kanalga xabar yuborishda xatolik: {e}")
        return False

# ── /start ───────────────────────────────────────────────────────────────────
UZ_ONLY_NOTE = (
    "⚠️ Iltimos, faqat **o‘zbek tilida (lotin yozuvida)** yozing.\n"
    "Masalan: Otabek Qodirov yoki +998 94 999 99 99"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()  # type: ignore
    welcome = (
        "Assalomu alaykum! 👋\n"
        "Ushbu bot ma'lumotlaringizni qabul qilib, Google Jadvalga saqlaydi.\n\n"
        "Ma'lumotlarni quyidagi tartibda yuboring:\n"
        "1) FIO (masalan: Otabek Qodirov)\n"
        "2) Telefon raqami (qat'iy format: +998 94 999 99 99)\n"
        "3) To‘liq manzil (posilkani qabul qilish uchun)\n"
        "   Masalan: Namangan viloyati, Uychi tumani, Soku MFY, "
        "Gulzor mahalla, Donishmatlar ko‘chasi, 15-uy\n\n"
        f"{UZ_ONLY_NOTE}\n\n"
        "Boshladik. Iltimos, FIO yozing:"
    )
    await update.message.reply_text(welcome, reply_markup=ReplyKeyboardRemove())  # type: ignore
    return ASK_NAME

# ── FIO qabul qilish ─────────────────────────────────────────────────────────
async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()  # type: ignore
    if not is_latin_text(name):
        await update.message.reply_text("Iltimos, **lotin yozuvida** yozing. " + UZ_ONLY_NOTE)  # type: ignore
        return ASK_NAME
    if not name:
        await update.message.reply_text("Iltimos, FIO kiriting.")  # type: ignore
        return ASK_NAME

    context.user_data["name"] = name  # type: ignore
    await update.message.reply_text("Telefon raqamni kiriting (namuna: +998 94 999 99 99):")  # type: ignore
    return ASK_PHONE

# ── Telefon qabul qilish ─────────────────────────────────────────────────────
async def ask_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = (update.message.text or "").strip()  # type: ignore
    phone = format_phone_number(phone)
    if not is_latin_text(phone):
        await update.message.reply_text("Iltimos, **lotin yozuvida** yozing. " + UZ_ONLY_NOTE)  # type: ignore
        return ASK_PHONE
    if not PHONE_RE.match(phone):
        await update.message.reply_text(  # type: ignore
            "❌ Telefon formati xato!\n"
            "To'g'ri namuna: +998 94 999 99 99\n"
            "Iltimos, qaytadan kiriting."
        )
        return ASK_PHONE

    context.user_data["phone"] = phone  # type: ignore
    prompt = (
        "Endi **TO'LIQ MANZIL** ni yuboring (posilkani qabul qilish uchun):\n"
        "Namuna: Namangan viloyati, Uychi tumani, Soku MFY, "
        "Gulzor mahalla, Donishmatlar ko'chasi, 15-uy"
    )
    await update.message.reply_text(prompt)  # type: ignore
    return ASK_ADDRESS

# ── Manzil qabul qilish va tasdiqlash ────────────────────────────────────────
async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = (update.message.text or "").strip()  # type: ignore
    if not is_latin_text(address):
        await update.message.reply_text("Iltimos, **lotin yozuvida** yozing. " + UZ_ONLY_NOTE)  # type: ignore
        return ASK_ADDRESS
    if len(address) < 5:
        await update.message.reply_text("Manzil juda qisqa. Iltimos, to'liq manzil kiriting.")  # type: ignore
        return ASK_ADDRESS

    context.user_data["address"] = address  # type: ignore
    await show_summary(update, context)
    return CONFIRM

# ── Tasdiqlash oynasidagi tugmalar ───────────────────────────────────────────
async def on_confirm_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query  # type: ignore
    await query.answer()  # type: ignore
    data = query.data  # type: ignore

    if data == "edit_name":
        context.user_data["edit_field"] = "name"  # type: ignore
        await query.edit_message_text("✏️ Yangi FIO ni kiriting:")  # type: ignore
        return EDIT_INPUT

    if data == "edit_phone":
        context.user_data["edit_field"] = "phone"  # type: ignore
        await query.edit_message_text("✏️ Yangi telefon (namuna: +998 94 999 99 99):")  # type: ignore
        return EDIT_INPUT

    if data == "edit_address":
        context.user_data["edit_field"] = "address"  # type: ignore
        await query.edit_message_text("✏️ Yangi to'liq manzilni kiriting:")  # type: ignore
        return EDIT_INPUT

    if data == "edit_all":
        context.user_data.clear()  # type: ignore
        await query.edit_message_text("Boshladik. Iltimos, FIO yozing:")  # type: ignore
        return ASK_NAME

    if data == "save":
        payload = {
            "name": context.user_data.get("name", ""),  # type: ignore
            "phone": context.user_data.get("phone", ""),  # type: ignore
            "address": context.user_data.get("address", ""),  # type: ignore
            "username": update.effective_user.username or "",  # type: ignore
            "user_id": update.effective_user.id  # type: ignore
        }
        ok, err = _append_to_sheet(payload)
        if ok:
            # Ma'lumotlar muvaffaqiyatli saqlangach, kanalga xabar yuborish
            notification_sent = await send_notification_to_channel(context, payload)
            if notification_sent:
                await query.edit_message_text("✅ Saqlandi va kanal xabardor qilindi! Yangi yozuv uchun /start yuboring.")  # type: ignore
            else:
                await query.edit_message_text("✅ Saqlandi, lekin kanalga xabar yuborishda muammo. Yangi yozuv uchun /start yuboring.")  # type: ignore
        else:
            await query.edit_message_text(  # type: ignore
                f"⚠️ Saqlashda xatolik.\nSabab: {err}\n"
                "Iltimos, birozdan so'ng qayta urinib ko'ring."
            )
        context.user_data.clear()  # type: ignore
        return ConversationHandler.END

    if data == "cancel":
        await query.edit_message_text("Bekor qilindi. Qayta boshlash uchun /start yuboring.")  # type: ignore
        context.user_data.clear()  # type: ignore
        return ConversationHandler.END

    return ConversationHandler.END

# ── «Tahrirlash»dan keyingi matn qabul qilish ───────────────────────────────
async def on_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data.get("edit_field")  # type: ignore
    value = (update.message.text or "").strip()  # type: ignore

    if not field:
        await update.message.reply_text("Xatolik yuz berdi. Qayta boshlash: /start")  # type: ignore
        context.user_data.clear()  # type: ignore
        return ConversationHandler.END

    if not is_latin_text(value):
        await update.message.reply_text("Iltimos, **lotin yozuvida** yozing. " + UZ_ONLY_NOTE)  # type: ignore
        return EDIT_INPUT

    if field == "phone":
        value = format_phone_number(value)
        if not PHONE_RE.match(value):
            await update.message.reply_text(  # type: ignore
                "❌ Telefon formati xato!\n"
                "To'g'ri namuna: +998 94 999 99 99\n"
                "Iltimos, qaytadan kiriting."
            )
            return EDIT_INPUT

    context.user_data[field] = value  # type: ignore
    context.user_data.pop("edit_field", None)  # type: ignore
    await show_summary(update, context)
    return CONFIRM

# ── /cancel ──────────────────────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()  # type: ignore
    await update.message.reply_text("Bekor qilindi. Qayta boshlash uchun /start yuboring.", reply_markup=ReplyKeyboardRemove())  # type: ignore
    return ConversationHandler.END

# ── Dastur ishga tushirish ───────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi.")
    if not SPREADSHEET_ID:
        raise RuntimeError("SPREADSHEET_ID topilmadi.")
    if not GOOGLE_PRIVATE_KEY or not GOOGLE_CLIENT_EMAIL:
        raise RuntimeError("Google credentials topilmadi.")

    application = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
            ASK_PHONE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_address)],
            ASK_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
            CONFIRM:     [CallbackQueryHandler(on_confirm_buttons)],
            EDIT_INPUT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, on_edit_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="data_intake_conversation",
        persistent=False,
    )

    application.add_handler(conv)
    application.add_handler(CommandHandler("cancel", cancel))

    PORT = int(os.getenv("PORT", 8080))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
