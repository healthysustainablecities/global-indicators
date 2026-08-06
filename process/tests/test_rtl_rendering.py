"""
Regression tests for right-to-left (Arabic/Persian) report rendering.

These tests protect the guarantees documented in
``subprocesses/_report_locales.py`` (see also upstream issue #478):

- zero-width non-joiner (ZWNJ, U+200C) is preserved exactly -- never
  removed, never replaced by a space or another invisible character;
- Persian and Arabic letters are joined correctly (contextual forms),
  including *not* joining across ZWNJ;
- text is not visually reversed when drawn by renderers without
  bidirectional support (Matplotlib);
- mixed-direction content (Latin words, numbers, percentages, units,
  parentheses and URLs) is ordered correctly, including bracket
  mirroring;
- wrapping happens on logical text, never splits words at ZWNJ, and
  multi-line right-to-left text reads top-to-bottom;
- English and other left-to-right output is byte-for-byte unchanged.

The visual fixture classes render representative Persian and Arabic
Matplotlib figures and PDF pages and compare them against committed
baseline images (regenerate with GHSCI_UPDATE_VISUAL_BASELINES=1).

Run from the ``process`` directory (all tests are also collected when
running ``python -m unittest -v tests/tests.py``):

    python -m unittest -v tests/test_rtl_rendering.py
"""

import os
import unicodedata
import unittest
from textwrap import wrap as textwrap_wrap

from subprocesses._report_locales import (
    LOCALE_PROFILES,
    ZWNJ,
    bidi_display_line,
    configure_pdf_text_shaping,
    contains_arabic,
    get_locale_profile,
    prepare_mpl_text,
    shape_arabic_text,
    wrap_logical_text,
)

# Logical-order sample strings (translator-style content).
MIRAVAM = 'می‌روم'  # 'I go': ZWNJ between می and روم
KHANEHHA = 'خانه‌ها'  # 'houses': ZWNJ between خانه and ها
TRANSPORT_PLANNING = 'برنامه‌ریزی حمل‌ونقل'  # two ZWNJ compounds
TEHRAN_YEAR_FA = 'تهران ۲۰۲۶'  # Persian (extended Arabic-Indic) digits
TEHRAN_YEAR_MIXED = 'تهران 2026 (GHSCI)'  # Latin digits and acronym
SALAM_AR = 'السَّلَامُ عَلَيْكُمْ'  # Arabic with harakat (diacritics)
MIXED_FA_EN = 'دسترسی GHSCI به گزارش 2026'
URL_FA = 'برای اطلاعات بیشتر: https://example.org/report دیدن کنید'

FA = LOCALE_PROFILES['Persian']
AR = LOCALE_PROFILES['Arabic']
EN = LOCALE_PROFILES['default']

# Expected display-order renderings (drawn left-to-right by Matplotlib).
# تهران shaped right-to-left is drawn as noon, alef, reh, heh, teh:
TEHRAN_DISPLAY = 'ﻥﺍﺮﻬﺗ'
EXPECTED_TEHRAN_YEAR_FA = '۲۰۲۶ ' + TEHRAN_DISPLAY
EXPECTED_TEHRAN_YEAR_MIXED = '(GHSCI) 2026 ' + TEHRAN_DISPLAY


def joining_form(character):
    """Return the contextual form of an Arabic presentation form character.

    E.g. 'ARABIC LETTER HEH FINAL FORM' -> 'FINAL'; ZWNJ -> 'ZWNJ';
    other characters -> ''.
    """
    if character == ZWNJ:
        return 'ZWNJ'
    name = unicodedata.name(character, '')
    for form in ('INITIAL', 'MEDIAL', 'FINAL', 'ISOLATED'):
        if name.endswith(f'{form} FORM'):
            return form
    return ''


