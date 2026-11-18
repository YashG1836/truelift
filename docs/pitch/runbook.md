# Demo runbook

How to give the talk and the live demo so that nothing in the room can stop it. The slides are
`TrueLift_deck.pdf` (source `deck.html`, notes in `speaker_notes.md`); the questions are in
`questions.md`. Customers, orders and profits in the demo are simulated on real 2019 listings;
say so once, early.

## Roles

One person drives the laptop and never speaks during the demo; one person speaks and never
touches the laptop. The third answers questions on the method and keeps time.

## Thirty minutes before

1. Get the offline bundle: download `truelift-offline.zip` from the
   [v2.0.0 release](https://github.com/YashG1836/truelift/releases/tag/v2.0.0) and unzip it into `dist/`
   (or build it). Start it with `python dist/truelift-offline/serve.py`, or open
   `dist/truelift-offline/index.html` directly.
   It needs no internet: every answer was computed by the service and saved.
2. Open three browser tabs: the offline demo, the deck PDF, and the public demo
   (`https://yashg1836.github.io/truelift/`) as a spare.
3. Set the projector to its real resolution and check the demo at 1024 × 768: the page must not
   scroll sideways.
4. Have the recording (`demo.mp4`, built by `python scripts/make_video.py`) ready in a fourth tab.
5. Phones: two team phones with the public demo open, in case the laptop fails.
6. Close notifications, set the laptop to stay awake, and plug it in.

## The three minutes of demo

Use the manual flow below for a live audience, and the **▶ Guided demo** (ten captioned steps,
arrow keys move) when the room is noisy or time is short. Say what happened, not only what was
forecast.

| Time | The driver does | The speaker says (in substance) |
|---|---|---|
| 0:00 | Home screen of the demo restaurant | "A real listing; its customers and orders are simulated. The owner runs ₹60 off for everyone." |
| 0:15 | **Create an offer** (the usual offer is preset) | "Before the OTP, TrueLift forecasts what the offer adds. Most orders using it would come anyway." Point at the share that would come anyway and the range. |
| 0:45 | **Use this version** | "Same discount size, a better version: who sees it, minimum order, time, Brand Pack. It shows its range too, because the best of many forecasts flatters itself." |
| 1:05 | Scroll to **Inside Zomato** | "A regular who orders anyway does not get the discount; a lapsed customer does; one customer in ten is held out, so we can measure." |
| 1:25 | **Continue to approve**, enter the OTP shown | "The owner approves exactly this, for four weeks, and sees who pays. The consent record stores the forecast they saw." |
| 1:45 | **Simulate the first week**, then three more weeks | "Today's report shows the orders that used the offer. The held-out customers show how many were extra. The range narrows every week." |
| 2:20 | **Show me how you know**, then **Send to my WhatsApp** | "This is the owner's weekly message: extra profit with a range, and a clear verdict." |
| 2:40 | **Renew this offer** | "Renewal needs a new OTP, and now the owner sees what was measured." |
| 2:55 | Evidence tab | "Across 300 simulated restaurants: the next two slides." |

If a week's true value falls outside its range, say so plainly: the ranges are built to miss
about one time in five.

## When something fails

| What fails | What to do | Why it works |
|---|---|---|
| Wi-Fi or venue network | Stay on the offline bundle | It reads only local files |
| The laptop's server will not start | Open `dist/truelift-offline/index.html` from the file system | The bundle works from a file, with no server |
| The laptop dies or the projector will not connect | Speak from the PDF on a second laptop; judges use their phones (QR code on slides 1, 6 and 12) | The public demo needs nothing from us |
| A wrong OTP is typed | Read the error, retype the code shown on screen | The OTP screen allows retries and explains the error |
| The page looks wrong at the projector's resolution | Zoom out one step (Ctrl and minus) | The layout is tested at 390 px phone width and on desktop |
| Anything else in the demo | Play the recording from the right point | It shows the same flow with captions |
| A question needs a design the static demo does not have | Offer to show it after the talk on the live service (`python tasks.py serve`) | The live service answers any design |

## Timing

The full talk with a three-minute demo is about ten minutes; `speaker_notes.md`
gives seconds per slide. The five-minute cut is slides 1, 3, 6, 7, 8 and 12: the problem in one
order, the demo, what it does for restaurants and for Zomato, and the ask. If time is unknown,
prepare both and decide at the door.

## Rehearsals

| Run | Purpose | Passes when |
|---|---|---|
| 1 | Timing | The talk ends 30 seconds inside the limit, twice in a row |
| 2 | Failure drill: Wi-Fi off, server down, wrong OTP, projector at 1024 × 768 | The demo completes every time |
| 3 | Hostile questions from someone outside the team, drawn at random from `questions.md` | No answer runs over 30 seconds and no number is given as "I think" |

After the talk, someone outside the team should be able to repeat three things: 32 extra orders
in 100 is the break-even for ₹60 off a ₹400 order; most TrueLift offers pay while most blanket
offers do not; Zomato's commission does not fall.

## Ninety seconds with the audience's phones

If the room allows it, hand the demo to the panel before showing anything:

> "Before we show you anything, scan this code. You own the restaurant on the screen. Tap
> **Create an offer**: that is your usual ₹60 off. Look at the forecast: most of the orders that
> would use it were coming anyway. Tap **Use this version**. Tap **Continue to approve** and type
> the OTP shown on the screen. Now tap **Simulate the first week**, and the next weeks after it.
> At the bottom, tap **Send to my WhatsApp**. That message is what the owner gets every week."

Rehearse it with three people who have never seen the project; note where each one hesitates.
If phones are not allowed or the room is large, run the same flow on the projector and leave the
code on the slide for afterwards.
