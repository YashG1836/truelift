# Research with restaurant owners

**Status: not yet conducted.** No interview has taken place. This page holds the method and the
empty tables the findings will go into. Nothing below is a finding until a row is filled from a
written interview note.

## Why

TrueLift rests on a statement about what owners can see: offer reports count the orders that used
an offer, not the orders it added, so owners approve offers without knowing whether they pay. Three
facts in the write-up depend on what owners can show us:

1. Whether Zomato charges commission on the bill before or after the discount. At 15% off, an offer
   breaks even when 32 of every 100 orders using it are extra if commission is on the discounted
   bill, and 45 of 100 if it is on the full bill (`truelift/economics.py`, Money maths page).
2. What an offer report and the OTP approval screen show today.
3. Whether owners read a forecast with a range, and a weekly result, the way we intend.

## Who and where

Six to eight owners or managers of restaurants that take Zomato orders, mixed by size: two outlet
managers of chains, three or four independent restaurants, one or two cloud kitchens or counters.
Gandhinagar (Infocity, Kudasan, Sargasan) and Ahmedabad, starting with outlets the team already
orders from. Visit between 3 pm and 5 pm, when kitchens are quiet. List fifteen outlets to reach
eight (`field_research/target_outlets.md`). Two team members per visit: one asks, one writes.

## The conversation (15 minutes)

| Part | Minutes | What to do |
|---|---|---|
| Consent | 1 | Read the consent script (`field_research/consent_script.md`). Ask before any photo. |
| How they use offers | 4 | Questions 1, 2 and 5 of the question sheet |
| The OTP approval | 2 | Question 3. If the OTP flow has not reached them, note that; it is a finding. |
| Money | 3 | Questions 4 and 6. Ask to see one payout statement with customer details covered. |
| Reading TrueLift | 4 | The comprehension cards, then the demo on a phone, without help at first |
| Close | 1 | Question 7; ask for an introduction to one more owner |

Question sheets: `field_research/question_sheet_en.md`, and drafts in Hindi and Gujarati
(`question_sheet_hi.md`, `question_sheet_gu.md`) that a native speaker should check before use.
The phone runs the offline demo (`python scripts/build_offline.py`, then open
`dist/truelift-offline/index.html`), so a weak network does not matter.

## What to record

- One page per interview, written within the hour (`field_research/note_template.md`): type and
  size of the restaurant, rough weekly Zomato orders, the answers, exact phrases.
- For each comprehension card: read correctly unaided, correctly after one hint, or not understood.
  Alternate the two forecast wordings between owners (card 2A to odd-numbered interviews, 2B to
  even-numbered ones).
- Photos of screens only with permission, with customer names, phone numbers and the restaurant's
  name covered or cropped. Delete raw photos after cropping.

## How to report

Counts, never percentages ("5 of 8 owners"), and never beyond "the owners we met". Restaurants are
described, not named ("40-seat North Indian restaurant, Kudasan"). Quotes are short and
anonymous. A finding that changes the product is listed with the change it caused.

## Findings

Not yet conducted.

| # | Restaurant (described, not named) | Area | Rough Zomato orders a week | Offer report seen | Payout statement seen | Commission base | OTP approval seen |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

| Comprehension item | Read correctly unaided | After one hint | Not understood |
|---|---|---|---|
| Card 1: today's report against TrueLift's weekly result | | | |
| Card 2A: forecast as a range | | | |
| Card 2B: forecast as a chance in ten | | | |
| Card 3: "1 in 10 customers will not see your offer" | | | |

Changes made because of what owners said: none yet.

## A wider, lighter signal

A five-question form (`field_research/short_form.md`) can go to any owners' group an interviewee
is willing to forward it to. It supplements the interviews; with fewer than twenty answers, report
counts only.
