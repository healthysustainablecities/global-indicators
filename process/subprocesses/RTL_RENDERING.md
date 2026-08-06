# Right-to-left (Arabic/Persian) report rendering

This document explains how right-to-left (RTL) text is rendered in
generated reports, the guarantees the code provides, and how to add
support for another RTL language.  It complements the docstrings in
[`_report_locales.py`](_report_locales.py), which is the single module
responsible for locale-aware text handling (see upstream issue
[#478](https://github.com/healthysustainablecities/global-indicators/issues/478)).

## Why RTL text needs special handling

Persian and Arabic are written right-to-left in a cursive script whose
letters change shape depending on their neighbours (joining), and
reports mix in left-to-right content: Latin place names, numbers,
percentages, units, parentheses and URLs.  Two different rendering
stacks are involved:

- **PDF text (fpdf2 + uharfbuzz):** fpdf2 applies the Unicode
  Bidirectional Algorithm (UBA) and HarfBuzz shapes each directional run,
  so it needs *logical-order* text plus correct configuration
  (direction, script, language).
- **Matplotlib figures:** this depends on the Matplotlib version, so text
  is always passed through `mpl_text()`, which dispatches on
  `matplotlib_applies_complex_text_layout()`:
  - **3.11 and later** route layout through libraqm, which shapes and
    applies the UBA just as fpdf2 does, so they receive *logical-order*
    text (wrapped, but otherwise untouched).
  - **Before 3.11** Matplotlib performed neither shaping nor
    bidirectional reordering, so text must be converted before drawing:
    Arabic letters replaced by their joined presentation forms
    (`arabic_reshaper`) and characters reordered into display order, via
    `prepare_mpl_text()`.

  Applying `prepare_mpl_text()` on a libraqm-backed Matplotlib reverses
  the text a second time — `خانه‌ها` renders as `اه‌هناخ`, with glyphs
  falling back to isolated forms — so never hand its output straight to
  Matplotlib.  Native shaping also positions Arabic diacritics better
  than presentation-form substitution can, which is visible in the
  `matplotlib_arabic` baseline.

## Locale profiles

`_report_locales.LOCALE_PROFILES` declares what the rendering code needs
to know about each language:

| field | example (Persian) | purpose |
|---|---|---|
| `code` | `fa` | BCP 47 language code (matches `language_code` in the languages worksheet) |
| `name` | `Persian` | language name used in the workbook and region configuration |
| `direction` | `rtl` | base paragraph direction |
| `script` | `arab` | ISO 15924/OpenType script tag passed to HarfBuzz |
| `hb_language` | `fa` | HarfBuzz language tag (enables language-specific font rules) |
| `primary_font` | `Vazirmatn` | font family registered with fpdf2/Matplotlib |
| `fallback_fonts` | `('dejavu',)` | fpdf2 fallback fonts for missing glyphs |
| `wrap_mode` | `WORD` | fpdf2 wrap mode |
| `requires_arabic_shaping` | `True` | whether Matplotlib text must be reshaped |

`get_locale_profile()` resolves a language to its profile.  Languages
without a registered profile fall back to the hints in the `fonts`
worksheet of `_report_configuration.xlsx`, where `Align == 'Right'` has
historically marked RTL languages — existing workbook-only
configurations therefore keep working unchanged.

## PDF text shaping

`configure_pdf_text_shaping()` (called from `prepare_pdf_fonts`) enables
fpdf2 text shaping explicitly.  For RTL locales the base paragraph
direction, script and language are passed to fpdf2/HarfBuzz instead of
relying on per-string auto-detection, which would give a left-to-right
base direction to any string that happens to start with a Latin letter
or a digit and mis-order the rest of the line.  The `Text shaping`
column of the fonts worksheet can disable the shaping engine for a
language (it defaults to enabled).

### ZWNJ and the fpdf2 X9 shim

The zero-width non-joiner (ZWNJ, U+200C) is meaningful Persian
orthography (`می‌روم`, `خانه‌ها`, `برنامه‌ریزی`): it prevents letters
from joining without adding a visible space.  **It must never be
removed, replaced by a space, or converted to another character.**

fpdf2 (2.8.7) applies UBA rule X9 literally and removes
"boundary-neutral" characters — including ZWNJ — from the text it sends
to HarfBuzz, which silently re-joined Persian words in PDFs.  Importing
`_report_locales` runs a feature probe
(`_fpdf_drops_joining_controls()`) and — only when the installed fpdf2
still loses the characters — installs
`_install_fpdf_joining_control_preservation()`, a small idempotent shim
that re-injects ZWNJ/ZWJ into fpdf2's resolved character stream (each
takes the embedding level of the character it follows, so directional
runs are unaffected).  A future fpdf2 release that preserves these
characters itself is left unpatched; the probe and the regression test
(`TestFpdfJoiningControlPreservation`) are then the places from which
to retire the shim.

## Matplotlib text preparation

`mpl_text(text, profile, wrap_width=None, rewrap=False)` is the single
entry point, used by every figure text path (map colorbar labels, tick
labels, north arrow, scalebar, overlay legends, threshold labels, policy
rating labels and the access-profile radar chart).  It wraps the logical
text and then, only where Matplotlib does not do its own complex text
layout, applies `prepare_mpl_text()`.

`prepare_mpl_text(text, profile, wrap_width=None, rewrap=False)` is that
unconditional logical-to-display transform.  It remains directly
testable, and is what the pre-3.11 path uses.  Its pipeline keeps text in
logical order for as long as possible:

1. **Wrap logical text** (optional).  Wrapping happens *before* shaping
   so line breaks fall between logical words; words are never broken
   internally (ZWNJ compounds stay intact — ZWNJ is not whitespace and
   is never a break point).  Text that already contains newlines is
   respected unless `rewrap=True`.
2. **NFC-normalise** each line (composes decomposed letter+mark pairs;
   ZWNJ is unaffected).  No other rewriting of translated content is
   performed — in particular Arabic diacritics (harakat) and tatweel are
   preserved (`arabic_reshaper`'s *default* configuration would delete
   harakat; ours does not), and no NLP-style normalisers are used.
3. **Shape** each line with `arabic_reshaper` (joined presentation
   forms, lam-alef ligatures; ZWNJ passes through and still breaks
   joining).  Scripts that do not require shaping are not reshaped.
4. **Reorder** each line separately into display order using fpdf2's UBA
   implementation for level resolution (so figures and PDFs resolve
   directions identically, including the paired-bracket rules), plus:
   rule L2 applied cluster-wise so combining marks travel with their
   base character; rule L3 so marks follow their base in drawing order
   (as Matplotlib requires); and rule L4 bracket mirroring — necessary
   because `python-bidi` 0.6.x does not mirror brackets, which made
   `(GHSCI)` render as `)GHSCI(`.
5. Lines are joined with newlines, so multi-line RTL text reads
   top-to-bottom.

Left-to-right text without Arabic characters is returned unchanged, so
English and other LTR reports are byte-for-byte identical.

The legacy helper `mpl_reshape()` in `_utils.py` delegates to this
pipeline, inferring the locale from the text content.  It is the
unconditional transform, so its result must not be handed to a
libraqm-backed Matplotlib; use `mpl_text()` instead.

## Template layout for RTL locales

`pdf_template_setup()` adapts the PDF templates for RTL locales using
named, documented transformations in `_utils.py`:

- `mirror_template_alignment()` — left-aligned/justified template
  elements become right-aligned;
- `apply_rtl_element_shifts()` — the shifts declared in
  `RTL_ELEMENT_SHIFTS` reposition individual elements whose placement is
  directional (e.g. the 'Low' annotation of the 1000 Cities plot and the
  study region legend swatches), each with a documented purpose.

The templates themselves are unchanged.

## Font configuration

Fonts are configured in the `fonts` worksheet of
`process/configuration/_report_configuration.xlsx` (one row per style:
`''`, `b`, `i`, `bi`).  Persian and Arabic use
[Vazirmatn](https://github.com/rastikerdar/vazirmatn) (bundled under
`process/configuration/fonts/vazirmatn-v33.003/`), which covers Arabic
presentation forms, harakat, Persian digits, ZWNJ and Latin text;
DejaVu Sans Condensed is the fallback.  Matplotlib uses the same font
file via `get_and_setup_font()`.

## Adding another RTL language

1. Add the translation column to the `languages` worksheet of
   `_report_configuration.xlsx` (keep ZWNJ and diacritics exactly as the
   translator wrote them; do not "clean" the text).
2. Add rows to the `fonts` worksheet for the language (font files, and
   `Align = Right` for backward compatibility).  Bundle or reference a
   font that covers the script.
3. Register a `LocaleProfile` in `_report_locales.LOCALE_PROFILES` with
   the language's code, direction, script, HarfBuzz language tag, fonts
   and wrap mode.  (Without this the workbook `Align` fallback still
   yields correct rendering, but the explicit profile also provides the
   script/language tags to HarfBuzz.)
4. Add the language to a region configuration under
   `reporting: languages:` and generate a report; a not-yet-validated
   translation can be tested with
   `generate_report_for_language(r, language, validate_language=False)`.
5. Extend `process/tests/test_rtl_rendering.py` with representative
   strings for the language and regenerate the visual baselines
   (`GHSCI_UPDATE_VISUAL_BASELINES=1`), then inspect them before
   committing.

## Testing

```bash
# from the process directory (inside the Docker container):
python -m unittest -v tests/test_rtl_rendering.py
```

The suite covers ZWNJ preservation, joining forms, bidirectional
ordering (numbers, brackets, URLs, mixed Arabic/English), logical
wrapping, LTR invariance, fpdf2 shaping configuration, the template
layout transformations, and visual regression fixtures that render
representative Persian/Arabic Matplotlib figures and PDF pages and
compare them against the committed baselines in
`process/tests/baselines/rtl/` (set `GHSCI_UPDATE_VISUAL_BASELINES=1`
to regenerate after an intentional change).  The comparison asserts
both the whole-image mean absolute difference and a changed-pixel
ratio, so corruption confined to a single text line cannot hide in the
page's white space.

PDF pages are rasterised with `pypdfium2`, a self-contained test-only
dependency (bundled PDFium, no system packages); it was added because
the Docker image has no other PDF rasterisation tool (its GDAL build
lacks the PDF driver, and poppler/ghostscript are not installed).  The
PDF fixtures are skipped when `pypdfium2` is not available.

## Known limitations

- `phrases['locale']` combines the language code with the study region's
  country code (e.g. `fa_ES` for a Persian report about a Spanish city);
  for such mixed locales Babel may fall back to Latin digits or
  untranslated unit names in *generated* numbers.  Translated phrases
  (which carry their own Persian/Arabic digits) are unaffected.
- The north-arrow label is centred just outside the map frame; long
  words (e.g. `شمال`) can be slightly clipped on some figures.  This
  pre-existing placement issue affects wide labels in any language.
- `python-bidi` remains installed for backward compatibility but is no
  longer used by the rendering path (fpdf2's UBA implementation is used
  for both PDFs and figures so they cannot disagree).
