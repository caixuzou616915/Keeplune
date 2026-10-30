---
name: aumovio-pptx
description: "Create AUMOVIO-branded PowerPoint (.pptx) decks from a JSON spec using python-pptx, then render slides to PNG for visual QA. Use when the user asks for a presentation, slide deck, or .pptx output, wants an AUMOVIO-styled deck, or asks to generate slides from structured content (title, section, bullets, cards, table, chart, closing). Not for editing arbitrary existing decks."
---

# AUMOVIO PPTX builder

In-house skill. Written from scratch on `python-pptx` (MIT); contains no third-party skill code.
`assets/template.pptx` is the AUMOVIO corporate template - internal use only.

## Workflow

1. Write a JSON spec (see `assets/sample_spec.json`).
2. Build: `python scripts/build_deck.py spec.json out/deck.pptx`. Read any `WARN` lines on stderr.
3. QA (Windows + PowerPoint): `powershell -File scripts/render_pptx.ps1 -Pptx out/deck.pptx` then view `out/qa/slide-NN.png`.
4. Fix any warned slide in the spec (shorten text, split content) and rebuild.

Requires `pip install python-pptx pillow`.

## Slide types

| type | template layout | fields |
|---|---|---|
| `title` | Cover (gradient) | `title`, `subtitle`, `org` (bottom right), `author` |
| `section` | Section (gradient) 01 | `title`, `number` (large, bottom right), `subtitle` |
| `bullets` | Content with enumeration list | `category`, `title`, `bullets`: strings, `{text, sub:[...]}`, `{heading}` (bold line) or `{para}` (plain paragraph) |
| `cards` | Title (white) | `category`, `title`, `cards:[{heading, body}]` (2-4 cards) |
| `table` | Title (white) | `category`, `title`, `columns`, `rows`, optional `col_widths` |
| `chart` | Title (white) | `category`, `title`, `chart:{type: bar/line/pie, categories, series:[{name, values}]}`, optional `takeaway` |
| `closing` | End (gradient) | `title` (default "Thank you"), `subtitle` |

All slides accept `notes` (speaker notes). Top level: `meta` (footer text), `date` (default: current month), `template` (path to another template with the same layout names).

## Text fitting

Text is measured with the installed font files (`AUMOVIO Office`, falling back to Arial/DejaVu) and wrapped like PowerPoint does:

- Every text block shrinks in 5% steps until it fits its box (minimum 60%; 50% for cover/section titles, 40% for the closing title).
- Bullet lists and tables shrink only to 90%; beyond that they continue on extra slides titled `... (cont.)`. Table headers repeat.
- Card heights follow their content; all cards on a slide share one font scale.
- Text that still does not fit is written at minimum size and reported as `WARN slide N (...)`.

## Brand rules

- Logo, gradients, footer (copyright, footer text, date, page number, classification) come from the template master and layouts - do not draw them.
- Content headline: orange `category` line (title placeholder), black `title` line (subheadline); each one line.
- Card/table/chart palette: orange `FF4208` (dominant), purple `4827AF`, blue `18A9E7`, peach `FFB7A1`, tint `FFF0EB`, text `111111`. Flat, sharp-cornered blocks; no shadows.
- Default content language is English.

## Limits

- Card text and single table rows are not split; very long cards or cells only shrink and warn.
- Only the layouts listed above are used; picture and agenda layouts of the template are not wired up.
