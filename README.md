# Telegram Data Bot

Телеграм бот для сбора данных пользователей и сохранения в Google Sheets.

## Структура данных
- Name (Имя)
- Phone (Телефон) 
- Address (Адрес)
- Telegram nickname
- Telegram Id
- Time (Время)

## Деплой на PythonAnywhere (БЕСПЛАТНО)

### 1. Создание аккаунта
- Идите на https://www.pythonanywhere.com
- Регистрируйтесь (бесплатно)
- Подтвердите email

### 2. Загрузка кода
- Откройте консоль: Dashboard → Tasks → Consoles → Bash
- Склонируйте репозиторий:
```bash
git clone https://github.com/ВАШ_USERNAME/telegram-data-bot.git
cd telegram-data-bot
```

### 3. Установка зависимостей
```bash
pip3.10 install --user -r requirements.txt
```

### 4. Настройка переменных окружения
- Создайте файл .env:
```bash
nano .env
```
- Скопируйте содержимое из config_pythonanywhere.txt
- Добавьте GOOGLE_PRIVATE_KEY (из private_key.txt)

### 5. Создание Always On Task
- Dashboard → Tasks → Always On Tasks
- Command: `python3.10 /home/yourusername/telegram-data-bot/main.py`
- Нажмите Create

### Готово! Бот работает 24/7 бесплатно! 🎉

**Преимущества PythonAnywhere:**
- ✅ Полностью бесплатно
- ✅ Простая настройка
- ✅ Always On задачи
- ✅ SSH доступ
- ✅ Telegram API включен в whitelist

## O'rnatish

1. **Virtual environment yarating va paketlarni o'rnating:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # macOS/Linux
   # yoki
   venv\Scripts\activate     # Windows
   pip install -r requirements.txt
   ```

2. **Konfiguratsiya faylini sozlang:**
   - `config.env` faylini oching
   - Quyidagi ma'lumotlarni to'ldiring:
     ```
     BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
     SPREADSHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms
     GOOGLE_CREDENTIALS_FILE=keys.json
     SHEET_NAME=
     ```

3. **Telegram Bot Token oling:**
   - [@BotFather](https://t.me/botfather) ga o'ting
   - Yangi bot yarating yoki mavjud bot tokenini oling
   - Token ni `config.env` faylida `BOT_TOKEN` ga qo'ying

4. **Google Sheets sozlang:**
   - [Google Sheets](https://sheets.google.com) da yangi jadval yarating
   - Jadval URL dan ID ni oling (masalan: `https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit`)
   - ID ni `config.env` faylida `SPREADSHEET_ID` ga qo'ying
   - `keys.json` faylidagi service account email (`sheet-writer@spheric-algebra-465618-t4.iam.gserviceaccount.com`) ni jadvalga ruxsat bering:
     - Jadvalni oching → "Share" tugmasini bosing
     - Email manzilini qo'shing va "Editor" ruxsatini bering

5. **Botni ishga tushiring:**
   ```bash
   source venv/bin/activate  # Virtual environment ni faollashtiring
   python main.py
   ```

## Foydalanish

1. Botga `/start` buyrug'ini yuboring
2. FIO ni kiriting (lotin yozuvida)
3. Telefon raqamini kiriting (+998 XX XXX XX XX formatida)
4. To'liq manzilni kiriting
5. Ma'lumotlarni tekshirib, saqlang

## Fayllar

- `main.py` - Asosiy bot kodi
- `keys.json` - Google Service Account ma'lumotlari
- `config.env` - Konfiguratsiya fayli
- `requirements.txt` - Python paketlari ro'yxati
