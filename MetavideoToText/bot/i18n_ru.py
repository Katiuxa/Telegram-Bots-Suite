"""Traducciones al ruso (se fusionan en bot.i18n.STRINGS)."""

RU: dict[str, str] = {
    "menu_home": "🏠 Главное меню",
    "menu_help": "❓ Справка",
    "input_placeholder": "Отправьте аудио, видео или ссылку…",
    "lang_changed": "✅ Язык приложения: *русский*.",
    "btn_back": "« Назад",
    "btn_summarize": "📝 Краткое содержание",
    "btn_txt": "📄 Файл .txt",
    "btn_pdf": "📕 PDF",
    "btn_mp3": "🎵 Аудио MP3",
    "btn_mp3_direct": "⬇️ Скачать MP3 (без данных)",
    "btn_link_transcribe": "📝 Транскрибировать в текст",
    "btn_link_mp3_only": "🎵 Аудио MP3",
    "link_choose_mode": (
        "🔗 *Ссылка получена*\n\n"
        "Что нужно?\n"
        "· *Транскрибировать* — текст с абзацами и собеседниками\n"
        "· *Аудио MP3* — название/артист опционально (или прямая загрузка на следующем шаге)"
    ),
    "link_mode_cancelled": "Ссылка отменена. Отправьте другую, когда будете готовы.",
    "progress_mp3_only": "Только MP3",
    "mp3_prompt_title": "🎵 *Аудио MP3*\n\nНапишите *название аудио*:",
    "mp3_prompt_author": "Теперь *имя автора* (исполнитель):",
    "mp3_meta_cancelled": "Отменено. Используйте *Аудио сразу* или меню.",
    "no_session_audio": (
        "Нет сохранённого аудио для этой транскрипции. "
        "Транскрибируйте файл снова, чтобы скачать MP3."
    ),
    "session_audio_too_big": (
        "Не удалось уложить один MP3 в лимит Telegram (~48 МБ). "
        "Аудио слишком длинное; попробуйте более короткую ссылку YouTube."
    ),
    "btn_read_tg": "📖 Читать в Telegram",
    "btn_index": "📑 Оглавление",
    "btn_highlights": "⭐ Главное",
    "btn_search": "🔍 Поиск",
    "search_prompt": (
        "🔍 *Поиск в транскрипции*\n\n"
        "Введите *слово или фразу* (без учёта регистра и ударений).\n"
        "Каждый фрагмент с *минутами и секундами*."
    ),
    "btn_search_again": "🔍 Другое слово",
    "search_too_short": (
        "Введите *минимум 2 символа*.\n\n"
        "_Напишите другое слово здесь или используйте кнопки ниже._"
    ),
    "search_no_results": (
        "Не найдено *«{query}»* в активном тексте "
        "(без учёта регистра и ударений).\n\n"
        "_Напишите другое слово в чат или нажмите кнопки ниже._"
    ),
    "search_many_results": "Найдено *{total}* фрагментов. Листайте стрелками.",
    "search_result_title": "🔍 *«{query}»* · *{cur}/{total}*",
    "search_result_time": "⏱ *{start}* – *{end}*",
    "search_result_excerpt": "Фрагмент:",
    "search_prev": "◀ Пред.",
    "search_next": "След. ▶",
    "search_indicator": "{cur}/{total}",
    "search_nav_toast": "Результат {cur} из {total}",
    "search_expired": "Поиск устарел. Нажмите 🔍 Поиск снова.",
    "search_again_toast": "Введите слово или фразу",
    "btn_send_another": "📤 Отправить другой файл",
    "btn_cancel": "❌ Отмена",
    "btn_audio": "🎤 Аудио",
    "btn_video": "🎬 Видео",
    "btn_link": "🔗 Ссылка",
    "btn_how_it_works": "❓ Как это работает",
    "page_prev": "◀ Пред. стр.",
    "page_next": "След. стр. ▶",
    "page_indicator": "Стр. {cur}/{total}",
    "page_toast": "Страница {cur} из {total}",
    "text_prev": "◀ Пред. текст",
    "text_next": "След. текст ▶",
    "fragment_indicator": "Фрагмент {cur}/{total}",
    "chapter_indicator": "Глава {cur}/{total}",
    "chapter_prev": "◀ Пред. глава",
    "chapter_next": "След. глава ▶",
    "chapter_list": "📑 Список глав",
    "highlight_indicator": "Момент {cur}/{total}",
    "highlight_prev": "◀ Пред. момент",
    "highlight_next": "След. момент ▶",
    "highlight_list": "⭐ Список моментов",
    "index_txt": "📄 TXT оглавления",
    "index_pdf": "📕 PDF оглавления",
    "highlights_txt": "📄 TXT главного",
    "highlights_pdf": "📕 PDF главного",
    "toc_page_prev": "◀ Пред. стр.",
    "toc_page_next": "След. стр. ▶",
    "toc_page_indicator": "Стр. {cur}/{total}",
    "transcript_actions": "📎 Действия с транскрипцией",
    "transcript_ready": "✅ *Транскрипция готова*\n\n",
    "transcript_header_first": (
        "✅ *Транскрипция* (1/{total})\n\n"
        "💡 _Файл .txt или PDF = полный текст._\n\n"
    ),
    "transcript_header": "✅ *Транскрипция* ({cur}/{total})\n\n",
    "summary_header_single": "📝 *Краткое содержание* (весь текст)\n\n",
    "summary_header": "📝 *Краткое содержание* ({cur}/{total})\n\n",
    "continues_part": "📄 *Продолжение ({cur}/{total})*\n\n",
    "read_tg_ready": (
        "📖 *Читать в Telegram*\n\n"
        "Удобный вид для телефона: главы, время и ясные абзацы.\n\n"
        "{url}"
    ),
    "read_tg_done": "Ссылка готова. Откройте для спокойного чтения.",
    "read_tg_fail": "Не удалось создать чтение в Telegram.",
    "no_transcript_saved": "Нет сохранённой транскрипции.",
    "no_index_saved": "Нет сохранённого оглавления.",
    "no_highlights_saved": "Нет сохранённых моментов.",
    "no_summary_saved": "Нет сохранённого краткого содержания.",
    "file_sent": "✅ {label} отправлен.",
    "pdf_fallback_txt": "⚠️ PDF не удался; отправляю TXT.",
    "busy_new_file": (
        "⏳ Обрабатываю новый файл. Когда закончится (или Отмена), "
        "можно отправить другой. Кнопки выше работают с готовым текстом."
    ),
    "busy_message": (
        "⏳ *Идёт загрузка или транскрипция*.\n\n"
        "• Если уже есть текст, можно "
        "*Оглавление, Главное, .txt, PDF, Читать в Telegram или Краткое содержание*.\n"
        "• Чтобы остановить: *❌ Отмена* в сообщении прогресса."
    ),
    "cancelled": "🛑 *Отменено.* Можно отправить другой файл или ссылку.",
    "mode_audio": (
        "🎤 *Аудио*\n\n"
        "Отправьте аудио или голосовое когда угодно.\n"
        "Можно и *без этой кнопки*."
    ),
    "mode_video": (
        "🎬 *Видео*\n\n"
        "Отправьте видео когда угодно.\n"
        "Можно и *без этой кнопки*."
    ),
    "mode_link": (
        "🔗 *Ссылка*\n\n"
        "Вставьте ссылку TikTok, Reels, X или YouTube.\n"
        "Можно и *без этой кнопки*."
    ),
    "mode_default": "Отправьте содержимое.",
    "progress_audio": "Ваше аудио",
    "progress_video": "Ваше видео",
    "progress_link": "Ваша ссылка",
    "progress_summary": "Краткое содержание",
    "progress_export_index": "Оглавление",
    "progress_export_highlights": "Главное",
    "progress_export_file": "Файл",
    "progress_read_tg": "Читать в Telegram",
    "index_toc_title": "📑 *Оглавление* — {total} глав",
    "index_toc_hint": "Выберите главу (как в транскрипции):",
    "index_toc_page": "_Страница списка {cur} из {total}_",
    "highlights_toc_title": "⭐ *Главное* — {total} ключевых моментов",
    "highlights_toc_hint": "Выберите момент (как в оглавлении):",
    "chapter_default": "Глава",
    "no_text_segment": "_(Нет текста в этом фрагменте.)_",
    "tg_title": "Транскрипция",
    "tg_intro": "Удобное чтение в Telegram · ~{words} слов · длительность {duration}",
    "tg_toc": "Главы",
    "tg_footer": (
        "Создано MetavideoToText · Нажмите главу, чтобы перейти в видео"
    ),
    "no_quote_saved": "_(Цитата не сохранена.)_",
    "highlight_default": "Важное",
    "send_audio": (
        "🎤 Отправьте голосовое, аудио в Telegram "
        "или файл (MP3, M4A, WAV, OGG, FLAC…)."
    ),
    "send_video": "🎬 Отправьте видео.",
    "preparing": "⏳ Подготовка…",
    "preparing_summary": "⏳ Готовлю краткое содержание…",
    "preparing_file": "⏳ Готовлю файл…",
    "index_opening": "⏳ Открываю оглавление…",
    "index_creating": "⏳ Создаю оглавление…",
    "highlights_opening": "⏳ Открываю главное…",
    "highlights_creating": "⏳ Выбираю важное…",
    "need_transcript_first": "Сначала транскрибируйте; затем кнопки результата.",
    "summary_need_transcript": (
        "📝 *Краткое содержание* — *после* транскрипции.\n\n"
        "Сначала отправьте аудио, видео или ссылку и дождитесь полного текста. "
        "Затем нажмите *Краткое содержание*."
    ),
    "export_need_transcript": "Сначала транскрибируйте; затем выберите экспорт.",
    "error_audio": "❌ Ошибка аудио: {detail}",
    "error_video": "❌ Ошибка видео: {detail}",
    "summary_done": (
        "Краткое содержание готово. Страницы или «Назад» для других действий."
    ),
}