class TestLocaleProfiles(unittest.TestCase):
    """The centralised locale profile abstraction."""

    def test_rtl_profiles_are_fully_specified(self):
        for name in ('Persian', 'Arabic'):
            profile = LOCALE_PROFILES[name]
            self.assertEqual(profile.direction, 'rtl')
            self.assertTrue(profile.is_rtl)
            self.assertEqual(profile.script, 'arab')
            self.assertTrue(profile.requires_arabic_shaping)
            self.assertEqual(profile.primary_font, 'Vazirmatn')
            self.assertIn('dejavu', profile.fallback_fonts)
            self.assertEqual(profile.wrap_mode, 'WORD')
        self.assertEqual(LOCALE_PROFILES['Persian'].code, 'fa')
        self.assertEqual(LOCALE_PROFILES['Persian'].hb_language, 'fa')
        self.assertEqual(LOCALE_PROFILES['Arabic'].code, 'ar')
        self.assertEqual(LOCALE_PROFILES['Arabic'].hb_language, 'ar')

    def test_lookup_by_name_code_and_auto_translation_suffix(self):
        self.assertEqual(get_locale_profile('Persian').code, 'fa')
        self.assertEqual(get_locale_profile('fa').name, 'Persian')
        self.assertEqual(
            get_locale_profile('Arabic (Auto-translation)').code,
            'ar',
        )

    def test_workbook_align_right_fallback_marks_rtl(self):
        # Backward compatibility: a language configured only in the fonts
        # worksheet with Align == 'Right' must be treated as right-to-left.
        profile = get_locale_profile(
            'Urdu',
            align_hint='Right',
            font_hint='SomeFont',
        )
        self.assertTrue(profile.is_rtl)
        self.assertTrue(profile.requires_arabic_shaping)
        self.assertEqual(profile.primary_font, 'SomeFont')

    def test_unknown_language_defaults_to_ltr(self):
        profile = get_locale_profile('Esperanto', align_hint='Left')
        self.assertFalse(profile.is_rtl)
        self.assertFalse(profile.requires_arabic_shaping)


class TestZWNJPreservation(unittest.TestCase):
    """ZWNJ must survive every stage of text preparation, unmodified."""

    def test_logical_source_text_contains_zwnj(self):
        for text, count in (
            (MIRAVAM, 1),
            (KHANEHHA, 1),
            (TRANSPORT_PLANNING, 2),
        ):
            self.assertEqual(text.count(ZWNJ), count)
            # preparing text must not mutate the logical source
            copy = str(text)
            prepare_mpl_text(text, FA)
            self.assertEqual(text, copy)
            self.assertEqual(text.count(ZWNJ), count)

    def test_shaping_preserves_zwnj(self):
        for text in (MIRAVAM, KHANEHHA, TRANSPORT_PLANNING):
            shaped = shape_arabic_text(text)
            self.assertEqual(shaped.count(ZWNJ), text.count(ZWNJ))

    def test_display_pipeline_preserves_zwnj_exactly(self):
        for text in (MIRAVAM, KHANEHHA, TRANSPORT_PLANNING):
            display = prepare_mpl_text(text, FA)
            self.assertEqual(display.count(ZWNJ), text.count(ZWNJ))
        # ZWNJ is never replaced by a space or another invisible character
        display = prepare_mpl_text(MIRAVAM, FA)
        for forbidden in (' ', '​', ' ', '‍', '⁠'):
            self.assertNotIn(forbidden, display)

    def test_wrapping_never_splits_words_at_zwnj(self):
        for width in range(3, 25):
            lines = wrap_logical_text(
                TRANSPORT_PLANNING,
                width,
                is_rtl=True,
            )
            # Breaks may only occur at the space: both ZWNJ compounds
            # must appear intact on whichever line carries them.
            reassembled = ' '.join(lines)
            self.assertEqual(reassembled, TRANSPORT_PLANNING)
            for line in lines:
                if ZWNJ in line:
                    self.assertTrue(
                        'برنامه‌ریزی' in line or 'حمل‌ونقل' in line,
                        f'width {width} split a ZWNJ compound: {lines!r}',
                    )


