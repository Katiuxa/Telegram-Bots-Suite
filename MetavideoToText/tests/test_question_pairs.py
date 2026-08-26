"""Emparejado ¿?/¡! — no dejar aperturas con punto ni tumbar multi-pregunta."""

from bot.services.orthography import restore_formatted_orthography, strip_bogus_question_marks
from bot.services.text_polish import pair_spanish_inverted_punctuation


SAMPLE = (
    "¿Te has dado cuenta que una de las cosas más raras de esta generación "
    "es que ya no sabemos existir sin ser observados?\n\n"
    "Y que cada paso que das tiene que ser compartido, explicado y visto "
    "y que si no lo muestras casi pareciera que no tienes vida o que es "
    "sospechoso Porque antes había partes de la vida que simplemente eran "
    "privadas, como tu casa, tus relaciones, tus gustos extraños y ahora "
    "el internet quiere tour completo de tu existencia. "
    "¿Cómo te preparas tu café. ¿Dónde compras tu ropa. ¿Tienes link?\n\n"
    "Compárteme el link ¿Cuánto pagas de renta. "
    "¿Cómo le haces para pagar esa renta. "
    "¿Por qué cortaste con tu novio. ¡Cuéntamelo todo!"
)


def _orphan_opens(text: str) -> list[str]:
    bad: list[str] = []
    i = 0
    while i < len(text):
        if text[i] in "¿¡":
            open_ch = text[i]
            close_ch = "?" if open_ch == "¿" else "!"
            j = i + 1
            while j < len(text) and text[j] not in "¿¡\n":
                if text[j] in ".!?…":
                    if text[j] != close_ch:
                        bad.append(text[i : j + 1])
                    break
                j += 1
            else:
                if j > i + 1:
                    bad.append(text[i:j] + "<no-close>")
        i += 1
    return bad


def test_pair_user_sample():
    out = pair_spanish_inverted_punctuation(SAMPLE)
    assert "¿Cómo te preparas tu café?" in out
    assert "¿Dónde compras tu ropa?" in out
    assert "¿Tienes link?" in out
    assert "Compárteme el link. ¿Cuánto pagas de renta?" in out
    assert "¿Cómo le haces para pagar esa renta?" in out
    assert "¿Por qué cortaste con tu novio?" in out
    assert "¡Cuéntamelo todo!" in out
    assert _orphan_opens(out) == []


def test_restore_formatted_pipeline():
    out = restore_formatted_orthography(SAMPLE, "es")
    assert "¿Por qué cortaste con tu novio?" in out
    assert _orphan_opens(out) == []


def test_strip_does_not_break_multi_question():
    glued = (
        "Compárteme el link ¿Cuánto pagas de renta? "
        "¿Cómo le haces para pagar esa renta? ¿Por qué cortaste con tu novio?"
    )
    out = strip_bogus_question_marks(glued)
    assert out.count("?") == 3
    assert "¿Cuánto pagas de renta?" in out
    assert "¿Por qué cortaste con tu novio?" in out


def test_false_question_still_demoted():
    assert strip_bogus_question_marks("Hay un chisme?") == "Hay un chisme."
    assert strip_bogus_question_marks("Es que yo te veo mejor?") == (
        "Es que yo te veo mejor."
    )


def test_abbrev_period_inside_question():
    s = "¿Viste al Sr. García ayer?"
    assert pair_spanish_inverted_punctuation(s) == s
