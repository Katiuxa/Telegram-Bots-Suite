"""Textos públicos del bot (perfil Telegram antes de /start)."""

# Descripción larga (~512 caracteres) por idioma de la app Telegram del usuario
BOT_PROFILE_BY_LANG = {
    "es": (
        "MetavideoToText convierte audio, vídeo, notas de voz y enlaces "
        "(TikTok, Reels, X, YouTube) en texto claro.\n\n"
        "Idioma de menú y transcripción: español, inglés, francés, ruso "
        "o *detección automática* (ideal para Reels/TikTok en hindi, urdu, etc.).\n\n"
        "Envía un archivo o enlace directamente. Después: resumen, .txt, PDF, "
        "leer en Telegram, índice y highlights.\n\n"
        "Pulsa Iniciar o /start."
    ),
    "en": (
        "MetavideoToText turns audio, video, voice notes and links "
        "(TikTok, Reels, X, YouTube) into clear text.\n\n"
        "Menu and transcripts in Spanish, English, French or Russian "
        "(from your Telegram language or keyboard buttons).\n\n"
        "Send a file or link directly. Then: summary, .txt, PDF, "
        "read in Telegram, index and highlights.\n\n"
        "Tap Start or /start."
    ),
    "fr": (
        "MetavideoToText transforme audio, vidéo, notes vocales et liens "
        "(TikTok, Reels, X, YouTube) en texte clair.\n\n"
        "Menu et transcriptions en espagnol, anglais, français ou russe "
        "(selon Telegram ou les boutons du clavier).\n\n"
        "Envoyez un fichier ou un lien. Ensuite : résumé, .txt, PDF, "
        "lire dans Telegram, index et temps forts.\n\n"
        "Appuyez sur Démarrer ou /start."
    ),
    "ru": (
        "MetavideoToText превращает аудио, видео, голосовые и ссылки "
        "(TikTok, Reels, X, YouTube) в понятный текст.\n\n"
        "Меню и транскрипция: испанский, английский, французский или русский "
        "(язык Telegram или кнопки клавиатуры).\n\n"
        "Отправьте файл или ссылку. Затем: краткое содержание, .txt, PDF, "
        "чтение в Telegram, оглавление и главное.\n\n"
        "Нажмите «Запустить» или /start."
    ),
}

BOT_PROFILE_SHORT_BY_LANG = {
    "es": "Audio, vídeo y enlaces → texto en ES/EN/FR/RU. Envía directo.",
    "en": "Audio, video & links → text in ES/EN/FR/RU. Just send.",
    "fr": "Audio, vidéo et liens → texte ES/EN/FR/RU. Envoyez direct.",
    "ru": "Аудио, видео и ссылки → текст ES/EN/FR/RU. Отправьте сразу.",
}

# Compatibilidad con imports antiguos
BOT_PROFILE_DESCRIPTION = BOT_PROFILE_BY_LANG["es"]
BOT_PROFILE_SHORT_DESCRIPTION = BOT_PROFILE_SHORT_BY_LANG["es"]