class TestArabicJoining(unittest.TestCase):
    """Persian and Arabic letters must join correctly (and only where
    joining is orthographically required)."""

    def test_khaneh_joins_and_zwnj_breaks_joining(self):
        display = prepare_mpl_text(KHANEHHA, FA)
        forms = [joining_form(c) for c in display]
        # Drawn left-to-right: ...ها | ZWNJ | خانه...  The heh ending
        # خانه (drawn right of the ZWNJ) takes FINAL form; the heh
        # beginning ها (drawn left of the ZWNJ) takes INITIAL form: the
        # ZWNJ breaks joining exactly between the two, with the same
        # visual neighbours as in the logical text.
        zwnj_at = display.index(ZWNJ)
        self.assertEqual(forms[zwnj_at + 1], 'FINAL')
        self.assertEqual(forms[zwnj_at - 1], 'INITIAL')
        self.assertEqual(
            unicodedata.name(display[zwnj_at + 1]),
            'ARABIC LETTER HEH FINAL FORM',
        )
        self.assertEqual(
            unicodedata.name(display[zwnj_at - 1]),
            'ARABIC LETTER HEH INITIAL FORM',
        )

    def test_miravam_joining_forms(self):
        display = prepare_mpl_text(MIRAVAM, FA)
        # the *first* logical letter م must be the rightmost drawn glyph
        # (last in string order), in INITIAL form joined to ی
        self.assertEqual(
            unicodedata.name(display[-1]),
            'ARABIC LETTER MEEM INITIAL FORM',
        )
        # the leftmost drawn glyph is the م of روم, which stands alone
        # (ISOLATED) because و cannot join forward
        self.assertEqual(
            unicodedata.name(display[0]),
            'ARABIC LETTER MEEM ISOLATED FORM',
        )
        # ی before the ZWNJ takes FINAL form: the ZWNJ correctly ends the
        # joining group of می rather than being dropped or spaced
        zwnj_at = display.index(ZWNJ)
        self.assertEqual(
            unicodedata.name(display[zwnj_at + 1]),
            'ARABIC LETTER FARSI YEH FINAL FORM',
        )

    def test_arabic_harakat_preserved_and_attached(self):
        display = prepare_mpl_text(SALAM_AR, AR)
        marks_in = sum(1 for c in SALAM_AR if unicodedata.combining(c))
        marks_out = sum(1 for c in display if unicodedata.combining(c))
        # The arabic_reshaper default configuration deletes harakat;
        # ours must not rewrite translated content.
        self.assertEqual(marks_in, marks_out)
        self.assertGreater(marks_out, 0)
        # Each combining mark must directly follow a base glyph in drawn
        # order (Matplotlib attaches marks to the preceding glyph).
        for position, character in enumerate(display):
            if unicodedata.combining(character):
                preceding = display[position - 1]
                self.assertFalse(
                    preceding.isspace(),
                    'combining mark separated from its base character',
                )
        # lam-alef must be ligated for shapers-less renderers
        self.assertTrue(
            any('LAM WITH ALEF' in unicodedata.name(c, '') for c in display),
            'expected a lam-alef ligature presentation form',
        )

    def test_glyphs_joined_not_isolated(self):
        # A fully-connecting word must contain no isolated forms at all
        # (بیشتر consists solely of dual-joining letters plus a final ر).
        display = prepare_mpl_text('بیشتر', FA)
        forms = [joining_form(c) for c in display]
        self.assertNotIn('ISOLATED', forms)
        self.assertIn('INITIAL', forms)
        self.assertIn('MEDIAL', forms)
        self.assertIn('FINAL', forms)


