# TrueLift: submission

Team Banana, IIT Gandhinagar: Yash Goyal, Bhavay Goyal, Kshitish Madbhavi.
IITGN × Eternal hackathon, Round 2.

## Links

| What | Link |
|---|---|
| Live demo | https://yashg1836.github.io/truelift/ |
| Code (GitHub) | https://github.com/YashG1836/truelift |
| Report (IEEE format, PDF) | https://github.com/YashG1836/truelift/blob/main/submission/TrueLift_Report.pdf |
| Presentation (PDF) | https://github.com/YashG1836/truelift/blob/main/submission/TrueLift_Presentation.pdf |
| Demo video (MP4, downloads) | https://github.com/YashG1836/truelift/raw/main/submission/TrueLift_Demo.mp4 |
| Offline demo (zip, runs without internet) | https://github.com/YashG1836/truelift/releases/tag/v2.0.0 |
| Full write-up: method, evidence, limits | https://github.com/YashG1836/truelift/blob/main/docs/method_and_evidence.md |
| Round 1 problem statement | https://github.com/YashG1836/truelift/blob/main/docs/round1_problem_statement.pdf |

## Files in this folder

- [`TrueLift_Report.pdf`](TrueLift_Report.pdf): the end-to-end report in IEEE conference format: the
  problem with its exact money, the system, the method, the evidence, the prototype and the limits.
- [`TrueLift_Presentation.pdf`](TrueLift_Presentation.pdf): 14 slides in the demo's Zomato style.
- [`TrueLift_Presentation.html`](TrueLift_Presentation.html): the same slides for a browser. Download it,
  open it, press F for full screen and the arrow keys to move. It needs no internet.
- [`TrueLift_Demo.mp4`](TrueLift_Demo.mp4): the guided demo, recorded with captions.

## Short description (for submission forms)

Restaurant discounts on Zomato are judged by the orders that use them, not the orders they create.
Since August 2026 a restaurant-funded offer starts only after the owner's OTP, so an owner who cannot
see whether an offer pays will stop approving it. TrueLift adds four calls to Zomato's existing offer
flow: a forecast of the extra orders and profit before the OTP, a serving rule that shows the discount
only to customers it brings in while holding out 1 in 10 as a control group, an itemised payout, and a
weekly measurement with a range and a verdict. In a simulated market of 300 real Bengaluru listings,
218 of 228 TrueLift offers pay for themselves against 130 of 300 blanket offers, restaurants make
₹4.77 lakh a week more than with no offers, and Zomato's commission is higher too. Customers, orders
and money are simulated; restaurant names and listings are real public 2019 data.

## How to present

1. **Live, with the guided demo (recommended).** Open the demo, press **▶ Guided demo** and keep
   pressing →. Ten steps with captions: the restaurant, the forecast, the better version, who sees the
   discount, the OTP approval, week 1, four weeks later, and the market.
2. **Slides.** `TrueLift_Presentation.pdf` (or the `.html` copy) tells the same story with the results.
3. **If the internet fails.** The offline zip from the release opens from a file; the video plays
   anywhere.

Speaker notes, a demo runbook with a failure drill, and thirty likely questions with answers are in
[`docs/pitch/`](../docs/pitch/).

## How these files are made

Nothing here is typed by hand. `python submission/src/build.py` fills every number from `reports/`
through the claims ledger (`docs/claims.yml`) and the generated tables, then builds the report with
Tectonic (`brew install tectonic`) and prints the slides with Google Chrome. Sources:
[`src/report.tex`](src/report.tex), [`src/deck.html`](src/deck.html), [`src/build.py`](src/build.py).
The video is `docs/pitch/demo.mp4`, recorded by `python tasks.py video`.
