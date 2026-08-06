"""
Locale profiles and bidirectional text preparation for report rendering.

This module centralises everything the reporting code needs to know about
a language in order to render it faithfully:

- ``LocaleProfile``: a declarative description of a report locale (text
  direction, script, HarfBuzz language tag, fonts and wrap mode).
- ``get_locale_profile``: profile lookup with a backward-compatible
  fallback for languages that are only described by the ``fonts``
  worksheet of ``_report_configuration.xlsx`` (where ``Align == 'Right'``
  has historically implied a right-to-left language).
- ``prepare_mpl_text``: the single entry point used to prepare text for
  Matplotlib, which cannot shape Arabic script or reorder bidirectional
  text by itself.  Text is kept in logical (Unicode) order for as long as
  possible: optional wrapping happens on the logical string, and only then
  is each resulting line shaped (``arabic_reshaper``) and reordered for
  display (Unicode Bidirectional Algorithm).
- ``configure_pdf_text_shaping``: explicit fpdf2/HarfBuzz text shaping
  configuration (direction, script and language) so right-to-left reports
  do not depend on per-string auto-detection of the base direction.

Zero-width non-joiner (ZWNJ, U+200C) handling
---------------------------------------------
ZWNJ is meaningful orthography in Persian (e.g. ``می‌روم``, ``خانه‌ها``)
and must never be replaced by a space, deleted, or converted to another
character.  Guarantees provided by this module:

- ``arabic_reshaper`` is configured so that ZWNJ (and Arabic diacritics /
  harakat, and tatweel) pass through unmodified; ZWNJ still breaks
  cursive joining exactly as required.
- Logical wrapping never breaks words at ZWNJ (it is not whitespace, and
  ``break_long_words`` is disabled).
- The bidirectional reordering implemented here re-injects ZWNJ into the
  display string.  (Rule X9 of the Unicode Bidirectional Algorithm treats
  ZWNJ as a "boundary neutral" and reference implementations drop it from
  reordered output; we restore it adjacent to its logical neighbours so
  the display string contains exactly the same characters as the logical
  string.)

Unicode normalisation
---------------------
Right-to-left text is normalised with NFC before shaping (this composes
decomposed letter+mark sequences the shaper would otherwise not join).
NFC never affects ZWNJ.  No other rewriting of translated content is
performed: in particular harakat are preserved and no NLP-style
"normalisers" are used.

Bidirectional algorithm implementation
--------------------------------------
The display-order transformation reuses fpdf2's Unicode Bidirectional
Algorithm implementation (``fpdf.bidi``, UAX #9 revision 48) so that
Matplotlib figures and fpdf2-generated PDF text resolve directions
identically -- including the paired-bracket rules (BD16/N0).  On top of
the resolved embedding levels this module applies:

- rule L2 (run reversal), performed on grapheme-like clusters so that
  combining marks stay attached to their base character;
- rule L3 (combining marks follow their base character in display order,
  which is what Matplotlib's simple glyph layout requires);
- rule L4 (bracket/symbol mirroring).  This matters because
  ``python-bidi`` 0.6.x does not mirror brackets, which made
  ``(GHSCI)`` render as ``)GHSCI(`` in right-to-left figure labels.
"""

import unicodedata
from dataclasses import dataclass
from textwrap import wrap

from arabic_reshaper import ArabicReshaper
from fpdf.bidi import BidiCharacter, BidiParagraph
from fpdf.enums import TextDirection

ZWNJ = '‌'
ZWJ = '‍'


def _fpdf_drops_joining_controls():
    """
    Probe whether the installed fpdf2 loses ZWNJ from bidi fragments.

    Builds a pristine ``BidiParagraph`` for a Persian word containing a
    zero-width non-joiner and checks that every character survives into
    ``get_bidi_fragments()``.  Pure computation without side effects;
    used at import time so the shim below is installed only on fpdf2
    builds that actually exhibit the defect.
    """
    probe_text = 'می' + ZWNJ + 'روم'
    paragraph = BidiParagraph(
        text=probe_text,
        base_direction=TextDirection.RTL,
    )
    recovered = ''.join(
        fragment for fragment, _ in paragraph.get_bidi_fragments()
    )
    return recovered != probe_text