class TestBidiOrdering(unittest.TestCase):
    """Display order for renderers without bidirectional support."""

    def test_text_is_not_visually_reversed(self):
        # The first logical letter must be the rightmost drawn glyph
        # (= last in string order), not the leftmost: a reversed string
        # here means the figure would read backwards.
        display = prepare_mpl_text('تهران', FA)
        self.assertEqual(display, TEHRAN_DISPLAY)
        self.assertEqual(
            unicodedata.name(display[-1]),
            'ARABIC LETTER TEH INITIAL FORM',
        )

    def test_persian_digits_keep_logical_order(self):
        display = prepare_mpl_text(TEHRAN_YEAR_FA, FA)
        self.assertEqual(display, EXPECTED_TEHRAN_YEAR_FA)
        # digits read left-to-right even inside right-to-left text
        self.assertIn('۲۰۲۶', display)
        self.assertNotIn('۶۲۰۲', display)

    def test_mixed_latin_number_and_mirrored_parentheses(self):
        display = prepare_mpl_text(TEHRAN_YEAR_MIXED, FA)
        self.assertEqual(display, EXPECTED_TEHRAN_YEAR_MIXED)
        # bracket mirroring (bidi rule L4): the parenthesised Latin
        # acronym must render '(GHSCI)', not ')GHSCI('
        self.assertIn('(GHSCI)', display)
        self.assertNotIn(')GHSCI(', display)
        self.assertIn('2026', display)
        self.assertNotIn('6202', display)

    def test_mixed_arabic_english_label(self):
        display = prepare_mpl_text(MIXED_FA_EN, FA)
        # Latin words and numbers stay intact and unreversed
        self.assertIn('GHSCI', display)
        self.assertIn('2026', display)
        # A right-to-left base direction places the first logical
        # (Persian) word rightmost, i.e. at the end of the drawn string.
        self.assertEqual(
            unicodedata.name(display[-1]),
            'ARABIC LETTER DAL ISOLATED FORM',
        )
        # and the trailing logical number '2026' is drawn leftmost
        self.assertTrue(display.startswith('2026'))

    def test_urls_remain_intact(self):
        display = prepare_mpl_text(URL_FA, FA)
        self.assertIn('https://example.org/report', display)

    def test_arabic_percent_stays_with_number(self):
        display = prepare_mpl_text('دسترسی ۵۰٪ (خوب)', FA)
        # the percent sign stays adjacent to its digits and parentheses
        # around the Persian word are mirrored for display
        self.assertIn('٪', display)
        digits_at = display.index('۵')
        self.assertIn(
            '٪',
            display[max(0, digits_at - 2) : digits_at + 3],
        )
        self.assertNotIn(')بوخ(', display.replace(' ', ''))

    def test_base_direction_parameter(self):
        # explicit right-to-left base ordering of a neutral-heavy string
        self.assertEqual(bidi_display_line('abc', base='L'), 'abc')
        self.assertEqual(bidi_display_line('', base='R'), '')


class TestMultilineWrapping(unittest.TestCase):
    """Wrapping happens on logical text; each line is shaped separately."""

    def test_multiline_persian_reads_top_to_bottom(self):
        display = prepare_mpl_text(TRANSPORT_PLANNING, FA, wrap_width=12)
        lines = display.split('\n')
        self.assertEqual(len(lines), 2)
        # each display line equals the independently prepared logical word,
        # so the first logical word is on the first (top) line
        self.assertEqual(lines[0], prepare_mpl_text('برنامه‌ریزی', FA))
        self.assertEqual(lines[1], prepare_mpl_text('حمل‌ونقل', FA))
        self.assertEqual(
            [line.count(ZWNJ) for line in lines],
            [1, 1],
        )

    def test_multiline_persian_label(self):
        multiline = 'دسترسی به خدمات\nو حمل‌ونقل عمومی'
        display = prepare_mpl_text(multiline, FA)
        lines = display.split('\n')
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], prepare_mpl_text('دسترسی به خدمات', FA))
        self.assertEqual(lines[1], prepare_mpl_text('و حمل‌ونقل عمومی', FA))

    def test_explicit_newlines_respected_without_rewrap(self):
        multiline = 'یک\nدو'
        display = prepare_mpl_text(multiline, FA, wrap_width=40)
        self.assertEqual(len(display.split('\n')), 2)


