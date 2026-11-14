# Simulator datasheet

The simulated market exists because no public dataset has restaurant offers with rupee outcomes and a
control group. It lets every estimate be checked against a known truth. It does not stand in for
Zomato's data: each assumption below says what would replace it. Code: `truelift/sim.py` (`Config`),
`truelift/economics.py` (`Terms`).

## Restaurants and customers

| Parameter | Value | Basis | Replaced by, inside Zomato |
|---|---|---|---|
| Restaurants | 300 real Bengaluru listings, 50 in each of six localities | Public 2019 Kaggle "Zomato Bangalore Restaurants": name, locality, cuisines, cost for two, rating, votes only | The live restaurant catalogue |
| Average order value | 0.7 x the listed cost for two, kept between ₹150 and ₹1,000 | Assumption; gives a market average near ₹460 | Actual order values |
| Customers | 5,000 per locality (30,000) | Size chosen so a run takes minutes | Real customers |
| Customer types (loyal, casual, deal-seeker, infrequent) | 25%, 40%, 20%, 15% | Assumption, varied in the sensitivity sweep (deal-seekers 10% to 35%) | Not needed: the model uses order history, not types |
| Ordering occasions a week by type | 2.0, 0.9, 1.0, 0.5 | Assumption | Session logs |
| Price sensitivity (utility per ₹100 saved) by type | 0.45, 1.2, 2.6, 1.6 | Calibrated so that about a third of the orders using a blanket ₹60 offer are truly extra; varied ±30% | Estimated from the shadow phase's random designs |
| Favourite-restaurant bonus by type | 2.8, 1.4, 0.3, 0.0 | Assumption: loyal customers return to a favourite | Order history |
| Swiggy as an alternative | Base utility by type; typical saving ₹40 | Assumption; varied ₹0 to ₹80 | Competitive data Zomato holds |
| Menus opened per ordering occasion | 8 | Assumption; Eternal's Q2 FY27 letter says users browse about 12 menus; varied 5 to 12 | Session logs |
| Value of topping up to a minimum order | 0.5 of the top-up | Hidden truth the method must learn; learned back as 0.50 | Learned from past minimum-order offers |
| Time slots (lunch, 3-6 pm, dinner) | 35%, 15%, 50% of occasions | Assumption | Session logs |
| Customers new to Zomato in the evaluation period | 8% | Assumption | Account creation dates |

## Money

| Parameter | Value | Basis |
|---|---|---|
| Commission | 25% of the bill after the discount (before-discount case also run) | Typical published partner terms; the base is a question for Eternal |
| GST on commission | 18% | Indian GST on services |
| Food and packaging cost | 37% of the menu price | Assumption; varied 30% to 45% |
| Zomato contribution | 8.5% of the bill minus any discount Zomato funds | Assumption for the platform's margin before fixed costs |

## What the simulator leaves out

Swiggy does not react to TrueLift; restaurants have no Swiggy-side offers; kitchens never run out of
capacity; delivery fees, platform coupons stacking with restaurant offers, Zomato Gold and ratings
feedback are not modelled; a customer's habits do not change because of last week's discount (no
habit formation, no learning to wait for a deal). These are the first things a pilot on real data
would measure.

## Checks that it is internally consistent

`tests/test_simulator.py` checks that probabilities are valid, that a world with no offers has no
effect, that the control-group hash is the one serving uses, that features use only the history before
each week, and that the fast history used by the service is identical to the full one.
