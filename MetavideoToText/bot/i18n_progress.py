"""Textos de progreso, errores de proceso y estados (ES / EN / FR / RU)."""

from __future__ import annotations

DEFAULT_LANG = "es"
_SUPPORTED = frozenset({"es", "en", "fr", "ru"})


def normalize_lang(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANG
    code = lang.strip().lower()[:2]
    return code if code in _SUPPORTED else DEFAULT_LANG


def _4(es: str, en: str, fr: str, ru: str) -> dict[str, str]:
    return {"es": es, "en": en, "fr": fr, "ru": ru}


PROGRESS_STRINGS: dict[str, dict[str, str]] = {
    "prog_starting": _4("Empezando", "Starting", "Démarrage", "Запуск"),
    "prog_checking_link": _4(
        "Comprobando enlace",
        "Checking link",
        "Vérification du lien",
        "Проверка ссылки",
    ),
    "prog_downloading_audio_only": _4(
        "Descargando solo audio (más rápido)",
        "Downloading audio only (faster)",
        "Téléchargement audio seul (plus rapide)",
        "Скачивание только аудио",
    ),
    "prog_converting_audio": _4(
        "Convirtiendo audio",
        "Converting audio",
        "Conversion audio",
        "Конвертация аудио",
    ),
    "prog_converting_audio_sub": _4(
        "Casi listo para transcribir",
        "Almost ready to transcribe",
        "Presque prêt à transcrire",
        "Скоро транскрипция",
    ),
    "prog_large_file_hint": _4(
        "Puede tardar en la Raspberry; no cierres el chat.",
        "May take a while on the Raspberry; keep the chat open.",
        "Peut prendre du temps sur la Raspberry.",
        "На Raspberry может занять время.",
    ),
    "prog_youtube_download_too_large": _4(
        "El audio supera ~{mb} MB (máx. {max_mb} MB). "
        "Prueba un vídeo más corto o exporta cookies.txt si YouTube no ofrece solo audio.",
        "File exceeds ~{mb} MB (max {max_mb} MB on the Pi). "
        "Try a shorter video or add cookies.txt.",
        "Fichier > ~{mb} Mo (max {max_mb} Mo). Vidéo plus courte ou cookies.txt.",
        "Файл > ~{mb} МБ (макс. {max_mb} МБ). Короче или cookies.txt.",
    ),
    "prog_file_too_big_audio_parts": _4(
        "📦 *Archivo grande:* pega el *enlace* de YouTube (TikTok/Reels) "
        "y elige *Solo audio* — un MP3 completo.",
        "📦 *Large file:* paste the YouTube (TikTok/Reels) *link* "
        "and choose *Audio only* — one complete MP3.",
        "📦 *Fichier lourd :* collez le *lien* YouTube et *Audio seulement* "
        "— un MP3 complet.",
        "📦 *Большой файл:* вставьте *ссылку* YouTube и *Только аудио* "
        "— один полный MP3.",
    ),
    "prog_extracting_audio": _4(
        "Extrayendo el audio",
        "Extracting audio",
        "Extraction de l'audio",
        "Извлечение аудио",
    ),
    "prog_youtube_captions": _4(
        "Leyendo subtítulos de YouTube",
        "Reading YouTube captions",
        "Lecture des sous-titres YouTube",
        "Чтение субтитров YouTube",
    ),
    "prog_whisper_fallback": _4(
        "Sin subtítulos — transcribiendo el audio (vídeos largos: varios minutos)",
        "No captions — transcribing audio (long videos take several minutes)",
        "Pas de sous-titres — transcription audio (les longues vidéos prennent du temps)",
        "Нет субтитров — транскрипция аудио (длинные видео занимают время)",
    ),
    "prog_polishing_text": _4(
        "Puliendo el texto",
        "Polishing text",
        "Finalisation du texte",
        "Обработка текста",
    ),
    "prog_transcribing": _4(
        "Transcribiendo",
        "Transcribing",
        "Transcription",
        "Транскрипция",
    ),
    "prog_transcribing_almost": _4(
        "Casi listo",
        "Almost done",
        "Presque fini",
        "Почти готово",
    ),
    "prog_part_n_of_m": _4(
        "Parte {cur} de {total}",
        "Part {cur} of {total}",
        "Partie {cur} sur {total}",
        "Часть {cur} из {total}",
    ),
    "prog_part_short": _4(
        "P.{cur}/{total}",
        "P.{cur}/{total}",
        "P.{cur}/{total}",
        "Ч.{cur}/{total}",
    ),
    "prog_downloading": _4(
        "Descargando",
        "Downloading",
        "Téléchargement",
        "Загрузка",
    ),
    "prog_download_sub_of": _4(
        "{done} de {total}{speed}",
        "{done} of {total}{speed}",
        "{done} sur {total}{speed}",
        "{done} из {total}{speed}",
    ),
    "prog_download_sub_partial": _4(
        "{done} descargados{speed}",
        "{done} downloaded{speed}",
        "{done} téléchargés{speed}",
        "Загружено {done}{speed}",
    ),
    "prog_download_sub_eta": _4(
        " · ~{eta} s restantes",
        " · ~{eta} s left",
        " · ~{eta} s restantes",
        " · ~{eta} с осталось",
    ),
    "prog_preparing_audio": _4(
        "Preparando el audio",
        "Preparing audio",
        "Préparation de l'audio",
        "Подготовка аудио",
    ),
    "prog_download_ready": _4(
        "Descarga lista",
        "Download complete",
        "Téléchargement terminé",
        "Загрузка завершена",
    ),
    "prog_download_cancelled": _4(
        "Descarga cancelada.",
        "Download cancelled.",
        "Téléchargement annulé.",
        "Загрузка отменена.",
    ),
    "prog_download_no_response": _4(
        "La descarga terminó sin respuesta.",
        "Download finished with no response.",
        "Téléchargement terminé sans réponse.",
        "Загрузка завершилась без ответа.",
    ),
    "prog_download_unknown_error": _4(
        "Error desconocido",
        "Unknown error",
        "Erreur inconnue",
        "Неизвестная ошибка",
    ),
    "prog_received": _4("Recibido", "Received", "Reçu", "Получено"),
    "prog_sending_text": _4(
        "Enviando el texto",
        "Sending text",
        "Envoi du texte",
        "Отправка текста",
    ),
    "prog_message_n_of_m": _4(
        "Mensaje {cur} de {total}",
        "Message {cur} of {total}",
        "Message {cur} sur {total}",
        "Сообщение {cur} из {total}",
    ),
    "prog_fetching_video": _4(
        "Obteniendo el vídeo",
        "Fetching video",
        "Récupération de la vidéo",
        "Получение видео",
    ),
    "prog_fetch_wait_1": _4(
        "Conectando con la plataforma…",
        "Connecting to the platform…",
        "Connexion à la plateforme…",
        "Подключение к платформе…",
    ),
    "prog_fetch_wait_2": _4(
        "Sigue en curso (TikTok/Reels pueden tardar 1–2 min)",
        "Still working (TikTok/Reels may take 1–2 min)",
        "Toujours en cours (TikTok/Reels : 1–2 min)",
        "Ещё идёт (TikTok/Reels: 1–2 мин)",
    ),
    "prog_fetch_wait_3": _4(
        "YouTube: solo audio, sin vídeo completo",
        "YouTube: audio only, not full video",
        "YouTube : audio seulement",
        "YouTube: только аудио",
    ),
    "prog_link_starting": _4(
        "Iniciando descarga…",
        "Starting download…",
        "Démarrage du téléchargement…",
        "Запуск загрузки…",
    ),
    "prog_download_timeout": _4(
        "La descarga tardó demasiado ({sec} s). Prueba otro enlace o más tarde.",
        "Download timed out ({sec} s). Try another link or later.",
        "Téléchargement trop long ({sec} s). Autre lien ou plus tard.",
        "Превышено время загрузки ({sec} с).",
    ),
    "prog_download_cli_failed": _4(
        "No pude descargar el enlace (código {code}). Actualiza la Pi: PI.cmd actualizar",
        "Could not download link (code {code}). Update the Pi.",
        "Échec du téléchargement ({code}). Mettez à jour la Pi.",
        "Ошибка загрузки ({code}).",
    ),
    "prog_ytdlp_ejs_missing": _4(
        "Falta soporte de YouTube en el servidor. Ejecuta en la Pi: pip install -U \"yt-dlp[default]\" y reinicia el bot.",
        "YouTube support missing on server. Run: pip install -U \"yt-dlp[default]\"",
        "Support YouTube manquant. pip install -U \"yt-dlp[default]\"",
        "Нет поддержки YouTube. pip install -U \"yt-dlp[default]\"",
    ),
    "prog_youtube_try": _4(
        "YouTube: intento {n}/{total}",
        "YouTube: attempt {n}/{total}",
        "YouTube : essai {n}/{total}",
        "YouTube: попытка {n}/{total}",
    ),
    "prog_reading_transcript": _4(
        "Leyendo tu transcripción",
        "Reading your transcript",
        "Lecture de la transcription",
        "Чтение транскрипции",
    ),
    "prog_creating_summary": _4(
        "Creando el resumen",
        "Creating summary",
        "Création du résumé",
        "Создание краткого содержания",
    ),
    "prog_sending_summary": _4(
        "Enviando el resumen",
        "Sending summary",
        "Envoi du résumé",
        "Отправка краткого содержания",
    ),
    "prog_translating": _4(
        "Traduciendo",
        "Translating",
        "Traduction",
        "Перевод",
    ),
    "prog_formatting": _4(
        "Formateando",
        "Formatting",
        "Mise en forme",
        "Форматирование",
    ),
    "prog_translate_waiting_quota": _4(
        "Traduciendo",
        "Translating",
        "Traduction",
        "Перевод",
    ),
    "prog_translate_mt_fallback": _4(
        "Traduciendo",
        "Translating",
        "Traduction",
        "Перевод",
    ),
    "prog_translate_mt_fail": _4(
        "No pude completar la traducción. Reintenta en un momento.",
        "Could not finish the translation. Try again in a moment.",
        "Impossible de terminer la traduction. Réessayez dans un instant.",
        "Не удалось завершить перевод. Повторите чуть позже.",
    ),
    "prog_translate_rate_limit": _4(
        "No pude traducir ahora mismo. Reintenta en un momento.",
        "Could not translate right now. Try again in a moment.",
        "Traduction indisponible pour le moment. Réessayez bientôt.",
        "Сейчас перевести не удалось. Повторите чуть позже.",
    ),
    "prog_translate_parse_fail": _4(
        "No se pudo interpretar la traducción. Reintenta.",
        "Could not parse translation. Try again.",
        "Traduction illisible. Réessayez.",
        "Не удалось разобрать перевод. Повторите.",
    ),
    "prog_translate_api_fail": _4(
        "No pude conectar con el servicio de traducción. Reintenta en unos segundos.",
        "Translation service unavailable. Try again in a few seconds.",
        "Service de traduction indisponible. Réessayez dans quelques secondes.",
        "Сервис перевода недоступен. Повторите через несколько секунд.",
    ),
    "prog_translate_auth_fail": _4(
        "Clave Groq inválida o sin permiso para traducir. Revisa GROQ_API_KEY.",
        "Invalid Groq key or no permission to translate. Check GROQ_API_KEY.",
        "Clé Groq invalide ou sans permission. Vérifiez GROQ_API_KEY.",
        "Неверный ключ Groq или нет доступа. Проверьте GROQ_API_KEY.",
    ),
    "prog_translate_no_key": _4(
        "Falta GROQ_API_KEY en .env para traducir.",
        "GROQ_API_KEY is missing in .env for translation.",
        "GROQ_API_KEY manquant dans .env pour traduire.",
        "В .env нет GROQ_API_KEY для перевода.",
    ),
    "prog_opening_index": _4(
        "Abriendo índice",
        "Opening index",
        "Ouverture de l'index",
        "Открытие оглавления",
    ),
    "prog_organizing_chapters": _4(
        "Organizando capítulos",
        "Organizing chapters",
        "Organisation des chapitres",
        "Организация глав",
    ),
    "prog_index_almost": _4(
        "Índice casi listo",
        "Index almost ready",
        "Index presque prêt",
        "Оглавление почти готово",
    ),
    "prog_building_index": _4(
        "Montando el índice",
        "Building index",
        "Montage de l'index",
        "Сборка оглавления",
    ),
    "prog_index_done": _4(
        "Índice ({total} capítulos). Toca un título.",
        "Index ({total} chapters). Tap a title.",
        "Index ({total} chapitres). Touchez un titre.",
        "Оглавление ({total} глав). Нажмите на заголовок.",
    ),
    "prog_opening_highlights": _4(
        "Abriendo highlights",
        "Opening highlights",
        "Ouverture des temps forts",
        "Открытие главного",
    ),
    "prog_finding_highlights": _4(
        "Buscando lo más importante",
        "Finding key moments",
        "Recherche des moments clés",
        "Поиск главного",
    ),
    "prog_building_highlights": _4(
        "Montando highlights",
        "Building highlights",
        "Montage des temps forts",
        "Сборка главного",
    ),
    "prog_highlights_done": _4(
        "Highlights ({total}). Toca un título.",
        "Highlights ({total}). Tap a title.",
        "Temps forts ({total}). Touchez un titre.",
        "Главное ({total}). Нажмите на заголовок.",
    ),
    "prog_preparing_file_step": _4(
        "Preparando archivo",
        "Preparing file",
        "Préparation du fichier",
        "Подготовка файла",
    ),
    "prog_creating_txt": _4(
        "Creando TXT",
        "Creating TXT",
        "Création du TXT",
        "Создание TXT",
    ),
    "prog_creating_pdf": _4(
        "Creando PDF",
        "Creating PDF",
        "Création du PDF",
        "Создание PDF",
    ),
    "prog_creating_mp3": _4(
        "Convirtiendo a MP3",
        "Converting to MP3",
        "Conversion en MP3",
        "Конвертация в MP3",
    ),
    "prog_sending_file": _4(
        "Enviando archivo",
        "Sending file",
        "Envoi du fichier",
        "Отправка файла",
    ),
    "prog_uploading_external": _4(
        "Subiendo a servidor externo…",
        "Uploading to external host…",
        "Envoi vers serveur externe…",
        "Загрузка на внешний сервер…",
    ),
    "prog_file_ready": _4(
        "¡{label} listo!",
        "{label} ready!",
        "{label} prêt !",
        "{label} готов!",
    ),
    "prog_file_create_fail": _4(
        "No pude crear {label}",
        "Could not create {label}",
        "Impossible de créer {label}",
        "Не удалось создать {label}",
    ),
    "prog_done": _4("Listo.", "Done.", "Terminé.", "Готово."),
    "prog_send_result_fail": _4(
        "Error al enviar el resultado",
        "Error sending result",
        "Erreur lors de l'envoi",
        "Ошибка отправки результата",
    ),
    "prog_send_error_detail": _4(
        "❌ Error al enviar: {detail}",
        "❌ Error sending: {detail}",
        "❌ Erreur d'envoi : {detail}",
        "❌ Ошибка отправки: {detail}",
    ),
    "prog_cancelled_body": _4(
        "Cancelado. Envía otro archivo o abre *Menú principal*.",
        "Cancelled. Send another file or open *Main menu*.",
        "Annulé. Envoyez un autre fichier ou ouvrez le *Menu principal*.",
        "Отменено. Отправьте другой файл или откройте *Главное меню*.",
    ),
    "prog_nothing_running": _4(
        "No hay nada en curso",
        "Nothing in progress",
        "Rien en cours",
        "Ничего не выполняется",
    ),
    "prog_cancelling": _4(
        "Cancelando…",
        "Cancelling…",
        "Annulation…",
        "Отмена…",
    ),
    "prog_no_task": _4(
        "No hay ninguna tarea en curso.",
        "No task in progress.",
        "Aucune tâche en cours.",
        "Нет активных задач.",
    ),
    "prog_state_cleared": _4(
        "Estado liberado. Ya puedes enviar otro vídeo o enlace.",
        "State cleared. You can send another video or link.",
        "État réinitialisé. Vous pouvez renvoyer une vidéo ou un lien.",
        "Состояние сброшено. Можно отправить снова.",
    ),
    "prog_fail_transcription": _4(
        "No pude completar la transcripción",
        "Could not complete transcription",
        "Transcription impossible",
        "Не удалось завершить транскрипцию",
    ),
    "prog_fail_transcription_empty": _4(
        "La transcripción salió vacía",
        "Transcription was empty",
        "Transcription vide",
        "Пустая транскрипция",
    ),
    "prog_fail_transcription_empty_hint": _4(
        "Prueba de nuevo o con otro enlace; el audio no dio texto usable.",
        "Try again or another link; the audio gave no usable text.",
        "Réessayez ou un autre lien ; l'audio n'a pas donné de texte utilisable.",
        "Попробуйте снова или другую ссылку; из аудио не вышел пригодный текст.",
    ),
    "prog_fail_process": _4(
        "Algo falló en el proceso",
        "Something went wrong",
        "Une erreur s'est produite",
        "Что-то пошло не так",
    ),
    "prog_fail_process_hint": _4(
        "Si es enlace, que sea público. Archivo: máx. 20 MB.",
        "For links, use a public URL. Files: max 20 MB.",
        "Lien public requis. Fichiers : max 20 Mo.",
        "Для ссылок — публичный URL. Файлы: макс. 20 МБ.",
    ),
    "prog_fail_summarize": _4(
        "No pude resumir",
        "Could not summarize",
        "Résumé impossible",
        "Не удалось сделать краткое содержание",
    ),
    "prog_fail_index": _4(
        "No pude crear el índice",
        "Could not create index",
        "Index impossible",
        "Не удалось создать оглавление",
    ),
    "prog_fail_highlights": _4(
        "No pude crear los highlights",
        "Could not create highlights",
        "Temps forts impossibles",
        "Не удалось создать главное",
    ),
    "prog_video_too_long": _4(
        "⏱ Más de {minutes} minutos. Envía uno más corto.",
        "⏱ Over {minutes} minutes. Send a shorter one.",
        "⏱ Plus de {minutes} minutes. Envoyez plus court.",
        "⏱ Больше {minutes} мин. Отправьте короче.",
    ),
    "prog_link_fail": _4(
        "❌ No pude procesar el enlace.\n\n{detail}",
        "❌ Could not process the link.\n\n{detail}",
        "❌ Impossible de traiter le lien.\n\n{detail}",
        "❌ Не удалось обработать ссылку.\n\n{detail}",
    ),
    "prog_link_hint": _4(
        "🔗 Pega un enlace de TikTok, Reels, X o YouTube.\n"
        "Puedes incluir texto antes o después del enlace.",
        "🔗 Paste a TikTok, Reels, X or YouTube link.\n"
        "You can add text before or after the link.",
        "🔗 Collez un lien TikTok, Reels, X ou YouTube.\n"
        "Du texte avant ou après le lien est accepté.",
        "🔗 Вставьте ссылку TikTok, Reels, X или YouTube.\n"
        "Можно добавить текст до или после ссылки.",
    ),
    "prog_file_too_big_mb": _4(
        "📦 Archivo de ~{mb:.1f} MB.",
        "📦 File ~{mb:.1f} MB.",
        "📦 Fichier ~{mb:.1f} Mo.",
        "📦 Файл ~{mb:.1f} МБ.",
    ),
    "prog_file_too_big_help": _4(
        "Telegram solo permite que los bots descarguen archivos de hasta "
        "*{max_mb} MB* (tu archivo supera ese límite).\n\n"
        "💡 *Qué puedes hacer:*\n"
        "• Comprime el vídeo (menos de {max_mb} MB)\n"
        "• Envía una *nota de voz* o archivo de *audio*\n"
        "• Si el vídeo está en TikTok, Reels, X o YouTube, pega el *enlace* 🔗 "
        "(vídeos largos: un solo MP3 con toda la duración)",
        "Telegram only lets bots download files up to "
        "*{max_mb} MB* (yours exceeds that).\n\n"
        "💡 *You can:*\n"
        "• Compress the video (under {max_mb} MB)\n"
        "• Send a *voice note* or *audio* file\n"
        "• For TikTok, Reels, X or YouTube, paste the *link* 🔗 "
        "(long videos: one MP3 with full duration)",
        "Telegram limite les bots à "
        "*{max_mb} Mo* (fichier trop grand).\n\n"
        "💡 *Options :*\n"
        "• Compressez la vidéo (< {max_mb} Mo)\n"
        "• Envoyez une *note vocale* ou un *audio*\n"
        "• TikTok/Reels : collez le *lien* 🔗",
        "Telegram позволяет ботам скачивать до "
        "*{max_mb} МБ* (ваш файл больше).\n\n"
        "💡 *Можно:*\n"
        "• Сжать видео (< {max_mb} МБ)\n"
        "• Отправить *голосовое* или *аудио*\n"
        "• TikTok/Reels — вставить *ссылку* 🔗",
    ),
    "prog_file_too_big_tg": _4(
        "📦 Telegram no deja descargar este archivo (> {max_mb} MB).\n\n",
        "📦 Telegram cannot download this file (> {max_mb} MB).\n\n",
        "📦 Telegram ne peut pas télécharger ce fichier (> {max_mb} Mo).\n\n",
        "📦 Telegram не может скачать этот файл (> {max_mb} МБ).\n\n",
    ),
    "prog_video_too_big_short": _4(
        "📦 Archivo demasiado grande para Telegram.\n{detail}",
        "📦 File too large for Telegram.\n{detail}",
        "📦 Fichier trop volumineux pour Telegram.\n{detail}",
        "📦 Файл слишком большой для Telegram.\n{detail}",
    ),
    "prog_no_timestamps": _4(
        "No hay tiempos guardados. Transcribe de nuevo el vídeo.",
        "No timestamps saved. Transcribe the video again.",
        "Pas d'horodatage. Retranscrivez la vidéo.",
        "Нет меток времени. Транскрибируйте снова.",
    ),
    "prog_no_highlights_gen": _4(
        "No pude generar highlights.",
        "Could not generate highlights.",
        "Impossible de générer les temps forts.",
        "Не удалось создать главное.",
    ),
    "prog_no_highlights_extract": _4(
        "No pude extraer highlights. Transcribe de nuevo el vídeo.",
        "Could not extract highlights. Transcribe again.",
        "Extraction impossible. Retranscrivez.",
        "Не удалось извлечь главное. Транскрибируйте снова.",
    ),
    "prog_chapter_list": _4(
        "Lista de capítulos",
        "Chapter list",
        "Liste des chapitres",
        "Список глав",
    ),
    "prog_highlights_list": _4(
        "Lista de highlights",
        "Highlights list",
        "Liste des temps forts",
        "Список моментов",
    ),
    "prog_export_label_index": _4(
        "Índice inteligente",
        "Smart index",
        "Index intelligent",
        "Умное оглавление",
    ),
    "prog_export_label_highlights": _4(
        "Highlights",
        "Highlights",
        "Temps forts",
        "Главное",
    ),
    "prog_transcription_unavailable": _4(
        "Transcripción en tu PC no disponible. Ejecuta LANZAR_BOT.cmd.",
        "Local transcription unavailable. Run LANZAR_BOT.cmd.",
        "Transcription locale indisponible. Lancez LANZAR_BOT.cmd.",
        "Локальная транскрипция недоступна. Запустите LANZAR_BOT.cmd.",
    ),
    "prog_transcription_service_unavailable": _4(
        "Servicio de transcripción no disponible",
        "Transcription service unavailable",
        "Service de transcription indisponible",
        "Сервис транскрипции недоступен",
    ),
    "prog_transcription_failed_audio": _4(
        "No pude transcribir el audio. Prueba otro archivo o uno más corto.",
        "Could not transcribe audio. Try another or shorter file.",
        "Transcription audio impossible. Autre fichier ou plus court.",
        "Не удалось транскрибировать. Другой или более короткий файл.",
    ),
    "prog_transcription_empty_local": _4(
        "Transcripción local vacía",
        "Local transcription empty",
        "Transcription locale vide",
        "Пустая локальная транскрипция",
    ),
    "prog_transcription_empty": _4(
        "Transcripción vacía.",
        "Empty transcription.",
        "Transcription vide.",
        "Пустая транскрипция.",
    ),
    "prog_no_text_summarize": _4(
        "No hay texto para resumir.",
        "No text to summarize.",
        "Pas de texte à résumer.",
        "Нет текста для краткого содержания.",
    ),
}


def prog(key: str, lang: str | None = None, **kwargs) -> str:
    """Texto de progreso/error; key sin prefijo prog_ (se añade solo)."""
    code = normalize_lang(lang)
    full_key = key if key.startswith("prog_") else f"prog_{key}"
    bucket = PROGRESS_STRINGS.get(full_key, {})
    msg = bucket.get(code) or bucket.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            return msg.format(**kwargs)
        except (KeyError, ValueError):
            return msg
    return msg


def is_downloading_label(label: str) -> bool:
    low = (label or "").lower()
    return any(
        w in low
        for w in (
            "descarg",
            "download",
            "télécharg",
            "загруз",
            "obteniendo",
            "fetching",
            "récupération",
            "получение",
            "audio only",
            "solo audio",
        )
    )


def is_live_transcribe_label(label: str) -> bool:
    low = (label or "").lower()
    return any(
        w in low
        for w in (
            "transcrib",
            "transcri",
            "транскрип",
        )
    )


def is_transcribing_compact(label: str, sub: str) -> bool:
    """Transcripción: solo barra y % (sin trozos ni vista previa de texto)."""
    if (sub or "").strip():
        return False
    low = (label or "").lower()
    return any(
        w in low
        for w in (
            "transcrib",
            "transcri",
            "транскрип",
            "casi listo",
            "almost done",
            "presque fini",
            "почти готово",
        )
    )