class TestLTRUnchanged(unittest.TestCase):
    """English and other left-to-right output must not change."""

    ENGLISH_SAMPLES = (
        'Percentage of population with access to public transport',
        'Population % with access within 500m to...',
        '25 city median (14.5)',
        'GOHSC 2026 - spatial indicators',
        'https://doi.org/10.25439/rmt.19586048',
        '50%',
        '12/24 policies identified',
    )

    def test_english_text_identity(self):
        for text in self.ENGLISH_SAMPLES:
            self.assertEqual(prepare_mpl_text(text, EN), text)
            # also via the content-based heuristic used by legacy callers
            self.assertEqual(prepare_mpl_text(text), text)

    def test_english_wrapping_matches_textwrap(self):
        text = 'Percentage of population with access to public transport'
        self.assertEqual(
            prepare_mpl_text(text, EN, wrap_width=20),
            '\n'.join(textwrap_wrap(text, 20, break_long_words=False)),
        )

    def test_english_rewrap_matches_legacy_radar_semantics(self):
        # the radar chart historically re-flowed manually line-broken
        # phrases with textwrap defaults (newlines treated as spaces)
        text = '% of\npopulation\nwith access\nwithin 500m\nto:'
        self.assertEqual(
            prepare_mpl_text(text, EN, wrap_width=13, rewrap=True),
            '\n'.join(textwrap_wrap(text, 13, break_long_words=False)),
        )

    def test_legacy_mpl_reshape_alias(self):
        from subprocesses._utils import mpl_reshape

        self.assertEqual(mpl_reshape('Public transport'), 'Public transport')
        self.assertEqual(mpl_reshape(MIRAVAM), prepare_mpl_text(MIRAVAM, FA))

    def test_contains_arabic(self):
        self.assertTrue(contains_arabic(MIRAVAM))
        self.assertTrue(contains_arabic(SALAM_AR))
        self.assertFalse(contains_arabic('Las Palmas 2026 (GHSCI)'))


class TestFpdfJoiningControlPreservation(unittest.TestCase):
    """fpdf2's bidi algorithm must not lose ZWNJ/ZWJ before shaping.

    fpdf2 2.8.7 removes boundary-neutral characters (rule X9) from the
    directional runs it passes to HarfBuzz, which joined Persian words
    across ZWNJ in generated PDFs; _report_locales installs a shim that
    re-injects the joining controls (see
    _install_fpdf_joining_control_preservation).
    """

    def test_bidi_fragments_keep_zwnj(self):
        from fpdf.bidi import BidiParagraph
        from fpdf.enums import TextDirection

        for text in (MIRAVAM, KHANEHHA, TRANSPORT_PLANNING):
            paragraph = BidiParagraph(
                text=text,
                base_direction=TextDirection.RTL,
            )
            fragments = paragraph.get_bidi_fragments()
            self.assertEqual(
                ''.join(fragment for fragment, _ in fragments),
                text,
                'fpdf2 bidi fragments must preserve every character, '
                'including ZWNJ',
            )

    def test_mixed_direction_fragments_still_split_correctly(self):
        from fpdf.bidi import BidiParagraph
        from fpdf.enums import TextDirection

        paragraph = BidiParagraph(
            text=MIXED_FA_EN,
            base_direction=TextDirection.RTL,
        )
        fragments = paragraph.get_bidi_fragments()
        directions = [direction.name for _, direction in fragments]
        self.assertIn('LTR', directions)
        self.assertIn('RTL', directions)
        self.assertEqual(
            ''.join(fragment for fragment, _ in fragments),
            MIXED_FA_EN,
        )

    def test_feature_probe_reports_no_defect_after_installation(self):
        from subprocesses._report_locales import _fpdf_drops_joining_controls

        # Importing _report_locales either found an fpdf2 build that
        # already preserves joining controls or installed the shim; in
        # both cases the import-time feature probe must now report the
        # defect as absent.
        self.assertFalse(_fpdf_drops_joining_controls())


