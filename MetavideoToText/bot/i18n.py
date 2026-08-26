"""Textos de interfaz: español, inglés, francés y ruso."""

from __future__ import annotations

from telegram.ext import ContextTypes

from bot.i18n_ru import RU

DEFAULT_LANG = "es"
SUPPORTED = frozenset({"es", "en", "fr", "ru"})

LANG_MENU = {
    "es": "🇪🇸 Español",
    "en": "🇬🇧 English",
    "fr": "🇫🇷 Français",
    "ru": "🇷🇺 Русский",
    "auto": "🌐 Detección",
}

STRINGS: dict[str, dict[str, str]] = {
    "menu_home": {
        "es": "🏠 Menú principal",
        "en": "🏠 Main menu",
        "fr": "🏠 Menu principal",
    },
    "menu_help": {
        "es": "❓ Ayuda",
        "en": "❓ Help",
        "fr": "❓ Aide",
    },
    "input_placeholder": {
        "es": "Envía audio, vídeo o enlace…",
        "en": "Send audio, video or link…",
        "fr": "Envoyez audio, vidéo ou lien…",
        "ru": "Отправьте аудио, видео или ссылку…",
    },
    "lang_name": {
        "es": "español",
        "en": "English",
        "fr": "français",
        "ru": "русский",
    },
    "lang_changed": {
        "es": "✅ Idioma de la app: *español*.",
        "en": "✅ App language: *English*.",
        "fr": "✅ Langue de l'app : *français*.",
        "ru": "✅ Язык приложения: *русский*.",
    },
    "idioma_prompt": {
        "es": "*Idioma de la aplicación*\n\nElige el idioma del menú:",
        "en": "*App language*\n\nChoose the menu language:",
        "fr": "*Langue de l'application*\n\nChoisissez la langue du menu :",
        "ru": "*Язык приложения*\n\nВыберите язык меню:",
    },
    "audio_lang_prompt": {
        "es": (
            "🎙 *Idioma del audio*\n\n"
            "Elige el idioma que se oye (o *detección*) para facilitar la transcripción:"
        ),
        "en": (
            "🎙 *Audio language*\n\n"
            "Pick the spoken language (or *detect*) to help transcription:"
        ),
        "fr": (
            "🎙 *Langue de l'audio*\n\n"
            "Choisissez la langue parlée (ou *détection*) pour faciliter la transcription :"
        ),
        "ru": (
            "🎙 *Язык аудио*\n\n"
            "Выберите язык речи (или *определение*) для транскрипции:"
        ),
    },
    "job_choose_mode": {
        "es": (
            "✅ Idioma del audio: *{label}*\n\n"
            "¿Qué quieres hacer?\n"
            "· *Transcribir* — texto con párrafos\n"
            "· *Audio MP3* — descarga el audio"
        ),
        "en": (
            "✅ Audio language: *{label}*\n\n"
            "What do you want?\n"
            "· *Transcribe* — text with paragraphs\n"
            "· *Audio MP3* — download the audio"
        ),
        "fr": (
            "✅ Langue de l'audio : *{label}*\n\n"
            "Que voulez-vous faire ?\n"
            "· *Transcrire* — texte avec paragraphes\n"
            "· *Audio MP3* — télécharger l'audio"
        ),
        "ru": (
            "✅ Язык аудио: *{label}*\n\n"
            "Что сделать?\n"
            "· *Транскрибировать* — текст с абзацами\n"
            "· *Аудио MP3* — скачать аудио"
        ),
    },
    "audio_lang_cancelled": {
        "es": "❌ Cancelado. Envía otro archivo o enlace cuando quieras.",
        "en": "❌ Cancelled. Send another file or link whenever you want.",
        "fr": "❌ Annulé. Envoyez un autre fichier ou lien quand vous voulez.",
        "ru": "❌ Отменено. Отправьте другой файл или ссылку когда захотите.",
    },
    "auto_detect_banner": {
        "es": (
            "🌐 *Idioma detectado:* {detected}\n"
            "Texto en idioma original. "
        ),
        "en": (
            "🌐 *Detected language:* {detected}\n"
            "Text in the original language. "
        ),
        "fr": (
            "🌐 *Langue détectée :* {detected}\n"
            "Texte dans la langue originale. "
        ),
        "ru": (
            "🌐 *Определён язык:* {detected}\n"
            "Текст на исходном языке. "
        ),
    },
    "auto_detect_translated": {
        "es": "Traducción al *{target}* incluida abajo.",
        "en": "*{target}* translation included below.",
        "fr": "Traduction en *{target}* ci-dessous.",
        "ru": "Перевод на *{target}* ниже.",
    },
    "auto_detect_no_translate": {
        "es": "Pulsa *Traducir…* si quieres otra versión.",
        "en": "Tap *Translate…* if you want another version.",
        "fr": "Appuyez sur *Traduire…* pour une autre version.",
        "ru": "Нажмите *Перевести…* для другой версии.",
    },
    "auto_detect_translate_failed": {
        "es": "No pude traducir automáticamente; usa *Traducir…*.",
        "en": "Auto-translation failed; use *Translate…*.",
        "fr": "Traduction auto échouée ; utilisez *Traduire…*.",
        "ru": "Автоперевод не удался; нажмите *Перевести…*.",
    },
    "btn_back": {"es": "« Atrás", "en": "« Back", "fr": "« Retour"},
    "btn_summarize": {"es": "📝 Resumir", "en": "📝 Summarize", "fr": "📝 Résumer"},
    "btn_txt": {"es": "📄 Archivo .txt", "en": "📄 .txt file", "fr": "📄 Fichier .txt"},
    "btn_pdf": {"es": "📕 PDF", "en": "📕 PDF", "fr": "📕 PDF"},
    "btn_mp3": {
        "es": "🎵 Audio MP3",
        "en": "🎵 Audio MP3",
        "fr": "🎵 Audio MP3",
        "ru": "🎵 Аудио MP3",
    },
    "btn_mp3_direct": {
        "es": "⬇️ Descargar MP3 (sin datos)",
        "en": "⬇️ Download MP3 (no details)",
        "fr": "⬇️ Télécharger MP3 (sans infos)",
        "ru": "⬇️ Скачать MP3 (без данных)",
    },
    "btn_link_transcribe": {
        "es": "📝 Transcribir a texto",
        "en": "📝 Transcribe to text",
        "fr": "📝 Transcrire en texte",
        "ru": "📝 Транскрибировать в текст",
    },
    "btn_link_mp3_only": {
        "es": "🎵 Audio MP3",
        "en": "🎵 Audio MP3",
        "fr": "🎵 Audio MP3",
        "ru": "🎵 Аудио MP3",
    },
    "btn_link_mp3_now": {
        "es": "⬇️ MP3 directo (sin preguntas)",
        "en": "⬇️ Direct MP3 (no prompts)",
        "fr": "⬇️ MP3 direct (sans questions)",
        "ru": "⬇️ MP3 сразу (без вопросов)",
    },
    "link_choose_mode": {
        "es": (
            "🔗 *Enlace recibido*\n\n"
            "Primero elige el *idioma del audio*, luego Transcribir o MP3."
        ),
        "en": (
            "🔗 *Link received*\n\n"
            "First pick the *audio language*, then Transcribe or MP3."
        ),
        "fr": (
            "🔗 *Lien reçu*\n\n"
            "Choisissez d'abord la *langue de l'audio*, puis Transcrire ou MP3."
        ),
        "ru": (
            "🔗 *Ссылка получена*\n\n"
            "Сначала выберите *язык аудио*, затем Транскрибировать или MP3."
        ),
    },
    "link_mode_cancelled": {
        "es": "Enlace cancelado. Envía otro cuando quieras.",
        "en": "Link cancelled. Send another when you like.",
        "fr": "Lien annulé. Renvoyez un lien quand vous voulez.",
        "ru": "Ссылка отменена. Отправьте другую, когда будете готовы.",
    },
    "progress_mp3_only": {
        "es": "Solo MP3",
        "en": "MP3 only",
        "fr": "MP3 seulement",
        "ru": "Только MP3",
    },
    "mp3_prompt_title": {
        "es": (
            "🎵 *Audio MP3*\n\n"
            "Escribe el *nombre de la pista* (título).\n"
            "Si lo dejas vacío, usaré el título del vídeo/enlace.\n\n"
            "O pulsa *Descargar MP3 (sin datos)* cuando quieras."
        ),
        "en": (
            "🎵 *Audio MP3*\n\n"
            "Send the *track title*.\n"
            "Leave it empty to use the video/link title.\n\n"
            "Or tap *Download MP3 (no details)* anytime."
        ),
        "fr": (
            "🎵 *Audio MP3*\n\n"
            "Envoyez le *titre de la piste*.\n"
            "Laissez vide pour utiliser le titre de la vidéo/lien.\n\n"
            "Ou appuyez sur *Télécharger MP3 (sans infos)* à tout moment."
        ),
        "ru": (
            "🎵 *Аудио MP3*\n\n"
            "Напишите *название трека*.\n"
            "Пустое поле — возьму название из видео/ссылки.\n\n"
            "Или нажмите *Скачать MP3 (без данных)* в любой момент."
        ),
    },
    "mp3_prompt_author": {
        "es": (
            "Ahora escribe el *nombre del artista* (opcional).\n"
            "Si lo dejas vacío, el MP3 irá sin artista.\n\n"
            "Siempre puedes pulsar *Descargar MP3 (sin datos)*."
        ),
        "en": (
            "Now send the *artist* name (optional).\n"
            "Leave it empty for no artist in the MP3.\n\n"
            "You can always tap *Download MP3 (no details)*."
        ),
        "fr": (
            "Maintenant le *nom de l'artiste* (optionnel).\n"
            "Laissez vide pour un MP3 sans artiste.\n\n"
            "Vous pouvez toujours appuyer sur *Télécharger MP3 (sans infos)*."
        ),
        "ru": (
            "Теперь *имя артиста* (необязательно).\n"
            "Пустое поле — MP3 без исполнителя.\n\n"
            "В любой момент можно нажать *Скачать MP3 (без данных)*."
        ),
    },
    "mp3_meta_cancelled": {
        "es": "Cancelado. Puedes usar *Audio directo* o volver al menú.",
        "en": "Cancelled. Use *Direct audio* or go back to the menu.",
        "fr": "Annulé. Utilisez *Audio direct* ou le menu.",
        "ru": "Отменено. Используйте *Аудио сразу* или меню.",
    },
    "no_session_audio": {
        "es": (
            "No hay audio guardado de esta transcripción. "
            "Transcribe de nuevo el archivo para poder descargar el MP3."
        ),
        "en": (
            "No saved audio for this transcript. "
            "Transcribe the file again to download the MP3."
        ),
        "fr": (
            "Pas d'audio enregistré pour cette transcription. "
            "Retranscrivez le fichier pour télécharger le MP3."
        ),
        "ru": (
            "Нет сохранённого аудио для этой транскрипции. "
            "Транскрибируйте файл снова, чтобы скачать MP3."
        ),
    },
    "session_audio_too_big": {
        "es": (
            "No pude preparar un MP3 que quepa en Telegram (~48 MB) "
            "y la subida externa está desactivada. "
            "Activa EXTERNAL_UPLOAD_ENABLED=1 o prueba un enlace más corto."
        ),
        "en": (
            "Could not fit an MP3 within Telegram's ~48 MB limit "
            "and external upload is disabled. "
            "Enable EXTERNAL_UPLOAD_ENABLED=1 or try a shorter link."
        ),
        "fr": (
            "Impossible de tenir le MP3 dans la limite Telegram (~48 Mo) "
            "et l'envoi externe est désactivé. "
            "Activez EXTERNAL_UPLOAD_ENABLED=1 ou essayez un lien plus court."
        ),
        "ru": (
            "Не удалось уложить MP3 в лимит Telegram (~48 МБ), "
            "а внешняя загрузка отключена. "
            "Включите EXTERNAL_UPLOAD_ENABLED=1 или попробуйте более короткую ссылку."
        ),
    },
    "mp3_external_header": {
        "es": "<b>{title}</b>\nMP3 · {size} MB",
        "en": "<b>{title}</b>\nMP3 · {size} MB",
        "fr": "<b>{title}</b>\nMP3 · {size} Mo",
        "ru": "<b>{title}</b>\nMP3 · {size} МБ",
    },
    "mp3_external_server": {
        "es": "Servidor: {provider} (hasta ~{max_mb} MB)",
        "en": "Host: {provider} (up to ~{max_mb} MB)",
        "fr": "Serveur : {provider} (jusqu'à ~{max_mb} Mo)",
        "ru": "Сервер: {provider} (до ~{max_mb} МБ)",
    },
    "mp3_external_expiry": {
        "es": "⏱ Tienes {expiry} para descargar.",
        "en": "⏱ You have {expiry} to download.",
        "fr": "⏱ Vous avez {expiry} pour télécharger.",
        "ru": "⏱ У вас {expiry} на скачивание.",
    },
    "mp3_external_howto": {
        "es": "📥 Abre el enlace y pulsa Descargar (o ⋮ → Descargar).",
        "en": "📥 Open the link and tap Download (or ⋮ → Download).",
        "fr": "📥 Ouvrez le lien et appuyez sur Télécharger (ou ⋮ → Télécharger).",
        "ru": "📥 Откройте ссылку и нажмите Скачать (или ⋮ → Скачать).",
    },
    "mp3_external_download": {
        "es": "Descargar MP3",
        "en": "Download MP3",
        "fr": "Télécharger MP3",
        "ru": "Скачать MP3",
    },
    "mp3_external_sent": {
        "es": "Enlace MP3 enviado ({label}).",
        "en": "MP3 link sent ({label}).",
        "fr": "Lien MP3 envoyé ({label}).",
        "ru": "Ссылка MP3 отправлена ({label}).",
    },
    "mp3_external_limit": {
        "es": "Límite de descargas grandes: {detail}",
        "en": "Large download limit: {detail}",
        "fr": "Limite de gros fichiers : {detail}",
        "ru": "Лимит больших загрузок: {detail}",
    },
    "btn_read_tg": {
        "es": "📖 Leer en Telegram",
        "en": "📖 Read in Telegram",
        "fr": "📖 Lire dans Telegram",
    },
    "btn_index": {"es": "📑 Índice", "en": "📑 Index", "fr": "📑 Index"},
    "btn_highlights": {"es": "⭐ Highlights", "en": "⭐ Highlights", "fr": "⭐ Temps forts"},
    "btn_search": {
        "es": "🔍 Buscar",
        "en": "🔍 Search",
        "fr": "🔍 Rechercher",
        "ru": "🔍 Поиск",
    },
    "search_prompt": {
        "es": (
            "🔍 *Buscar en la transcripción*\n\n"
            "Escribe la *palabra o frase* (ignoro tildes y mayúsculas).\n"
            "Te mostraré cada fragmento con *minuto y segundo*."
        ),
        "en": (
            "🔍 *Search the transcript*\n\n"
            "Type a *word or phrase* (accents and case ignored).\n"
            "Each match shows *minutes and seconds*."
        ),
        "fr": (
            "🔍 *Rechercher dans la transcription*\n\n"
            "Tapez un *mot ou une phrase* (accents et majuscules ignorés).\n"
            "Chaque occurrence affiche *minutes et secondes*."
        ),
        "ru": (
            "🔍 *Поиск в транскрипции*\n\n"
            "Введите *слово или фразу* (без учёта регистра и ударений).\n"
            "Каждый фрагмент с *минутами и секундами*."
        ),
    },
    "btn_search_again": {
        "es": "🔍 Otra palabra",
        "en": "🔍 Another word",
        "fr": "🔍 Autre mot",
        "ru": "🔍 Другое слово",
    },
    "search_too_short": {
        "es": (
            "Escribe *al menos 2 letras* para buscar.\n\n"
            "_Puedes escribir otra palabra aquí o usar los botones de abajo._"
        ),
        "en": (
            "Type *at least 2 characters* to search.\n\n"
            "_You can type another word here or use the buttons below._"
        ),
        "fr": (
            "Tapez *au moins 2 caractères*.\n\n"
            "_Écrivez un autre mot ici ou utilisez les boutons ci-dessous._"
        ),
        "ru": (
            "Введите *минимум 2 символа*.\n\n"
            "_Напишите другое слово здесь или используйте кнопки ниже._"
        ),
    },
    "search_no_results": {
        "es": (
            "No encontré *«{query}»* en el texto activo "
            "(sin tildes ni mayúsculas).\n\n"
            "_Escribe otra palabra en el chat o pulsa los botones de abajo._"
        ),
        "en": (
            "No match for *«{query}»* in the active text "
            "(accents and case ignored).\n\n"
            "_Type another word in the chat or use the buttons below._"
        ),
        "fr": (
            "Aucun résultat pour *« {query} »* dans le texte actif "
            "(accents et majuscules ignorés).\n\n"
            "_Tapez un autre mot ici ou utilisez les boutons ci-dessous._"
        ),
        "ru": (
            "Не найдено *«{query}»* в активном тексте "
            "(без учёта регистра и ударений).\n\n"
            "_Напишите другое слово в чат или нажмите кнопки ниже._"
        ),
    },
    "search_many_results": {
        "es": "Encontré *{total}* fragmentos. Usa las flechas para navegar.",
        "en": "Found *{total}* matches. Use the arrows to browse.",
        "fr": "*{total}* occurrences. Utilisez les flèches.",
        "ru": "Найдено *{total}* фрагментов. Листайте стрелками.",
    },
    "search_result_title": {
        "es": "🔍 *«{query}»* · resultado *{cur}/{total}*",
        "en": "🔍 *«{query}»* · match *{cur}/{total}*",
        "fr": "🔍 *« {query} »* · *{cur}/{total}*",
        "ru": "🔍 *«{query}»* · *{cur}/{total}*",
    },
    "search_result_time": {
        "es": "⏱ *{start}* – *{end}*",
        "en": "⏱ *{start}* – *{end}*",
        "fr": "⏱ *{start}* – *{end}*",
        "ru": "⏱ *{start}* – *{end}*",
    },
    "search_result_excerpt": {
        "es": "Fragmento:",
        "en": "Excerpt:",
        "fr": "Extrait :",
        "ru": "Фрагмент:",
    },
    "search_prev": {"es": "◀ Anterior", "en": "◀ Previous", "fr": "◀ Préc.", "ru": "◀ Пред."},
    "search_next": {"es": "Siguiente ▶", "en": "Next ▶", "fr": "Suiv. ▶", "ru": "След. ▶"},
    "search_indicator": {
        "es": "{cur}/{total}",
        "en": "{cur}/{total}",
        "fr": "{cur}/{total}",
        "ru": "{cur}/{total}",
    },
    "search_nav_toast": {
        "es": "Resultado {cur} de {total}",
        "en": "Match {cur} of {total}",
        "fr": "Résultat {cur} sur {total}",
        "ru": "Результат {cur} из {total}",
    },
    "search_expired": {
        "es": "La búsqueda caducó. Pulsa 🔍 Buscar de nuevo.",
        "en": "Search expired. Tap 🔍 Search again.",
        "fr": "Recherche expirée. Touchez 🔍 Rechercher.",
        "ru": "Поиск устарел. Нажмите 🔍 Поиск снова.",
    },
    "search_again_toast": {
        "es": "Escribe la palabra o frase a buscar",
        "en": "Type the word or phrase to find",
        "fr": "Tapez le mot ou la phrase",
        "ru": "Введите слово или фразу",
    },
    "btn_send_another": {
        "es": "📤 Enviar otro archivo",
        "en": "📤 Send another file",
        "fr": "📤 Envoyer un autre fichier",
    },
    "btn_cancel": {"es": "❌ Cancelar", "en": "❌ Cancel", "fr": "❌ Annuler"},
    "btn_audio": {"es": "🎤 Audio", "en": "🎤 Audio", "fr": "🎤 Audio", "ru": "🎤 Аудио"},
    "btn_video": {"es": "🎬 Vídeo", "en": "🎬 Video", "fr": "🎬 Vidéo"},
    "btn_link": {"es": "🔗 Enlace web", "en": "🔗 Web link", "fr": "🔗 Lien web"},
    "btn_how_it_works": {
        "es": "❓ Cómo funciona",
        "en": "❓ How it works",
        "fr": "❓ Comment ça marche",
    },
    "btn_translate": {
        "es": "🌐 Traducir…",
        "en": "🌐 Translate…",
        "fr": "🌐 Traduire…",
        "ru": "🌐 Перевести…",
    },
    "variant_original_short": {
        "es": "📄 Original ({code})",
        "en": "📄 Original ({code})",
        "fr": "📄 Original ({code})",
        "ru": "📄 Оригинал ({code})",
    },
    "translate_menu_title": {
        "es": (
            "🌐 *Traducir transcripción*\n\n"
            "Idioma original: *{source}*\n"
            "Elige idioma destino."
        ),
        "en": (
            "🌐 *Translate transcript*\n\n"
            "Original language: *{source}*\n"
            "Pick a target language."
        ),
        "fr": (
            "🌐 *Traduire la transcription*\n\n"
            "Langue originale : *{source}*\n"
            "Choisissez la langue cible."
        ),
        "ru": (
            "🌐 *Перевод транскрипции*\n\n"
            "Исходный язык: *{source}*\n"
            "Выберите язык перевода."
        ),
    },
    "translate_working": {
        "es": "Traduciendo a {target}…",
        "en": "Translating to {target}…",
        "fr": "Traduction en {target}…",
        "ru": "Перевод на {target}…",
    },
    "translate_done_short": {
        "es": "Traducción a *{target}* lista.",
        "en": "*{target}* translation ready.",
        "fr": "Traduction en *{target}* prête.",
        "ru": "Перевод на *{target}* готов.",
    },
    "translate_done": {
        "es": (
            "✅ *Traducción lista* ({target}).\n\n"
            "Ahora trabajas con la versión traducida "
            "(resumen, .txt, índice, highlights…).\n"
            "Cambia a *Original* cuando quieras volver al texto fuente."
        ),
        "en": (
            "✅ *Translation ready* ({target}).\n\n"
            "You're now using the translated version "
            "(summary, .txt, index, highlights…).\n"
            "Switch to *Original* anytime for the source text."
        ),
        "fr": (
            "✅ *Traduction prête* ({target}).\n\n"
            "Vous utilisez la version traduite "
            "(résumé, .txt, index, temps forts…).\n"
            "Revenez à *Original* pour le texte source."
        ),
        "ru": (
            "✅ *Перевод готов* ({target}).\n\n"
            "Сейчас используется перевод "
            "(краткое содержание, .txt, оглавление, главное…).\n"
            "Переключитесь на *Оригинал* для исходного текста."
        ),
    },
    "translate_switched": {
        "es": "📄 Viendo: *{label}* — resumen, export e índice usan este texto.",
        "en": "📄 Viewing: *{label}* — summary, export and index use this text.",
        "fr": "📄 Affichage : *{label}* — résumé, export et index utilisent ce texte.",
        "ru": "📄 Просмотр: *{label}* — краткое содержание, экспорт и оглавление используют этот текст.",
    },
    "translate_fail": {
        "es": "No pude traducir",
        "en": "Could not translate",
        "fr": "Traduction impossible",
        "ru": "Не удалось перевести",
    },
    "translate_no_groq": {
        "es": "Falta GROQ_API_KEY para traducir.",
        "en": "GROQ_API_KEY is required for translation.",
        "fr": "GROQ_API_KEY requis pour traduire.",
        "ru": "Для перевода нужен GROQ_API_KEY.",
    },
    "progress_translate": {
        "es": "Traducción",
        "en": "Translation",
        "fr": "Traduction",
        "ru": "Перевод",
    },
    "page_prev": {"es": "◀ Pág. anterior", "en": "◀ Prev. page", "fr": "◀ Page préc."},
    "page_next": {"es": "Pág. siguiente ▶", "en": "Next page ▶", "fr": "Page suiv. ▶"},
    "page_indicator": {"es": "Pág. {cur}/{total}", "en": "Page {cur}/{total}", "fr": "Page {cur}/{total}"},
    "page_toast": {"es": "Página {cur} de {total}", "en": "Page {cur} of {total}", "fr": "Page {cur} sur {total}"},
    "text_prev": {"es": "◀ Texto ant.", "en": "◀ Prev. text", "fr": "◀ Texte préc."},
    "text_next": {"es": "Texto sig. ▶", "en": "Next text ▶", "fr": "Texte suiv. ▶"},
    "fragment_indicator": {
        "es": "Fragmento {cur}/{total}",
        "en": "Part {cur}/{total}",
        "fr": "Fragment {cur}/{total}",
    },
    "chapter_indicator": {
        "es": "Capítulo {cur}/{total}",
        "en": "Chapter {cur}/{total}",
        "fr": "Chapitre {cur}/{total}",
    },
    "chapter_prev": {"es": "◀ Cap. anterior", "en": "◀ Prev. ch.", "fr": "◀ Ch. préc."},
    "chapter_next": {"es": "Cap. siguiente ▶", "en": "Next ch. ▶", "fr": "Ch. suiv. ▶"},
    "chapter_list": {
        "es": "📑 Lista de capítulos",
        "en": "📑 Chapter list",
        "fr": "📑 Liste des chapitres",
    },
    "highlight_indicator": {
        "es": "Highlight {cur}/{total}",
        "en": "Highlight {cur}/{total}",
        "fr": "Temps fort {cur}/{total}",
    },
    "highlight_prev": {"es": "◀ Highlight ant.", "en": "◀ Prev. highlight", "fr": "◀ Temps fort préc."},
    "highlight_next": {"es": "Highlight sig. ▶", "en": "Next highlight ▶", "fr": "Temps fort suiv. ▶"},
    "highlight_list": {
        "es": "⭐ Lista de highlights",
        "en": "⭐ Highlight list",
        "fr": "⭐ Liste des temps forts",
    },
    "index_txt": {"es": "📄 TXT del índice", "en": "📄 Index .txt", "fr": "📄 Index .txt"},
    "index_pdf": {"es": "📕 PDF del índice", "en": "📕 Index PDF", "fr": "📕 Index PDF"},
    "highlights_txt": {"es": "📄 TXT highlights", "en": "📄 Highlights .txt", "fr": "📄 Temps forts .txt"},
    "highlights_pdf": {"es": "📕 PDF highlights", "en": "📕 Highlights PDF", "fr": "📕 Temps forts PDF"},
    "toc_page_prev": {"es": "◀ Pág. anterior", "en": "◀ Prev. page", "fr": "◀ Page préc."},
    "toc_page_next": {"es": "Pág. siguiente ▶", "en": "Next page ▶", "fr": "Page suiv. ▶"},
    "toc_page_indicator": {
        "es": "Pág. {cur}/{total}",
        "en": "Page {cur}/{total}",
        "fr": "Page {cur}/{total}",
    },
    "transcript_actions": {
        "es": "📎 Acciones sobre tu transcripción",
        "en": "📎 Actions for your transcript",
        "fr": "📎 Actions sur votre transcription",
    },
    "transcript_ready": {
        "es": "✅ *Transcripción lista*\n\n",
        "en": "✅ *Transcript ready*\n\n",
        "fr": "✅ *Transcription prête*\n\n",
    },
    "transcript_header_first": {
        "es": "✅ *Transcripción* (1/{total})\n\n💡 _Archivo .txt o PDF = texto íntegro._\n\n",
        "en": "✅ *Transcript* (1/{total})\n\n💡 _.txt or PDF = full text._\n\n",
        "fr": "✅ *Transcription* (1/{total})\n\n💡 _Fichier .txt ou PDF = texte intégral._\n\n",
        "ru": "✅ *Транскрипция* (1/{total})\n\n💡 _Файл .txt или PDF = полный текст._\n\n",
    },
    "transcript_header": {
        "es": "✅ *Transcripción* ({cur}/{total})\n\n",
        "en": "✅ *Transcript* ({cur}/{total})\n\n",
        "fr": "✅ *Transcription* ({cur}/{total})\n\n",
        "ru": "✅ *Транскрипция* ({cur}/{total})\n\n",
    },
    "transcript_header_variant": {
        "es": "🌐 _Versión activa:_ *{label}*\n\n",
        "en": "🌐 _Active version:_ *{label}*\n",
        "fr": "🌐 _Version active :_ *{label}*\n\n",
        "ru": "🌐 _Активная версия:_ *{label}*\n\n",
    },
    "summary_header_single": {
        "es": "📝 *Resumen* (cubre todo el contenido)\n\n",
        "en": "📝 *Summary* (covers all content)\n\n",
        "fr": "📝 *Résumé* (couvre tout le contenu)\n\n",
    },
    "summary_header": {
        "es": "📝 *Resumen* ({cur}/{total})\n\n",
        "en": "📝 *Summary* ({cur}/{total})\n\n",
        "fr": "📝 *Résumé* ({cur}/{total})\n\n",
    },
    "continues_part": {
        "es": "📄 *Continúa ({cur}/{total})*\n\n",
        "en": "📄 *Continues ({cur}/{total})*\n\n",
        "fr": "📄 *Suite ({cur}/{total})*\n\n",
    },
    "read_tg_ready": {
        "es": (
            "📖 *Leer en Telegram*\n\n"
            "Vista optimizada para móvil: capítulos, tiempos y párrafos claros.\n\n"
            "{url}"
        ),
        "en": (
            "📖 *Read in Telegram*\n\n"
            "Mobile-friendly view: chapters, timestamps and clear paragraphs.\n\n"
            "{url}"
        ),
        "fr": (
            "📖 *Lire dans Telegram*\n\n"
            "Vue optimisée mobile : chapitres, horaires et paragraphes clairs.\n\n"
            "{url}"
        ),
    },
    "read_tg_done": {
        "es": "Enlace listo. Ábrelo para leer con calma.",
        "en": "Link ready. Open it for a comfortable read.",
        "fr": "Lien prêt. Ouvrez-le pour une lecture confortable.",
    },
    "read_tg_fail": {
        "es": "No pude crear la lectura en Telegram.",
        "en": "Could not create the Telegram reading view.",
        "fr": "Impossible de créer la vue de lecture Telegram.",
    },
    "no_transcript_saved": {
        "es": "No hay transcripción guardada.",
        "en": "No saved transcript.",
        "fr": "Aucune transcription enregistrée.",
    },
    "no_index_saved": {
        "es": "No hay índice guardado.",
        "en": "No saved index.",
        "fr": "Aucun index enregistré.",
    },
    "no_highlights_saved": {
        "es": "No hay highlights guardados.",
        "en": "No saved highlights.",
        "fr": "Aucun temps fort enregistré.",
    },
    "no_summary_saved": {
        "es": "No hay resumen guardado.",
        "en": "No saved summary.",
        "fr": "Aucun résumé enregistré.",
    },
    "file_sent": {
        "es": "✅ {label} enviado.",
        "en": "✅ {label} sent.",
        "fr": "✅ {label} envoyé.",
    },
    "pdf_fallback_txt": {
        "es": "⚠️ PDF falló; envío TXT.",
        "en": "⚠️ PDF failed; sending TXT.",
        "fr": "⚠️ Échec PDF ; envoi TXT.",
    },
    "busy_new_file": {
        "es": (
            "⏳ Sigo con tu archivo nuevo. Cuando termine (o Cancelar) "
            "podrás transcribir otro. Los botones de arriba usan el texto ya listo."
        ),
        "en": (
            "⏳ Still processing your new file. When done (or Cancel) "
            "you can transcribe another. Buttons above use the ready text."
        ),
        "fr": (
            "⏳ Traitement du nouveau fichier en cours. À la fin (ou Annuler) "
            "vous pourrez en envoyer un autre. Les boutons ci-dessus utilisent le texte prêt."
        ),
    },
    "busy_message": {
        "es": (
            "⏳ *Sigo con la descarga o transcripción* en curso.\n\n"
            "• Si ya tienes un texto anterior, puedes usar "
            "*Índice, Highlights, .txt, PDF, Leer en Telegram o Resumir*.\n"
            "• Para parar lo actual: pulsa *❌ Cancelar* en el progreso."
        ),
        "en": (
            "⏳ *Download or transcription still in progress*.\n\n"
            "• If you already have a previous transcript, you can use "
            "*Index, Highlights, .txt, PDF, Read in Telegram or Summarize*.\n"
            "• To stop the current job: tap *❌ Cancel* on the progress message."
        ),
        "fr": (
            "⏳ *Téléchargement ou transcription en cours*.\n\n"
            "• Si vous avez déjà une transcription, utilisez "
            "*Index, Temps forts, .txt, PDF, Lire dans Telegram ou Résumer*.\n"
            "• Pour arrêter : touchez *❌ Annuler* sur le message de progression."
        ),
    },
    "cancelled": {
        "es": "🛑 *Cancelado.* Puedes enviar otro archivo o enlace.",
        "en": "🛑 *Cancelled.* You can send another file or link.",
        "fr": "🛑 *Annulé.* Vous pouvez envoyer un autre fichier ou lien.",
        "ru": "🛑 *Отменено.* Можно отправить другой файл или ссылку.",
    },
    "error_file_too_big": {
        "es": (
            "📦 Ese archivo supera los 20 MB que Telegram permite a los bots.\n"
            "Comprime el vídeo, envía audio/nota de voz o pega un enlace."
        ),
        "en": (
            "📦 That file exceeds Telegram's 20 MB limit for bots.\n"
            "Compress the video, send audio/voice note, or paste a link."
        ),
        "fr": (
            "📦 Ce fichier dépasse la limite de 20 Mo de Telegram pour les bots.\n"
            "Compressez la vidéo, envoyez audio/note vocale ou collez un lien."
        ),
        "ru": (
            "📦 Файл больше 20 МБ — лимит Telegram для ботов.\n"
            "Сожмите видео, отправьте аудио/голосовое или вставьте ссылку."
        ),
    },
    "start_text": {
        "es": (
            "🏠 *MetavideoToText*\n\n"
            "Envía un audio, un vídeo o un enlace de cualquier plataforma "
            "y lo convierto en texto (o MP3).\n\n"
            "Idioma del menú: *{lang_label}*"
        ),
        "en": (
            "🏠 *MetavideoToText*\n\n"
            "Send audio, video or a link from any platform "
            "and I'll turn it into text (or MP3).\n\n"
            "Menu language: *{lang_label}*"
        ),
        "fr": (
            "🏠 *MetavideoToText*\n\n"
            "Envoyez un audio, une vidéo ou un lien de n'importe quelle plateforme "
            "et je le transforme en texte (ou MP3).\n\n"
            "Langue du menu : *{lang_label}*"
        ),
        "ru": (
            "🏠 *MetavideoToText*\n\n"
            "Отправьте аудио, видео или ссылку с любой платформы — "
            "превращу в текст (или MP3).\n\n"
            "Язык меню: *{lang_label}*"
        ),
    },
    "start_translate_pending": {
        "es": (
            "_Sin transcripción guardada._ Las nuevas serán en *{transcript}*; "
            "después podrás *Traducir…* a otros idiomas."
        ),
        "en": (
            "_No saved transcript._ New ones will be in *{transcript}*; "
            "then *Translate…* to other languages."
        ),
        "fr": (
            "_Pas encore de transcription._ Les nouvelles seront en *{transcript}* ; "
            "puis *Traduire…* vers d'autres langues."
        ),
        "ru": (
            "_Нет сохранённой транскрипции._ Новые будут на *{transcript}*; "
            "затем *Перевести…* на другие языки."
        ),
    },
    "start_translate_original": {
        "es": (
            "*Original* ({source}). Pulsa *Traducir…* para trabajar en otro idioma."
        ),
        "en": (
            "*Original* ({source}). Tap *Translate…* to work in another language."
        ),
        "fr": (
            "*Original* ({source}). Touchez *Traduire…* pour une autre langue."
        ),
        "ru": (
            "*Оригинал* ({source}). Нажмите *Перевести…* для другого языка."
        ),
    },
    "start_translate_original_saved": {
        "es": (
            "*Original* ({source}) activo. Traducciones guardadas: {saved}. "
            "Alterna con los botones del menú de la transcripción."
        ),
        "en": (
            "*Original* ({source}) active. Saved translations: {saved}. "
            "Switch via the transcript menu buttons."
        ),
        "fr": (
            "*Original* ({source}) actif. Traductions enregistrées : {saved}. "
            "Alternez via les boutons de la transcription."
        ),
        "ru": (
            "Активен *оригинал* ({source}). Сохранённые переводы: {saved}. "
            "Переключайте кнопками меню транскрипции."
        ),
    },
    "start_translate_active": {
        "es": (
            "versión traducida *{label}* _(original: {source})_. "
            "Resumen, búsqueda e índice usan esta versión."
        ),
        "en": (
            "translated version *{label}* _(original: {source})_. "
            "Summary, search and index use this version."
        ),
        "fr": (
            "version traduite *{label}* _(original : {source})_. "
            "Résumé, recherche et index suivent cette version."
        ),
        "ru": (
            "переведённая версия *{label}* _(оригинал: {source})_. "
            "Краткое содержание, поиск и оглавление используют эту версию."
        ),
    },
    "start_optional": {
        "es": "Guía rápida (opcional):",
        "en": "Quick guide (optional):",
        "fr": "Guide rapide (optionnel) :",
        "ru": "Краткая подсказка (необязательно):",
    },
    "menu_main_transcript_line": {
        "es": "",
        "en": "",
        "fr": "",
        "ru": "",
    },
    "menu_main_translate_line": {
        "es": "",
        "en": "",
        "fr": "",
        "ru": "",
    },
    "menu_main_text": {
        "es": (
            "🏠 *MetavideoToText*\n\n"
            "Envía un audio, un vídeo o un enlace de cualquier plataforma "
            "y lo convierto en texto (o MP3).\n\n"
            "Idioma del menú: *{lang_label}*"
        ),
        "en": (
            "🏠 *MetavideoToText*\n\n"
            "Send audio, video or a link from any platform "
            "and I'll turn it into text (or MP3).\n\n"
            "Menu language: *{lang_label}*"
        ),
        "fr": (
            "🏠 *MetavideoToText*\n\n"
            "Envoyez un audio, une vidéo ou un lien de n'importe quelle plateforme "
            "et je le transforme en texte (ou MP3).\n\n"
            "Langue du menu : *{lang_label}*"
        ),
        "ru": (
            "🏠 *MetavideoToText*\n\n"
            "Отправьте аудио, видео или ссылку с любой платформы — "
            "превращу в текст (или MP3).\n\n"
            "Язык меню: *{lang_label}*"
        ),
    },
    "help_text": {
        "es": (
            "📖 *Ayuda — MetavideoToText*\n\n"
            "*Qué hace*\n"
            "Convierte audio, vídeo, notas de voz y enlaces (TikTok, Reels, YouTube) "
            "en texto, con tiempos cuando el audio lo permite.\n\n"
            "*Idiomas*\n"
            "· */idioma* — idioma del menú de la app.\n"
            "· Al enviar un archivo — eliges el *idioma del audio* "
            "(o detección) y luego *Transcribir* o *MP3*.\n\n"
            "*Cómo va*\n"
            "1. Envías un archivo o enlace.\n"
            "2. Eliges idioma del audio → Transcribir o MP3.\n"
            "3. Con la transcripción: *Traducir…*, .txt, PDF, *Buscar*, enviar otro.\n\n"
            "*Buscar*\n"
            "🔍 Cada resultado muestra *minuto:segundo*; "
            "en YouTube, botón para abrir ese instante.\n\n"
            "*Traducir*\n"
            "*Traducir…* genera versiones en ES/EN/FR/RU. "
            "Alterna *Original* y traducción; export y búsqueda usan la versión activa.\n\n"
            "📦 Telegram suele limitar *~20 MB por envío* al bot.\n"
            "🔗 Para vídeos largos, pega el *enlace* (YouTube hasta ~5 h).\n"
            "🔗 TikTok/Reels: ~10 min.\n"
            "🗑 Temporales se borran solos en ~45 min.\n\n"
            "🛠 *Última actualización del bot:* `{build_version}`"
        ),
        "en": (
            "📖 *Help — MetavideoToText*\n\n"
            "*What it does*\n"
            "Turns audio, video, voice notes and links (TikTok, Reels, YouTube) "
            "into text in *Spanish, English, French or Russian*, with timestamps when possible.\n\n"
            "*Language*\n"
            "By default we follow your Telegram app language; change it with 🇪🇸 🇬🇧 🇫🇷 🇷🇺 "
            "(menu and transcripts stay in sync).\n\n"
            "*How it works*\n"
            "1. Send a file or link.\n"
            "2. Watch progress; you can *Cancel*.\n"
            "3. When ready, use *buttons* "
            "(summarize, export, read in Telegram, index, highlights, *search*).\n\n"
            "*Search*\n"
            "🔍 Find a word or phrase with *timestamps*; on YouTube, jump to that second.\n\n"
            "*Index & highlights*\n"
            "Index splits content into chapters; highlights mark key moments.\n\n"
            "*While another file processes*\n"
            "You can still use actions on your previous transcript.\n\n"
            "*Translate*\n"
            "After transcribing, *Translate…* creates versions in other languages (ES/EN/FR/RU). "
            "Switch *Original* and translation; summary, index and export use the active version.\n\n"
            "📦 Telegram usually limits *~20 MB per upload* to the bot.\n"
            "🔗 For long videos, paste the *link* (YouTube up to ~5 h → one complete MP3).\n"
            "🔗 TikTok/Reels: ~10 min.\n"
            "🍪 If YouTube fails: `cookies.txt` in the bot folder.\n"
            "🗑 Temp files auto-delete in ~45 min.\n\n"
            "🛠 *Last bot update:* `{build_version}`"
        ),
        "fr": (
            "📖 *Aide — MetavideoToText*\n\n"
            "*Fonction*\n"
            "Convertit audio, vidéo, notes vocales et liens (TikTok, Reels, YouTube) "
            "en texte en *espagnol, anglais, français ou russe*, avec horaires si possible.\n\n"
            "*Langue*\n"
            "Par défaut : celle de votre Telegram ; changez avec 🇪🇸 🇬🇧 🇫🇷 🇷🇺 "
            "(menu et transcription alignés).\n\n"
            "*Déroulement*\n"
            "1. Envoyez un fichier ou un lien.\n"
            "2. Suivez la progression ; *Annuler* possible.\n"
            "3. Transcription prête : *boutons* "
            "(résumer, exporter, lire dans Telegram, index, temps forts, *recherche*).\n\n"
            "*Rechercher*\n"
            "🔍 Mot ou phrase avec *horodatage* ; sur YouTube, lien vers l'instant.\n\n"
            "*Index et temps forts*\n"
            "L'index divise en chapitres ; les temps forts marquent l'essentiel.\n\n"
            "*Pendant un autre traitement*\n"
            "Les actions sur une transcription précédente restent disponibles.\n\n"
            "*Traduire*\n"
            "Après transcription, *Traduire…* crée des versions dans d'autres langues (ES/EN/FR/RU). "
            "Alternez *Original* et traduction ; résumé, index et export suivent la version active.\n\n"
            "📦 Telegram limite souvent *~20 Mo par envoi* au bot.\n"
            "🔗 Pour les longues vidéos, collez le *lien* (YouTube jusqu'à ~5 h → un MP3 complet).\n"
            "🔗 TikTok/Reels : ~10 min.\n"
            "🍪 Si YouTube échoue : `cookies.txt` dans le dossier du bot.\n"
            "🗑 Fichiers temporaires supprimés en ~45 min.\n\n"
            "🛠 *Dernière mise à jour :* `{build_version}`"
        ),
        "ru": (
            "📖 *Справка — MetavideoToText*\n\n"
            "*Что делает*\n"
            "Превращает аудио, видео, голосовые и ссылки (TikTok, Reels, YouTube) "
            "в текст на *испанском, английском, французском или русском*, с метками времени.\n\n"
            "*Язык*\n"
            "По умолчанию — как в Telegram; смените кнопками 🇪🇸 🇬🇧 🇫🇷 🇷🇺 "
            "(меню и транскрипция совпадают).\n\n"
            "*Как работает*\n"
            "1. Отправьте файл или ссылку.\n"
            "2. Следите за прогрессом; можно *Отменить*.\n"
            "3. Готово — *кнопки* "
            "(краткое содержание, экспорт, читать в Telegram, оглавление, главное).\n\n"
            "*Оглавление и главное*\n"
            "Оглавление делит на главы; главное — ключевые моменты.\n\n"
            "*Пока обрабатывается другой файл*\n"
            "Действия с предыдущей транскрипцией доступны.\n\n"
            "*Перевод*\n"
            "После транскрипции *Перевести…* создаёт версии на других языках (ES/EN/FR/RU). "
            "Переключайте *Оригинал* и перевод; краткое содержание, оглавление и экспорт используют активную версию.\n\n"
            "📦 Telegram обычно *~20 МБ на отправку* боту.\n"
            "🔗 Длинные видео — вставьте *ссылку* (YouTube до ~5 ч → один полный MP3).\n"
            "🔗 TikTok/Reels: ~10 мин.\n"
            "🍪 Если YouTube не работает: `cookies.txt` в папке бота.\n"
            "🗑 Временные файлы удаляются ~через 45 мин.\n\n"
            "🛠 *Обновление бота:* `{build_version}`"
        ),
    },
    "mode_audio": {
        "es": (
            "🎤 *Audio*\n\n"
            "Envía nota de voz, audio o archivo MP3/M4A/WAV (máx. ~20 MB).\n"
            "Para audios más largos, sube el vídeo a YouTube y pega el enlace 🔗."
        ),
        "en": (
            "🎤 *Audio*\n\n"
            "Send a voice note, audio or MP3/M4A/WAV file (max ~20 MB).\n"
            "For longer audio, upload to YouTube and paste the link 🔗."
        ),
        "fr": (
            "🎤 *Audio*\n\n"
            "Note vocale, audio ou fichier MP3/M4A/WAV (max ~20 Mo).\n"
            "Pour plus long : mettez sur YouTube et collez le lien 🔗."
        ),
        "ru": (
            "🎤 *Аудио*\n\n"
            "Голосовое, аудио или MP3/M4A/WAV (до ~20 МБ).\n"
            "Длиннее — загрузите на YouTube и вставьте ссылку 🔗."
        ),
    },
    "mode_video": {
        "es": (
            "🎬 *Vídeo*\n\n"
            "Envía un vídeo cuando quieras.\n"
            "También puedes mandarlo *sin pulsar este botón*."
        ),
        "en": (
            "🎬 *Video*\n\n"
            "Send a video anytime.\n"
            "You can also send it *without tapping this button*."
        ),
        "fr": (
            "🎬 *Vidéo*\n\n"
            "Envoyez une vidéo quand vous voulez.\n"
            "Vous pouvez aussi l'envoyer *sans appuyer sur ce bouton*."
        ),
    },
    "mode_link": {
        "es": (
            "🔗 *Enlace*\n\n"
            "Pega un enlace de TikTok, Reels, X o YouTube.\n"
            "También puedes pegarlo *sin pulsar este botón*."
        ),
        "en": (
            "🔗 *Link*\n\n"
            "Paste a TikTok, Reels, X or YouTube link.\n"
            "You can also paste it *without tapping this button*."
        ),
        "fr": (
            "🔗 *Lien*\n\n"
            "Collez un lien TikTok, Reels, X ou YouTube.\n"
            "Vous pouvez aussi le coller *sans appuyer sur ce bouton*."
        ),
    },
    "mode_default": {
        "es": "Envíame tu contenido.",
        "en": "Send me your content.",
        "fr": "Envoyez-moi votre contenu.",
    },
    "progress_audio": {"es": "Tu audio", "en": "Your audio", "fr": "Votre audio"},
    "progress_video": {"es": "Tu vídeo", "en": "Your video", "fr": "Votre vidéo"},
    "progress_link": {"es": "Tu enlace", "en": "Your link", "fr": "Votre lien"},
    "progress_summary": {"es": "Resumen", "en": "Summary", "fr": "Résumé"},
    "progress_export_index": {"es": "Índice", "en": "Index", "fr": "Index"},
    "progress_export_highlights": {"es": "Highlights", "en": "Highlights", "fr": "Temps forts"},
    "progress_export_file": {"es": "Archivo", "en": "File", "fr": "Fichier"},
    "progress_read_tg": {
        "es": "Leer en Telegram",
        "en": "Read in Telegram",
        "fr": "Lire dans Telegram",
    },
    "index_toc_title": {
        "es": "📑 *Índice* — {total} capítulos",
        "en": "📑 *Index* — {total} chapters",
        "fr": "📑 *Index* — {total} chapitres",
    },
    "index_toc_hint": {
        "es": "Elige un capítulo (mismo estilo que la transcripción):",
        "en": "Pick a chapter (same style as the transcript):",
        "fr": "Choisissez un chapitre (même style que la transcription) :",
    },
    "index_toc_page": {
        "es": "_Página {cur} de {total} del listado_",
        "en": "_List page {cur} of {total}_",
        "fr": "_Page {cur} sur {total} de la liste_",
    },
    "highlights_toc_title": {
        "es": "⭐ *Highlights* — {total} momentos clave",
        "en": "⭐ *Highlights* — {total} key moments",
        "fr": "⭐ *Temps forts* — {total} moments clés",
    },
    "highlights_toc_hint": {
        "es": "Elige un momento (misma idea que el índice):",
        "en": "Pick a moment (same idea as the index):",
        "fr": "Choisissez un moment (comme l'index) :",
    },
    "chapter_default": {"es": "Capítulo", "en": "Chapter", "fr": "Chapitre"},
    "no_text_segment": {
        "es": "_(Sin texto en este tramo.)_",
        "en": "_(No text in this segment.)_",
        "fr": "_(Pas de texte dans ce passage.)_",
    },
    "tg_title": {
        "es": "Transcripción",
        "en": "Transcript",
        "fr": "Transcription",
    },
    "tg_intro": {
        "es": "Lectura cómoda en Telegram · ~{words} palabras",
        "en": "Comfortable Telegram reading · ~{words} words",
        "fr": "Lecture confortable Telegram · ~{words} mots",
        "ru": "Удобное чтение в Telegram · ~{words} слов",
    },
    "tg_toc": {"es": "Capítulos", "en": "Chapters", "fr": "Chapitres"},
    "tg_footer": {
        "es": "Generado por MetavideoToText · Para tiempos e índice usa las opciones del menú",
        "en": "Generated by MetavideoToText · Use menu options for timestamps and index",
        "fr": "Généré par MetavideoToText · Utilisez le menu pour horodatage et index",
        "ru": "Создано MetavideoToText · Время и оглавление — в меню бота",
    },
    "no_quote_saved": {
        "es": "_(Sin cita guardada.)_",
        "en": "_(No saved quote.)_",
        "fr": "_(Pas de citation enregistrée.)_",
    },
    "highlight_default": {"es": "Destacado", "en": "Highlight", "fr": "Temps fort"},
    "send_audio": {
        "es": (
            "🎤 Envíame una nota de voz, un audio de Telegram "
            "o un archivo (MP3, M4A, WAV, OGG, FLAC…)."
        ),
        "en": (
            "🎤 Send a voice note, Telegram audio, "
            "or a file (MP3, M4A, WAV, OGG, FLAC…)."
        ),
        "fr": (
            "🎤 Envoyez une note vocale, un audio Telegram "
            "ou un fichier (MP3, M4A, WAV, OGG, FLAC…)."
        ),
    },
    "send_video": {
        "es": "🎬 Envíame un vídeo.",
        "en": "🎬 Send me a video.",
        "fr": "🎬 Envoyez une vidéo.",
    },
    "preparing": {"es": "⏳ Preparando…", "en": "⏳ Preparing…", "fr": "⏳ Préparation…"},
    "preparing_summary": {
        "es": "⏳ Preparando resumen…",
        "en": "⏳ Preparing summary…",
        "fr": "⏳ Préparation du résumé…",
    },
    "preparing_file": {
        "es": "⏳ Preparando archivo…",
        "en": "⏳ Preparing file…",
        "fr": "⏳ Préparation du fichier…",
    },
    "index_opening": {
        "es": "⏳ Abriendo índice…",
        "en": "⏳ Opening index…",
        "fr": "⏳ Ouverture de l'index…",
    },
    "index_creating": {
        "es": "⏳ Creando índice…",
        "en": "⏳ Creating index…",
        "fr": "⏳ Création de l'index…",
    },
    "highlights_opening": {
        "es": "⏳ Abriendo highlights…",
        "en": "⏳ Opening highlights…",
        "fr": "⏳ Ouverture des temps forts…",
    },
    "highlights_creating": {
        "es": "⏳ Seleccionando lo más importante…",
        "en": "⏳ Picking key moments…",
        "fr": "⏳ Sélection des moments clés…",
    },
    "need_transcript_first": {
        "es": "Primero transcribe algo; luego usa los botones del resultado.",
        "en": "Transcribe something first; then use the result buttons.",
        "fr": "Transcrivez d'abord ; puis utilisez les boutons du résultat.",
    },
    "summary_need_transcript": {
        "es": (
            "📝 *Resumir* va *después* de la transcripción.\n\n"
            "Primero envía audio, vídeo o enlace y espera el texto completo. "
            "Luego pulsa *Resumir*."
        ),
        "en": (
            "📝 *Summarize* comes *after* the transcript.\n\n"
            "Send audio, video or a link first and wait for the full text. "
            "Then tap *Summarize*."
        ),
        "fr": (
            "📝 *Résumer* vient *après* la transcription.\n\n"
            "Envoyez d'abord audio, vidéo ou un lien et attendez le texte complet. "
            "Puis touchez *Résumer*."
        ),
    },
    "export_need_transcript": {
        "es": "Primero transcribe algo; luego elige exportación.",
        "en": "Transcribe something first; then choose export.",
        "fr": "Transcrivez d'abord ; puis choisissez l'export.",
    },
    "error_audio": {
        "es": "❌ Error con el audio: {detail}",
        "en": "❌ Audio error: {detail}",
        "fr": "❌ Erreur audio : {detail}",
    },
    "error_video": {
        "es": "❌ Error con el vídeo: {detail}",
        "en": "❌ Video error: {detail}",
        "fr": "❌ Erreur vidéo : {detail}",
    },
    "summary_done": {
        "es": "Resumen listo. Usa las páginas o «Atrás» para más acciones.",
        "en": "Summary ready. Use pages or «Back» for more actions.",
        "fr": "Résumé prêt. Utilisez les pages ou « Retour » pour plus d'actions.",
        "ru": "Краткое содержание готово. Страницы или «Назад» для других действий.",
    },
    "metainfo_source": {
        "es": "Fuente",
        "en": "Source",
        "fr": "Source",
        "ru": "Источник",
    },
}