def _install_fpdf_joining_control_preservation():
    """
    Make fpdf2's bidirectional algorithm keep ZWNJ and ZWJ.

    fpdf2 (tested with 2.8.7) applies rule X9 of the Unicode
    Bidirectional Algorithm literally, removing "boundary neutral"
    characters from its resolved character stream.  The stream is used to
    build the directional runs passed to HarfBuzz for shaping, so the
    zero-width non-joiner (U+200C) and zero-width joiner (U+200D) never
    reach the shaping engine and Persian words like ``می‌روم`` are
    rendered incorrectly joined (``میروم``) in generated PDFs.

    UAX #9 removes these characters for the purposes of the *algorithm*
    only; renderers are expected to keep them for shaping.  This shim
    re-injects the two joining controls into ``BidiParagraph``'s resolved
    character list, each taking the embedding level of the character it
    follows so directional runs are unaffected.  Both controls carry
    orthographic meaning and are zero-width, so this changes joining
    behaviour only.  Idempotent; applied when this module is imported,
    and only when the feature probe above shows the installed fpdf2
    still loses the characters -- a future release that preserves them
    itself is left unpatched.
    """
    if getattr(BidiParagraph, '_ghsci_preserves_joining_controls', False):
        return
    if not _fpdf_drops_joining_controls():
        # Nothing to fix in this fpdf2 build; mark it handled so the
        # probe runs at most once per process.
        BidiParagraph._ghsci_preserves_joining_controls = True
        return
    original_init = BidiParagraph.__init__

    def init_preserving_joining_controls(self, text, *args, **kwargs):
        original_init(self, text, *args, **kwargs)
        if not text or (ZWNJ not in text and ZWJ not in text):
            return
        retained = {
            bidi_character.character_index: bidi_character
            for bidi_character in self.characters
        }
        if len(retained) == len(text):
            return
        rebuilt = []
        previous_level = self.base_embedding_level
        for index, character in enumerate(text):
            if index in retained:
                rebuilt.append(retained[index])
                previous_level = retained[index].embedding_level
            elif character in (ZWNJ, ZWJ):
                rebuilt.append(
                    BidiCharacter(index, character, previous_level, False),
                )
        self.characters = rebuilt

    BidiParagraph.__init__ = init_preserving_joining_controls
    BidiParagraph._ghsci_preserves_joining_controls = True


_install_fpdf_joining_control_preservation()