class TestPDFShapingConfiguration(unittest.TestCase):
    """fpdf2 text shaping is configured explicitly for RTL locales."""

    def _pdf(self):
        from fpdf import FPDF

        return FPDF(orientation='portrait', format='A4', unit='mm')

    def test_rtl_locale_sets_direction_script_language(self):
        from fpdf.enums import TextDirection

        pdf = configure_pdf_text_shaping(self._pdf(), FA)
        self.assertIsNotNone(pdf.text_shaping)
        self.assertEqual(
            pdf.text_shaping['direction'],
            TextDirection.RTL,
        )
        self.assertEqual(pdf.text_shaping['script'], 'arab')
        self.assertEqual(pdf.text_shaping['language'], 'fa')
        pdf = configure_pdf_text_shaping(self._pdf(), AR)
        self.assertEqual(pdf.text_shaping['language'], 'ar')

    def test_ltr_locale_keeps_automatic_detection(self):
        pdf = configure_pdf_text_shaping(self._pdf(), EN)
        self.assertIsNotNone(pdf.text_shaping)
        self.assertIsNone(pdf.text_shaping['direction'])

    def test_shaping_can_be_disabled(self):
        pdf = configure_pdf_text_shaping(self._pdf(), FA, enable=False)
        self.assertIsNone(pdf.text_shaping)


class TestTemplateLayoutTransformations(unittest.TestCase):
    """Named right-to-left layout transformations for PDF templates."""

    def _elements(self):
        import pandas as pd

        return pd.DataFrame(
            {
                'name': [
                    'Low',
                    'study region legend patch a',
                    'study region legend patch b',
                    'study region legend patch c',
                    'title',
                    'centered_item',
                ],
                'align': ['L', 'L', 'L', 'L', 'J', 'C'],
                'x1': [78.0, 14.0, 75.0, 136.0, 10.0, 50.0],
                'x2': [102.0, 24.0, 85.0, 146.0, 200.0, 150.0],
            },
        )

    def test_mirror_template_alignment(self):
        from subprocesses._utils import mirror_template_alignment

        elements = mirror_template_alignment(self._elements())
        self.assertEqual(
            elements['align'].tolist(),
            ['R', 'R', 'R', 'R', 'R', 'C'],
        )

    def test_named_rtl_element_shifts(self):
        from subprocesses._utils import (
            RTL_ELEMENT_SHIFTS,
            apply_rtl_element_shifts,
        )

        for shift in RTL_ELEMENT_SHIFTS:
            self.assertTrue(shift['purpose'])
        elements = apply_rtl_element_shifts(self._elements())
        moved = elements.set_index('name')
        self.assertEqual(moved.loc['Low', 'x1'], 78 - 18)
        self.assertEqual(moved.loc['Low', 'x2'], 102 - 18)
        self.assertEqual(
            moved.loc['study region legend patch a', 'x1'],
            14 + 46,
        )
        self.assertEqual(
            moved.loc['study region legend patch c', 'x1'],
            136 + 50,
        )
        # elements without a named shift are untouched
        self.assertEqual(moved.loc['title', 'x1'], 10)
        self.assertEqual(moved.loc['centered_item', 'x2'], 150)


VAZIRMATN = (
    'configuration/fonts/vazirmatn-v33.003/fonts/ttf/Vazirmatn-Regular.ttf'
)
DEJAVU = (
    'configuration/fonts/dejavu-fonts-ttf-2.37/ttf/DejaVuSansCondensed.ttf'
)
BASELINE_DIR = 'tests/baselines/rtl'
ARTIFACT_DIR = 'tests/artifacts/rtl'
UPDATE_BASELINES = os.environ.get('GHSCI_UPDATE_VISUAL_BASELINES') == '1'
# Baselines and artifacts are rendered by the same pinned stack, so a
# clean re-render is pixel-identical (measured: 0 differing pixels on
# every fixture) and both tolerances below are pure headroom.  The
# whole-image mean absolute difference catches broad regressions
# (reversed/unjoined text moves most glyphs), but on a mostly-white
# page it dilutes corruption confined to one text line (erasing a
# single rendered line scores only ~0.1-0.7 on these fixtures).  The
# changed-pixel ratio closes that gap: erasing even the lightest single
# line changes >=0.05% of pixels by more than CHANGED_PIXEL_DELTA
# grayscale levels (measured per fixture: 0.05-1.07%), safely above
# CHANGED_PIXEL_RATIO_LIMIT.
MEAN_DIFFERENCE_LIMIT = 2.0
CHANGED_PIXEL_DELTA = 20
CHANGED_PIXEL_RATIO_LIMIT = 0.0002

