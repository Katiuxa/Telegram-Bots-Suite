import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove

from bot.i18n import LANG_MENU, get_lang, t
from bot.services.highlights_view import (
    HIGHLIGHTS_TOC_PAGE_SIZE,
    highlight_button_label,
)
from bot.services.moments_view import INDEX_TOC_PAGE_SIZE, chapter_button_label
from bot.services.transcript_active import (
    VARIANT_ORIGINAL,
    list_translation_langs,
    variant_button_label,
)


def _variant_switch_rows(context, lang: str) -> list[list[InlineKeyboardButton]]:
    """Fila(s) para alternar original ↔ traducciones guardadas."""
    translated = list_translation_langs(context)
    if not translated:
        return []
    buttons: list[InlineKeyboardButton] = [
        InlineKeyboardButton(
            variant_button_label(context, VARIANT_ORIGINAL, lang),
            callback_data="action:variant:original",
        )
    ]
    for code in translated:
        buttons.append(
            InlineKeyboardButton(
                variant_button_label(context, code, lang),
                callback_data=f"action:variant:{code}",
            )
        )
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(buttons), 2):
        rows.append(buttons[i : i + 2])
    return rows


def _translate_action_row(lang: str) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(t("btn_translate", lang), callback_data="action:translate_menu")]


def _after_transcript_action_rows(code: str) -> list[list[InlineKeyboardButton]]:
    """Acciones post-transcripción: Traducir, TXT, PDF, Buscar, Enviar otro."""
    return [
        _translate_action_row(code),
        [
            InlineKeyboardButton(t("btn_txt", code), callback_data="fmt_get:txt"),
            InlineKeyboardButton(t("btn_pdf", code), callback_data="fmt_get:pdf"),
        ],
        [
            InlineKeyboardButton(t("btn_search", code), callback_data="action:search"),
        ],
        [
            InlineKeyboardButton(t("btn_send_another", code), callback_data="home"),
        ],
    ]


def after_transcript_keyboard(lang: str | None = None, context=None) -> InlineKeyboardMarkup:
    code = lang or "es"
    rows: list[list[InlineKeyboardButton]] = []
    if context is not None:
        rows.extend(_variant_switch_rows(context, code))
    rows.extend(_after_transcript_action_rows(code))
    return InlineKeyboardMarkup(rows)


def translate_target_keyboard(context, lang: str | None = None) -> InlineKeyboardMarkup:
    from bot.services.transcript_active import get_source_lang, has_translation, translation_targets

    code = lang or "es"
    targets = translation_targets(context)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for tgt in targets:
        label = LANG_MENU.get(tgt, tgt.upper())
        if has_translation(context, tgt):
            label = f"{label} ✓"
        row.append(
            InlineKeyboardButton(label, callback_data=f"action:translate_to:{tgt}")
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(t("btn_back", code), callback_data="fmt_back")])
    return InlineKeyboardMarkup(rows)


def reply_keyboard(lang: str | None = None) -> ReplyKeyboardRemove:
    """Sin teclado inferior: solo menú inline / mensajes."""
    return ReplyKeyboardRemove()