from bot.i18n_progress import PROGRESS_STRINGS

STRINGS.update(PROGRESS_STRINGS)


for _key, _ru in RU.items():
    if _key in STRINGS:
        STRINGS[_key]["ru"] = _ru


def normalize_lang(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANG
    code = lang.strip().lower()[:2]
    return code if code in SUPPORTED else DEFAULT_LANG


def lang_from_telegram(language_code: str | None) -> str:
    """Mapea language_code de Telegram (ISO 639-1) a un idioma soportado."""
    if not language_code:
        return DEFAULT_LANG
    base = language_code.lower().replace("_", "-").split("-")[0]
    if base in SUPPORTED:
        return base
    if base in ("ca", "gl", "eu"):
        return "es"
    if base in ("uk", "be", "kk", "hy"):
        return "ru"
    if base in ("pt", "it", "de", "nl", "pl", "sv", "da", "nb", "fi"):
        return "en"
    if base in ("ar", "he", "tr"):
        return "en"
    return DEFAULT_LANG


def get_lang(context: ContextTypes.DEFAULT_TYPE | None) -> str:
    if context is None:
        return DEFAULT_LANG
    return normalize_lang(context.user_data.get("ui_lang"))


def ensure_user_lang(update, context: ContextTypes.DEFAULT_TYPE | None) -> str:
    """
    Por defecto siempre español (app personal).
    Solo se mantiene otro idioma si el usuario lo eligió con /idioma.
    """
    if context is None:
        return DEFAULT_LANG
    if context.user_data.get("ui_lang_manual"):
        return get_lang(context)
    from bot.services.transcript_lang import set_ui_lang

    set_ui_lang(context, DEFAULT_LANG)
    context.user_data["lang_initialized"] = True
    return DEFAULT_LANG


def set_lang(context: ContextTypes.DEFAULT_TYPE, lang: str) -> str:
    from bot.services.transcript_lang import set_ui_lang

    context.user_data["lang_initialized"] = True
    context.user_data["ui_lang_manual"] = True
    return set_ui_lang(context, lang)


def lang_from_menu_text(text: str) -> str | None:
    t = (text or "").strip()
    for code, label in LANG_MENU.items():
        if t == label:
            return code
    return None


def t(key: str, lang: str | None = None, **kwargs) -> str:
    code = normalize_lang(lang)
    bucket = STRINGS.get(key, {})
    msg = bucket.get(code) or bucket.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            return msg.format(**kwargs)
        except (KeyError, ValueError):
            return msg
    return msg


def menu_home(lang: str | None = None) -> str:
    return t("menu_home", lang)


def menu_help(lang: str | None = None) -> str:
    return t("menu_help", lang)


def active_lang_label(code: str | None) -> str:
    """Etiqueta visible del idioma activo (bandera + nombre)."""
    from bot.services.transcript_lang import AUTO_LANG, detected_language_label

    if not code:
        return LANG_MENU.get(DEFAULT_LANG, DEFAULT_LANG.upper())
    if code == AUTO_LANG or code == "auto":
        return LANG_MENU.get(AUTO_LANG, "🌐 Detección")
    c = normalize_lang(code)
    if c in LANG_MENU:
        return LANG_MENU[c]
    return detected_language_label(code)


def welcome_language_kwargs(
    context: ContextTypes.DEFAULT_TYPE, ui_lang: str
) -> dict[str, str]:
    """Etiquetas de idioma para /start: menú, transcripción y traducción activa."""
    from bot.services.transcript_active import (
        VARIANT_ORIGINAL,
        get_content_lang,
        get_source_lang,
        get_variant,
        list_translation_langs,
    )
    from bot.services.transcript_lang import get_transcript_lang

    code = normalize_lang(ui_lang)
    transcript_label = active_lang_label(get_transcript_lang(context))

    if not context.user_data.get("last_segments"):
        translate_status = t(
            "start_translate_pending", code, transcript=transcript_label
        )
    else:
        variant = get_variant(context)
        source_label = active_lang_label(get_source_lang(context))
        if variant != VARIANT_ORIGINAL:
            work_label = active_lang_label(get_content_lang(context))
            translate_status = t(
                "start_translate_active",
                code,
                label=work_label,
                source=source_label,
            )
        elif list_translation_langs(context):
            saved = ", ".join(
                active_lang_label(c) for c in list_translation_langs(context)
            )
            translate_status = t(
                "start_translate_original_saved",
                code,
                source=source_label,
                saved=saved,
            )
        else:
            translate_status = t(
                "start_translate_original", code, source=source_label
            )

    return {
        "lang_label": active_lang_label(code),
        "transcript_lang_label": transcript_label,
        "translate_status": translate_status,
    }


_START_TRANSLATE_SLOT = "§TRANSLATE§"


def build_start_message(context: ContextTypes.DEFAULT_TYPE, ui_lang: str) -> str:
    """Mensaje /start con idiomas sustituidos (sin doble .format que rompe las llaves)."""
    k = welcome_language_kwargs(context, ui_lang)
    msg = t(
        "start_text",
        ui_lang,
        lang_label=k["lang_label"],
        transcript_lang_label=k["transcript_lang_label"],
    )
    if _START_TRANSLATE_SLOT in msg:
        return msg.replace(_START_TRANSLATE_SLOT, k["translate_status"])
    return msg