VISUAL_SAMPLES = {
    'Persian': (
        MIRAVAM,
        KHANEHHA,
        TRANSPORT_PLANNING,
        TEHRAN_YEAR_FA,
        TEHRAN_YEAR_MIXED,
        'دسترسی به خدمات\nو حمل‌ونقل عمومی',
        MIXED_FA_EN,
    ),
    'Arabic': (
        SALAM_AR,
        'النسبة المئوية للسكان الذين يمكنهم الوصول (٪50)',
        'الوصول إلى GHSCI 2026',
    ),
    'English': (
        'Percentage of population with access',
        'GOHSC 2026 (GHSCI)',
    ),
}


def compare_with_baseline(test_case, artifact_path, baseline_name):
    """
    Compare a rendered image against its committed baseline.

    Asserts two complementary grayscale metrics: the whole-image mean
    absolute difference (broad regressions such as reversed or unjoined
    text, which move most glyphs) and the changed-pixel ratio (local
    corruption confined to a single text line, which white space would
    otherwise dilute below the mean's tolerance).  See the tolerance
    constants above for the calibration rationale.
    Set GHSCI_UPDATE_VISUAL_BASELINES=1 to (re)create baselines.
    """
    from PIL import Image

    baseline_path = os.path.join(BASELINE_DIR, baseline_name)
    if UPDATE_BASELINES or not os.path.exists(baseline_path):
        os.makedirs(BASELINE_DIR, exist_ok=True)
        Image.open(artifact_path).save(baseline_path)
        if not UPDATE_BASELINES:
            test_case.skipTest(
                f'baseline created at {baseline_path}; re-run to compare',
            )
        return
    with Image.open(artifact_path) as rendered, Image.open(
        baseline_path,
    ) as baseline:
        rendered = rendered.convert('L')
        baseline = baseline.convert('L')
        test_case.assertEqual(
            rendered.size,
            baseline.size,
            'rendered image size differs from baseline',
        )
        total_pixels = rendered.size[0] * rendered.size[1]
        difference_sum = 0
        changed_pixels = 0
        for a, b in zip(rendered.getdata(), baseline.getdata()):
            delta = abs(a - b)
            difference_sum += delta
            if delta > CHANGED_PIXEL_DELTA:
                changed_pixels += 1
        mean_difference = difference_sum / total_pixels
        changed_ratio = changed_pixels / total_pixels
        test_case.assertLessEqual(
            mean_difference,
            MEAN_DIFFERENCE_LIMIT,
            f'visual regression against {baseline_path} '
            f'(mean absolute difference {mean_difference:.2f})',
        )
        test_case.assertLessEqual(
            changed_ratio,
            CHANGED_PIXEL_RATIO_LIMIT,
            f'visual regression against {baseline_path} '
            f'({changed_pixels} pixels, {changed_ratio:.4%}, differ by '
            f'more than {CHANGED_PIXEL_DELTA} grayscale levels)',
        )