# Unicode blocks whose characters require Arabic-script shaping.
_ARABIC_BLOCKS = (
    (0x0600, 0x06FF),  # Arabic (includes Persian letters and digits)
    (0x0750, 0x077F),  # Arabic Supplement
    (0x08A0, 0x08FF),  # Arabic Extended-A
    (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
)

# Bidi rule L4 mirror pairs (subset of Unicode BidiMirroring.txt that can
# plausibly occur in report phrases).  A mirrored character appearing in a
# right-to-left run must be rendered as its pair; renderers without bidi
# support (Matplotlib) need the swap baked into the display string.
_MIRROR_PAIRS = {
    '(': ')',
    ')': '(',
    '[': ']',
    ']': '[',
    '{': '}',
    '}': '{',
    '<': '>',
    '>': '<',
    '«': '»',
    '»': '«',
    '‹': '›',
    '›': '‹',
    '⟨': '⟩',
    '⟩': '⟨',
    '≤': '≥',
    '≥': '≤',
}


@dataclass(frozen=True)
class LocaleProfile:
    """
    Declarative description of a report locale.

    Fields:

    - ``code``: BCP 47 language code (e.g. 'fa'), as recorded in the
      ``language_code`` row of the languages worksheet.
    - ``name``: language name as used in the report configuration
      workbook (e.g. 'Persian').
    - ``direction``: base text direction, 'ltr' or 'rtl'.
    - ``script``: ISO 15924 / OpenType script tag (e.g. 'arab', 'latn')
      passed to HarfBuzz when shaping PDF text.
    - ``hb_language``: HarfBuzz (BCP 47) language tag enabling
      language-specific font behaviour (e.g. 'fa', 'ar').
    - ``primary_font``: font family name registered with fpdf2 (matches
      the ``Font`` column of the fonts worksheet).
    - ``fallback_fonts``: fpdf2 fallback font families for glyphs missing
      from the primary font.
    - ``wrap_mode``: fpdf2 wrap mode, 'WORD' or 'CHAR'.  Word wrapping
      never splits at ZWNJ because ZWNJ is not whitespace.
    - ``requires_arabic_shaping``: whether text must be run through
      ``arabic_reshaper`` before it can be drawn by renderers that do not
      shape Arabic script themselves (Matplotlib).
    """

    code: str
    name: str
    direction: str = 'ltr'
    script: str = 'latn'
    hb_language: str = None
    primary_font: str = None
    fallback_fonts: tuple = ('dejavu',)
    wrap_mode: str = 'WORD'
    requires_arabic_shaping: bool = False

    @property
    def is_rtl(self):
        """True if the locale's base text direction is right-to-left."""
        return self.direction == 'rtl'


# Registry of known locale profiles, keyed by the language names used in
# the languages worksheet of _report_configuration.xlsx.  Languages not
# listed here fall back to workbook-driven behaviour (see
# get_locale_profile); adding a new right-to-left language is a matter of
# appending a profile here and configuring its font in the workbook.
LOCALE_PROFILES = {
    'default': LocaleProfile(
        code='en',
        name='default',
        direction='ltr',
        script='latn',
        hb_language='en',
        primary_font='dejavu',
    ),
    'Arabic': LocaleProfile(
        code='ar',
        name='Arabic',
        direction='rtl',
        script='arab',
        hb_language='ar',
        primary_font='Vazirmatn',
        fallback_fonts=('dejavu',),
        wrap_mode='WORD',
        requires_arabic_shaping=True,
    ),
    'Persian': LocaleProfile(
        code='fa',
        name='Persian',
        direction='rtl',
        script='arab',
        hb_language='fa',
        primary_font='Vazirmatn',
        fallback_fonts=('dejavu',),
        wrap_mode='WORD',
        requires_arabic_shaping=True,
    ),
}

# Also allow lookup by language code (e.g. 'fa' from phrases['language_code']).
_PROFILES_BY_CODE = {
    profile.code: profile
    for profile in LOCALE_PROFILES.values()
    if profile.name != 'default'
}


def get_locale_profile(
    language,
    align_hint=None,
    font_hint=None,
    wrap_hint=None,
):
    """
    Return the LocaleProfile for a report language.

    The language may be given by name (e.g. 'Persian', or
    'Arabic (Auto-translation)') or by code (e.g. 'fa').  The registered
    profile is returned when one exists; otherwise an ad-hoc profile is
    derived from the optional fonts-worksheet hints, so that languages
    configured only in the workbook keep working unchanged.  For backward
    compatibility with existing workbooks, an ``align_hint`` of 'Right'
    (the ``Align`` column) marks such a language as right-to-left, and
    ``font_hint``/``wrap_hint`` carry its ``Font`` and ``Wrapmode``
    columns.
    """
    if language is None:
        return LOCALE_PROFILES['default']
    language = str(language).replace(' (Auto-translation)', '').strip()
    if language in LOCALE_PROFILES:
        return LOCALE_PROFILES[language]
    if language in _PROFILES_BY_CODE:
        return _PROFILES_BY_CODE[language]
    if str(align_hint).strip().lower() == 'right':
        # Workbook-driven right-to-left language without a registered
        # profile: assume Arabic-script shaping (reshaping is a no-op for
        # non-Arabic text, e.g. Hebrew, so this is safe).
        return LocaleProfile(
            code=language,
            name=language,
            direction='rtl',
            script='arab',
            hb_language=None,
            primary_font=font_hint,
            wrap_mode=wrap_hint or 'WORD',
            requires_arabic_shaping=True,
        )
    return LocaleProfile(
        code=language,
        name=language,
        direction='ltr',
        script='latn',
        hb_language=None,
        primary_font=font_hint,
        wrap_mode=wrap_hint or 'WORD',
    )


def contains_arabic(text):
    """True if text contains characters from Arabic script blocks."""
    return any(
        start <= ord(character) <= end
        for character in str(text)
        for (start, end) in _ARABIC_BLOCKS
    )


# arabic_reshaper selects Arabic presentation forms (joining) for
# renderers that cannot shape.  The configuration below preserves
# translated content exactly:
# - delete_harakat=False keeps Arabic diacritics (the library default
#   deletes them, silently rewriting e.g. 'السَّلَامُ عَلَيْكُمْ');
# - delete_tatweel=False keeps tatweel/kashida;
# - ZWNJ is not a reshapeable letter and passes through unchanged while
#   still breaking joining, which is exactly its purpose.
_ARABIC_RESHAPER = ArabicReshaper(
    configuration={
        'delete_harakat': False,
        'delete_tatweel': False,
        'shift_harakat_position': False,
        'support_zwj': True,
    },
)


def shape_arabic_text(text):
    """
    Replace Arabic letters with their joined presentation forms.

    The output remains in logical order; combining marks (harakat), ZWNJ
    and all non-Arabic characters are preserved unchanged.
    """
    return _ARABIC_RESHAPER.reshape(text)


def _base_direction(base):
    if isinstance(base, TextDirection):
        return base
    if str(base).upper() in ('R', 'RTL'):
        return TextDirection.RTL
    return TextDirection.LTR


def bidi_display_line(line, base='R'):
    """
    Reorder one logical line into display (drawing) order.

    Uses fpdf2's Unicode Bidirectional Algorithm implementation to resolve
    embedding levels, then applies rules L2 (reversal, cluster-wise so
    combining marks travel with their base character), L3 (marks follow
    their base in display order) and L4 (bracket mirroring).  Characters
    the algorithm classifies as boundary-neutral (notably ZWNJ) are
    re-injected so no character of the logical line is lost.

    ``line`` is logical-order text without newlines (shape Arabic text
    with shape_arabic_text first if the renderer needs joined forms) and
    ``base`` is the base paragraph direction, 'R'/'RTL' or 'L'/'LTR'.
    Returns the line in left-to-right drawing order for simple renderers
    such as Matplotlib.
    """
    if line == '':
        return line
    paragraph = BidiParagraph(
        text=line,
        base_direction=_base_direction(base),
    )
    # Resolved characters in logical order; embedding levels are final
    # after this call (rule L1 applied).  Rule X9 removes boundary-neutral
    # characters (ZWNJ/ZWJ and explicit directional controls) from this
    # list; character_index lets us re-inject them below.
    resolved = paragraph.get_characters_with_embedding_level()
    base_level = paragraph.base_embedding_level
    levels_by_index = {
        bidi_character.character_index: bidi_character.embedding_level
        for bidi_character in resolved
    }
    # Group characters into clusters of (base character + its combining
    # marks + trailing boundary-neutral characters such as ZWNJ), so that
    # reversal never separates marks from bases (rule L3) and re-injected
    # characters stay adjacent to their logical neighbours.  Each cluster
    # is [level, core characters, trailing boundary-neutral characters].
    clusters = []
    for index, character in enumerate(line):
        level = levels_by_index.get(index)
        if level is None and clusters:
            # Boundary-neutral character dropped by rule X9 (e.g. ZWNJ):
            # re-inject attached to the preceding cluster.
            clusters[-1][2].append(character)
            continue
        if unicodedata.combining(character) and clusters:
            # Combining mark: keep with its base character.
            clusters[-1][1].append(character)
            continue
        clusters.append([level, [character], []])
    # A line that begins with an unattached character (e.g. leading ZWNJ
    # or combining mark) produces a cluster without a resolved level;
    # give it its neighbour's level.
    for position, cluster in enumerate(clusters):
        if cluster[0] is None:
            cluster[0] = (
                clusters[position + 1][0]
                if position + 1 < len(clusters)
                else base_level
            )
    # Rule L2: from the highest level down to the lowest odd level,
    # reverse any contiguous sequence of clusters at or above that level.
    max_level = max(cluster[0] for cluster in clusters)
    odd_levels = [cluster[0] for cluster in clusters if cluster[0] % 2]
    min_odd_level = min(odd_levels) if odd_levels else max_level + 1
    for threshold in range(max_level, min_odd_level - 1, -1):
        reordered = []
        run = []
        for cluster in clusters:
            if cluster[0] >= threshold:
                run.append(cluster)
            else:
                reordered.extend(reversed(run))
                run = []
                reordered.append(cluster)
        reordered.extend(reversed(run))
        clusters = reordered
    # Emit clusters.  Within reversed (odd-level) runs a logically
    # trailing boundary-neutral character is drawn to the left of -- i.e.
    # before -- its base, keeping it between the same visual neighbours
    # as in the logical text.  Combining marks always follow their base
    # in drawing order (rule L3, as simple renderers expect).  Rule L4:
    # characters at a right-to-left (odd) level render mirrored.
    display_characters = []
    for level, core, boundary_neutral in clusters:
        if level % 2:
            ordered = list(reversed(boundary_neutral)) + core
        else:
            ordered = core + boundary_neutral
        for character in ordered:
            if (
                level % 2
                and character in _MIRROR_PAIRS
                and unicodedata.mirrored(character)
            ):
                display_characters.append(_MIRROR_PAIRS[character])
            else:
                display_characters.append(character)
    return ''.join(display_characters)


def wrap_logical_text(text, width, is_rtl=False, rewrap=False):
    """
    Wrap logical-order text, returning a list of logical-order lines.

    Wrapping is performed before any shaping or reordering so that line
    breaks fall between logical words.  Words are never broken internally
    (so ZWNJ-joined compounds like ``برنامه‌ریزی`` stay intact; ZWNJ is
    not whitespace and never becomes a break point) and, for
    right-to-left text, hyphenated words are also kept whole.

    With ``rewrap=True`` any existing newlines are treated as ordinary
    whitespace and the text is re-flowed to the requested width (standard
    ``textwrap`` semantics); otherwise each existing line is wrapped
    independently and blank lines are preserved.
    """
    rtl_wrap_options = {'break_on_hyphens': False} if is_rtl else {}
    if rewrap:
        wrapped = wrap(
            str(text),
            width,
            break_long_words=False,
            **rtl_wrap_options,
        )
        return wrapped if wrapped else ['']
    lines = []
    for logical_line in str(text).splitlines() or ['']:
        if logical_line.strip() == '':
            lines.append(logical_line)
            continue
        wrapped = wrap(
            logical_line,
            width,
            break_long_words=False,
            **rtl_wrap_options,
        )
        lines.extend(wrapped if wrapped else [logical_line])
    return lines


def prepare_mpl_text(text, profile=None, wrap_width=None, rewrap=False):
    """
    Prepare text for rendering with Matplotlib.

    Matplotlib neither shapes Arabic script nor applies the Unicode
    Bidirectional Algorithm, so right-to-left text must be converted from
    logical order to a shaped, display-ordered string.  The pipeline is:

    1. keep the text in logical order;
    2. wrap the logical text if ``wrap_width`` is given (unless it
       already contains explicit newlines, which are respected -- pass
       ``rewrap=True`` to re-flow such text instead);
    3. for locales requiring it, NFC-normalise and shape each line
       (``arabic_reshaper``; ZWNJ, harakat and tatweel preserved);
    4. reorder each line separately for display with the locale's base
       direction (so multi-line right-to-left text reads top-to-bottom);
    5. join lines with newlines.

    Left-to-right text without Arabic characters is returned unchanged
    (apart from optional wrapping), so English and other LTR reports are
    unaffected.

    ``text`` is logical-order text (or any value convertible to str).
    ``profile`` is the LocaleProfile of the report language; if None, the
    profile is inferred from the text content (Arabic characters imply an
    Arabic-script right-to-left locale), matching the behaviour of the
    legacy ``mpl_reshape`` helper.  ``wrap_width`` sets an optional
    maximum number of characters per line, applied to the logical text
    before shaping; ``rewrap=True`` treats existing newlines as ordinary
    whitespace when wrapping (standard ``textwrap`` semantics) instead of
    respecting them.  Returns text ready to pass to Matplotlib.
    """
    if text is None:
        return text
    text = str(text)
    if profile is None:
        if contains_arabic(text):
            profile = LOCALE_PROFILES['Arabic']
        else:
            profile = LOCALE_PROFILES['default']
    needs_shaping = profile.requires_arabic_shaping and contains_arabic(text)
    needs_bidi = profile.is_rtl or needs_shaping
    # Wrap logical text first; if the text already contains newlines they
    # define the layout and wrapping is skipped (matching the historical
    # behaviour of the report figure functions) unless rewrap is set.
    if wrap_width is not None and (rewrap or '\n' not in text):
        lines = wrap_logical_text(
            text,
            wrap_width,
            is_rtl=profile.is_rtl,
            rewrap=rewrap,
        )
    else:
        lines = text.splitlines() or ['']
    if not needs_bidi:
        return '\n'.join(lines)
    display_lines = []
    for line in lines:
        # NFC composes decomposed letter+mark pairs so they shape as
        # single letters.  ZWNJ is unaffected by NFC.
        line = unicodedata.normalize('NFC', line)
        if needs_shaping:
            line = shape_arabic_text(line)
        display_lines.append(
            bidi_display_line(line, base='R' if profile.is_rtl else 'L'),
        )
    return '\n'.join(display_lines)


def configure_pdf_text_shaping(pdf, profile, enable=True):
    """
    Configure fpdf2 text shaping explicitly for the report locale.

    For right-to-left locales the paragraph base direction, script and
    language are passed to fpdf2/HarfBuzz rather than relying on
    per-string auto-detection.  Auto-detection assigns a left-to-right
    base direction to any string that happens to start with a Latin
    letter or digit (e.g. ``2026 تهران`` or template score strings),
    mis-ordering the remainder of the line in Persian and Arabic reports;
    an explicit base direction resolves such mixed strings correctly.

    Left-to-right locales keep fpdf2's automatic per-fragment detection,
    which is the historical behaviour and correctly renders occasional
    embedded right-to-left words.

    ``pdf`` is an fpdf.FPDF instance and ``profile`` the LocaleProfile of
    the report language; pass ``enable=False`` to disable the shaping
    engine entirely (as per the ``Text shaping`` column of the fonts
    worksheet).
    """
    if not enable:
        pdf.set_text_shaping(False)
        return pdf
    if profile.is_rtl:
        pdf.set_text_shaping(
            use_shaping_engine=True,
            direction=profile.direction,
            script=profile.script,
            language=profile.hb_language,
        )
    else:
        pdf.set_text_shaping(True)
    return pdf