def ui_lang_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    """Selector de idioma de la app (/idioma). Sin Auto."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(LANG_MENU["es"], callback_data="ui_lang:es"),
                InlineKeyboardButton(LANG_MENU["en"], callback_data="ui_lang:en"),
            ],
            [
                InlineKeyboardButton(LANG_MENU["fr"], callback_data="ui_lang:fr"),
                InlineKeyboardButton(LANG_MENU["ru"], callback_data="ui_lang:ru"),
            ],
        ]
    )


def audio_lang_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    """Idioma del audio antes de Transcribir/MP3."""
    code = lang or "es"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(LANG_MENU["es"], callback_data="audio_lang:es"),
                InlineKeyboardButton(LANG_MENU["en"], callback_data="audio_lang:en"),
            ],
            [
                InlineKeyboardButton(LANG_MENU["fr"], callback_data="audio_lang:fr"),
                InlineKeyboardButton(LANG_MENU["ru"], callback_data="audio_lang:ru"),
            ],
            [
                InlineKeyboardButton(LANG_MENU["auto"], callback_data="audio_lang:auto"),
            ],
            [
                InlineKeyboardButton(t("btn_cancel", code), callback_data="audio_lang:cancel"),
            ],
        ]
    )


def job_mode_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    """Tras elegir idioma del audio: Transcribir o MP3."""
    code = lang or "es"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t("btn_link_transcribe", code), callback_data="job_mode:transcribe"
                ),
            ],
            [
                InlineKeyboardButton(
                    t("btn_link_mp3_only", code), callback_data="job_mode:mp3"
                ),
            ],
            [
                InlineKeyboardButton(t("btn_cancel", code), callback_data="job_mode:cancel"),
            ],
        ]
    )


def main_menu_inline(lang: str | None = None) -> InlineKeyboardMarkup | None:
    """Sin botones bajo el menú: basta con enviar archivo o enlace."""
    return None


def export_format_keyboard(kind: str, lang: str | None = None) -> InlineKeyboardMarkup:
    code = lang or "es"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(t("btn_txt", code), callback_data=f"fmt_get:{kind}_txt"),
                InlineKeyboardButton(t("btn_pdf", code), callback_data=f"fmt_get:{kind}_pdf"),
            ],
            [
                InlineKeyboardButton(t("btn_back", code), callback_data="fmt_back"),
            ],
        ]
    )


def summary_back_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    code = lang or "es"
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t("btn_back", code), callback_data="fmt_back")]]
    )


def summary_page_keyboard(
    page: int, total_pages: int, lang: str | None = None
) -> InlineKeyboardMarkup:
    code = lang or "es"
    rows: list[list[InlineKeyboardButton]] = []
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(t("page_prev", code), callback_data="sum_nav:prev")
            )
        nav.append(
            InlineKeyboardButton(
                t("page_indicator", code, cur=page + 1, total=total_pages),
                callback_data="sum_nav:noop",
            )
        )
        if page < total_pages - 1:
            nav.append(
                InlineKeyboardButton(t("page_next", code), callback_data="sum_nav:next")
            )
        rows.append(nav)
    rows.append([InlineKeyboardButton(t("btn_back", code), callback_data="fmt_back")])
    return InlineKeyboardMarkup(rows)


def link_mode_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    """Compat: mismo teclado que job_mode (callbacks job_mode:*)."""
    return job_mode_keyboard(lang)


def mp3_meta_prompt_keyboard(
    lang: str | None = None, *, link_only: bool = False
) -> InlineKeyboardMarkup:
    """Durante título/autor: siempre visible descarga directa sin metadatos."""
    code = lang or "es"
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                t("btn_mp3_direct", code), callback_data="fmt_get:mp3_direct"
            ),
        ],
    ]
    if link_only:
        rows.append(
            [InlineKeyboardButton(t("btn_send_another", code), callback_data="home")]
        )
    else:
        rows.append([InlineKeyboardButton(t("btn_back", code), callback_data="fmt_back")])
    return InlineKeyboardMarkup(rows)


def cancel_job_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    code = lang or "es"
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t("btn_cancel", code), callback_data="action:cancel")]]
    )


def _toc_pagination_row(
    toc_page: int, pages: int, prev_cb: str, next_cb: str, lang: str
) -> list[InlineKeyboardButton] | None:
    if pages <= 1:
        return None
    nav: list[InlineKeyboardButton] = []
    if toc_page > 0:
        nav.append(InlineKeyboardButton(t("toc_page_prev", lang), callback_data=prev_cb))
    nav.append(
        InlineKeyboardButton(
            t("toc_page_indicator", lang, cur=toc_page + 1, total=pages),
            callback_data="mom_nav:noop",
        )
    )
    if toc_page < pages - 1:
        nav.append(InlineKeyboardButton(t("toc_page_next", lang), callback_data=next_cb))
    return nav


def index_toc_keyboard(
    blocks, toc_page: int, *, page_size: int = INDEX_TOC_PAGE_SIZE, lang: str | None = None
) -> InlineKeyboardMarkup:
    code = lang or "es"
    total = len(blocks)
    pages = max(1, math.ceil(total / page_size))
    toc_page = max(0, min(toc_page, pages - 1))
    start = toc_page * page_size
    chunk = blocks[start : start + page_size]

    rows: list[list[InlineKeyboardButton]] = []
    for b in chunk:
        rows.append(
            [
                InlineKeyboardButton(
                    chapter_button_label(b),
                    callback_data=f"mom_nav:goto:{b.index - 1}",
                )
            ]
        )

    nav = _toc_pagination_row(toc_page, pages, "mom_nav:tocprev", "mom_nav:tocnext", code)
    if nav:
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(t("index_txt", code), callback_data="fmt_get:index_txt"),
            InlineKeyboardButton(t("index_pdf", code), callback_data="fmt_get:index_pdf"),
        ]
    )
    rows.append([InlineKeyboardButton(t("btn_back", code), callback_data="fmt_back")])
    return InlineKeyboardMarkup(rows)


def search_empty_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    """Sin coincidencias o texto corto: atrás al menú del vídeo, luego otra búsqueda."""
    code = lang or "es"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t("btn_back", code), callback_data="fmt_back")],
            [
                InlineKeyboardButton(
                    t("btn_search_again", code), callback_data="search_nav:new"
                )
            ],
        ]
    )


def search_result_keyboard(
    page: int,
    total: int,
    *,
    seek_url: str | None = None,
    seek_label: str = "",
    lang: str | None = None,
) -> InlineKeyboardMarkup:
    code = lang or "es"
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(t("search_prev", code), callback_data="search_nav:prev")
        )
    nav.append(
        InlineKeyboardButton(
            t("search_indicator", code, cur=page + 1, total=total),
            callback_data="search_nav:noop",
        )
    )
    if page < total - 1:
        nav.append(
            InlineKeyboardButton(t("search_next", code), callback_data="search_nav:next")
        )
    rows.append(nav)

    seek_row = _seek_button_row(seek_url, label=seek_label)
    if seek_row:
        rows.append(seek_row)

    rows.append([InlineKeyboardButton(t("btn_back", code), callback_data="fmt_back")])
    rows.append(
        [
            InlineKeyboardButton(
                t("btn_search_again", code), callback_data="search_nav:new"
            ),
        ]
    )
    return InlineKeyboardMarkup(rows)


def _seek_button_row(seek_url: str | None, *, label: str) -> list[InlineKeyboardButton] | None:
    if seek_url and label:
        return [InlineKeyboardButton(label, url=seek_url)]
    return None


def moment_page_keyboard(
    chapter_page: int,
    chapter_total: int,
    *,
    text_page: int = 0,
    text_total: int = 1,
    seek_url: str | None = None,
    seek_label: str = "",
    lang: str | None = None,
) -> InlineKeyboardMarkup:
    code = lang or "es"
    rows: list[list[InlineKeyboardButton]] = []

    if text_total > 1:
        tnav: list[InlineKeyboardButton] = []
        if text_page > 0:
            tnav.append(
                InlineKeyboardButton(t("text_prev", code), callback_data="mom_nav:subprev")
            )
        tnav.append(
            InlineKeyboardButton(
                t("fragment_indicator", code, cur=text_page + 1, total=text_total),
                callback_data="mom_nav:noop",
            )
        )
        if text_page < text_total - 1:
            tnav.append(
                InlineKeyboardButton(t("text_next", code), callback_data="mom_nav:subnext")
            )
        rows.append(tnav)

    cnav: list[InlineKeyboardButton] = []
    if chapter_page > 0:
        cnav.append(
            InlineKeyboardButton(t("chapter_prev", code), callback_data="mom_nav:prev")
        )
    cnav.append(
        InlineKeyboardButton(
            t("chapter_indicator", code, cur=chapter_page + 1, total=chapter_total),
            callback_data="mom_nav:noop",
        )
    )
    if chapter_page < chapter_total - 1:
        cnav.append(
            InlineKeyboardButton(t("chapter_next", code), callback_data="mom_nav:next")
        )
    rows.append(cnav)

    seek_row = _seek_button_row(seek_url, label=seek_label)
    if seek_row:
        rows.append(seek_row)

    rows.append(
        [InlineKeyboardButton(t("chapter_list", code), callback_data="mom_nav:toc")]
    )
    rows.append(
        [
            InlineKeyboardButton(t("index_txt", code), callback_data="fmt_get:index_txt"),
            InlineKeyboardButton(t("index_pdf", code), callback_data="fmt_get:index_pdf"),
        ]
    )
    rows.append([InlineKeyboardButton(t("btn_back", code), callback_data="fmt_back")])
    return InlineKeyboardMarkup(rows)


def highlights_toc_keyboard(
    items, toc_page: int, *, page_size: int = HIGHLIGHTS_TOC_PAGE_SIZE, lang: str | None = None
) -> InlineKeyboardMarkup:
    code = lang or "es"
    total = len(items)
    pages = max(1, math.ceil(total / page_size))
    toc_page = max(0, min(toc_page, pages - 1))
    start = toc_page * page_size
    chunk = items[start : start + page_size]

    rows: list[list[InlineKeyboardButton]] = []
    for h in chunk:
        rows.append(
            [
                InlineKeyboardButton(
                    highlight_button_label(h),
                    callback_data=f"hi_nav:goto:{h.index - 1}",
                )
            ]
        )

    if pages > 1:
        nav: list[InlineKeyboardButton] = []
        if toc_page > 0:
            nav.append(
                InlineKeyboardButton(t("toc_page_prev", code), callback_data="hi_nav:tocprev")
            )
        nav.append(
            InlineKeyboardButton(
                t("toc_page_indicator", code, cur=toc_page + 1, total=pages),
                callback_data="hi_nav:noop",
            )
        )
        if toc_page < pages - 1:
            nav.append(
                InlineKeyboardButton(t("toc_page_next", code), callback_data="hi_nav:tocnext")
            )
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(t("highlights_txt", code), callback_data="fmt_get:highlights_txt"),
            InlineKeyboardButton(t("highlights_pdf", code), callback_data="fmt_get:highlights_pdf"),
        ]
    )
    rows.append([InlineKeyboardButton(t("btn_back", code), callback_data="fmt_back")])
    return InlineKeyboardMarkup(rows)


def highlight_page_keyboard(
    item_page: int,
    item_total: int,
    *,
    text_page: int = 0,
    text_total: int = 1,
    seek_url: str | None = None,
    seek_label: str = "",
    lang: str | None = None,
) -> InlineKeyboardMarkup:
    code = lang or "es"
    rows: list[list[InlineKeyboardButton]] = []

    if text_total > 1:
        tnav: list[InlineKeyboardButton] = []
        if text_page > 0:
            tnav.append(
                InlineKeyboardButton(t("text_prev", code), callback_data="hi_nav:subprev")
            )
        tnav.append(
            InlineKeyboardButton(
                t("fragment_indicator", code, cur=text_page + 1, total=text_total),
                callback_data="hi_nav:noop",
            )
        )
        if text_page < text_total - 1:
            tnav.append(
                InlineKeyboardButton(t("text_next", code), callback_data="hi_nav:subnext")
            )
        rows.append(tnav)

    cnav: list[InlineKeyboardButton] = []
    if item_page > 0:
        cnav.append(
            InlineKeyboardButton(t("highlight_prev", code), callback_data="hi_nav:prev")
        )
    cnav.append(
        InlineKeyboardButton(
            t("highlight_indicator", code, cur=item_page + 1, total=item_total),
            callback_data="hi_nav:noop",
        )
    )
    if item_page < item_total - 1:
        cnav.append(
            InlineKeyboardButton(t("highlight_next", code), callback_data="hi_nav:next")
        )
    rows.append(cnav)

    seek_row = _seek_button_row(seek_url, label=seek_label)
    if seek_row:
        rows.append(seek_row)

    rows.append(
        [InlineKeyboardButton(t("highlight_list", code), callback_data="hi_nav:toc")]
    )
    rows.append(
        [
            InlineKeyboardButton(t("highlights_txt", code), callback_data="fmt_get:highlights_txt"),
            InlineKeyboardButton(t("highlights_pdf", code), callback_data="fmt_get:highlights_pdf"),
        ]
    )
    rows.append([InlineKeyboardButton(t("btn_back", code), callback_data="fmt_back")])
    return InlineKeyboardMarkup(rows)


def transcript_page_keyboard(
    page: int, total_pages: int, lang: str | None = None, context=None
) -> InlineKeyboardMarkup:
    code = lang or "es"
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(t("page_prev", code), callback_data="tx_nav:prev"))
    nav.append(
        InlineKeyboardButton(
            t("page_indicator", code, cur=page + 1, total=total_pages),
            callback_data="tx_nav:noop",
        )
    )
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(t("page_next", code), callback_data="tx_nav:next"))

    rows: list[list[InlineKeyboardButton]] = [nav]
    if context is not None:
        rows.extend(_variant_switch_rows(context, code))
    rows.extend(_after_transcript_action_rows(code))
    return InlineKeyboardMarkup(rows)


def lang_from_context(context) -> str:
    return get_lang(context)