@unittest.skipUnless(
    os.path.exists(VAZIRMATN),
    'Vazirmatn font not found (run from the process directory)',
)
class TestVisualMatplotlibFixture(unittest.TestCase):
    """Visual regression fixture for Matplotlib RTL rendering."""

    @classmethod
    def setUpClass(cls):
        import matplotlib

        matplotlib.use('Agg')
        import matplotlib.font_manager as fm
        import matplotlib.pyplot as plt

        fm.fontManager.addfont(VAZIRMATN)
        cls.font_name = fm.FontProperties(fname=VAZIRMATN).get_name()
        cls.plt = plt
        os.makedirs(ARTIFACT_DIR, exist_ok=True)

    def render_language_fixture(self, language):
        profile = get_locale_profile(language)
        samples = VISUAL_SAMPLES[language]
        figure, axes = self.plt.subplots(
            figsize=(6, 0.7 * len(samples) + 0.5),
        )
        axes.set_axis_off()
        for row, sample in enumerate(samples):
            axes.text(
                0.98,
                1 - (row + 0.5) / len(samples),
                prepare_mpl_text(sample, profile, wrap_width=60),
                fontsize=14,
                fontfamily=self.font_name,
                ha='right',
                va='center',
                transform=axes.transAxes,
            )
        artifact = os.path.join(
            ARTIFACT_DIR,
            f'matplotlib_{language.lower()}.png',
        )
        figure.savefig(artifact, dpi=100)
        self.plt.close(figure)
        compare_with_baseline(
            self,
            artifact,
            f'matplotlib_{language.lower()}.png',
        )

    def test_persian_figure_text(self):
        self.render_language_fixture('Persian')

    def test_arabic_figure_text(self):
        self.render_language_fixture('Arabic')

    def test_english_control_figure_text(self):
        self.render_language_fixture('English')


@unittest.skipUnless(
    os.path.exists(VAZIRMATN),
    'Vazirmatn font not found (run from the process directory)',
)
class TestVisualPDFFixture(unittest.TestCase):
    """
    Visual regression fixture for fpdf2 RTL page rendering.

    Rasterisation uses pypdfium2, a self-contained test-only dependency
    (bundled PDFium; no system packages): the Docker image provides no
    other PDF rasterisation tool (its GDAL build has no PDF driver and
    poppler/ghostscript are not installed).  The test is skipped when
    pypdfium2 is unavailable.
    """

    def render_language_page(self, language, samples):
        from fpdf import FPDF

        try:
            import pypdfium2
        except ImportError:
            self.skipTest(
                'pypdfium2 not installed (test-only dependency used to '
                'rasterise PDF pages; pip install pypdfium2)',
            )
        profile = get_locale_profile(language)
        pdf = FPDF(orientation='portrait', format='A5', unit='mm')
        pdf.add_font('Vazirmatn', style='', fname=VAZIRMATN)
        pdf.add_font('dejavu', style='', fname=DEJAVU)
        pdf.set_fallback_fonts(['dejavu'])
        configure_pdf_text_shaping(pdf, profile)
        pdf.set_auto_page_break(False)
        pdf.add_page()
        pdf.set_font('Vazirmatn', size=13)
        pdf.set_y(10)
        for sample in samples:
            pdf.multi_cell(
                w=pdf.epw,
                h=8,
                text=sample,
                align='R' if profile.is_rtl else 'L',
                new_x='LMARGIN',
                new_y='NEXT',
            )
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        pdf_path = os.path.join(ARTIFACT_DIR, f'pdf_{language.lower()}.pdf')
        pdf.output(pdf_path)
        document = pypdfium2.PdfDocument(pdf_path)
        try:
            page = document[0]
            bitmap = page.render(scale=1.5)
            image = bitmap.to_pil()
        finally:
            document.close()
        artifact = os.path.join(ARTIFACT_DIR, f'pdf_{language.lower()}.png')
        image.save(artifact)
        compare_with_baseline(self, artifact, f'pdf_{language.lower()}.png')

    def test_persian_pdf_page(self):
        self.render_language_page('Persian', VISUAL_SAMPLES['Persian'])

    def test_arabic_pdf_page(self):
        self.render_language_page('Arabic', VISUAL_SAMPLES['Arabic'])

    def test_english_control_pdf_page(self):
        self.render_language_page('English', VISUAL_SAMPLES['English'])


if __name__ == '__main__':
    unittest.main(failfast=False)
