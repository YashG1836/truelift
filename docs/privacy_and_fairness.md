# Privacy and fairness

TrueLift decides which customers see a restaurant's discount. That is a decision about people, so
this page sets out what data it uses, what it never uses, what a restaurant can see, who gets the
discounts and what that costs, and how we read the rules that apply. Everything measured here is
from the simulated market; no real customer data is used anywhere in this repository.

## What the model reads, and what it never reads

The model reads only order and menu-visit history on Zomato, the restaurant's public listing, the
time of the visit and the offer itself. The complete list, each input with its meaning, is
`ALLOWED_FEATURES` in `truelift/model.py`. `tests/test_fairness.py` fails if the model reads anything
outside that list, or if an input's name refers to a protected trait (gender, religion, caste, age
and similar) or to where a customer lives.

It never reads location below the city, device, payment method, contact details, the content of
orders, or anything that stands in for income. This is deliberate: in January 2025 India's consumer
authority questioned ride-hailing apps over prices that appeared to depend on the customer's phone,
and a discount that depends on the phone would raise the same question.

The data serve one purpose: deciding whether a customer sees an offer the restaurant has approved,
and measuring what the offer added. They are not used for prices, credit or anything else.

## What a restaurant sees

An owner sees totals for their own offer: visits, orders, extra orders and profit, with a range.
They never see a customer's identity. While either group in an offer's comparison (shown or held
out) has fewer than 20 customers, the page hides that week's order counts and says why; the
estimate still uses every visit. The rule is `MIN_GROUP_CUSTOMERS` in `truelift/demo.py`, and a test
checks it.

## What customers experience

Customers who are held out, or not chosen for a targeted offer, see the restaurant's normal menu
prices. No one is charged more than the menu price; the decision is only whether a discount
appears. We recommend a short line wherever a targeted offer appears, for example "Offers may vary
by customer and time".

Exposure records (who was shown or held out, and when) are kept for the offer's life plus an audit
period that Zomato's legal team would set; the prototype keeps them only for the demo session.

## Who gets the discounts

Targeting by the extra orders an offer creates has a predictable side effect: regulars, who order
anyway, are offered fewer discounts than occasional customers. The loyalty gap below is how many
more points of their visits non-regulars are offered a saving (a discount or a Brand Pack reward)
than regulars of the same restaurant. Three changes narrow it, each at a cost to restaurants that
the table shows.

<!-- BEGIN:fairness-table -->
| Policy | Regulars offered a saving | Others offered a saving | Loyalty gap (points) | Restaurants' profit from their own offers | Offers that pay |
|---|---|---|---|---|---|
| Today: same discount for everyone | 100% | 100% | 0 | +₹6.94 lakh | 130 |
| TrueLift | 7% | 55% | 48 | +₹7.89 lakh | 218 |
| TrueLift + Brand Pack reward for regulars | 78% | 55% | −24 | +₹7.89 lakh | 218 |
| TrueLift, regulars always eligible | 78% | 55% | −23 | +₹6.98 lakh | 163 |
| TrueLift + a random 20% of others shown | 21% | 59% | 38 | +₹7.65 lakh | 198 |
<!-- END:fairness-table -->

A Brand Pack reward for regulars, measured with its own control group, closes the gap (regulars are
then offered a saving more often than others) at almost no cost to the restaurants' own-offer
profit, which is why the create screen offers it. Making regulars always eligible for the discount
closes the gap too, but gives back much of what targeting gained: the discount goes again to orders
that would have come anyway. Showing the offer to a random fifth of the others costs a little and
keeps everyone within reach of a discount. The choice belongs to the owner and to Zomato; the full report, by customer
segment, locality and price band, is `fairness` in `reports/evaluation.json` and on the Evidence page.

## The rules, as we read them

This is our reading, not legal advice; Zomato's legal team would review each point.

| Rule | What it asks, as we read it | What TrueLift does |
|---|---|---|
| Digital Personal Data Protection Act 2023 and its Rules (notified in November 2025; according to published summaries, the main notice and consent duties apply from May 2027) | Personal data used for a stated purpose, with notice; data minimisation | Uses only order and visit history Zomato already holds, for one stated purpose; reads no device, payment or location data |
| Consumer Protection (E-Commerce) Rules 2020 | No manipulation of prices or of the order of search results that misleads consumers | Never changes a menu price or a listing's position; a customer either sees the restaurant's approved discount or the normal price |
| Guidelines on dark patterns (consumer authority, 2023) | No false urgency, no hidden costs, no "drip pricing" | No countdowns or hidden charges; the discount shown is the discount applied |
| The consumer authority's January 2025 questions on differential pricing | Prices should not depend on the customer's device | The model has no device or payment input, and a test enforces it |

What we do not know: how Zomato's consent text covers personalised offers today, and whether
holding a customer out of one restaurant's discount needs its own notice. Both are questions for
Eternal.

## Security

The prototype's security measures (checksummed model loading, per-visitor sessions, OTP expiry and
attempt limits, a hash-chained consent ledger, security headers, problem-detail errors without
stack traces, a non-root container) are listed in `SECURITY.md`.
