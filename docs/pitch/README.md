# Pitch

Everything for presenting TrueLift. The numbers in the deck, the notes and the one-pager are
generated from `reports/` by `scripts/make_deck.py`; the question bank's numbers are checked by
`scripts/check_claims.py`. Customers, orders and profits are simulated on real 2019 listings, and
every file says so.

| File | What it is |
|---|---|
| [`TrueLift_deck.pdf`](TrueLift_deck.pdf) | The deck: twelve slides and eight appendix slides (source [`deck.html`](deck.html): open it in a browser, arrow keys move, P presents, N shows notes) |
| [`TrueLift_deck.pptx`](TrueLift_deck.pptx) | The same deck as an editable PowerPoint file, with speaker notes |
| [`speaker_notes.md`](speaker_notes.md) | What to say on each slide, timing, the five-minute cut, and one sentence each for leaders, domain experts and engineers on the results slides |
| [`runbook.md`](runbook.md) | Demo choreography, what to do when something fails, timing, rehearsals, and the ninety-second script for the audience's phones |
| [`questions.md`](questions.md) | Thirty questions with short answers, each with its number and source |
| [`TrueLift_one_page.pdf`](TrueLift_one_page.pdf) | One page to leave with the panel, with a QR code to the demo (source [`one_page.html`](one_page.html)) |
| `demo.mp4` | A captioned recording of the guided demo, the fallback if the live demo fails (`python tasks.py video`) |

The five-minute cut is slides 1, 3, 6, 7, 8 and 12. The deck and the video use no real restaurant
names (decision D5); the live demo shows the real listing names, labelled as simulated data.

Rebuild after any change to `reports/`:

```bash
python tasks.py deck     # deck.html, notes, one-pager, PDFs and the PPTX
python tasks.py video    # demo.mp4, after python tasks.py export
```
