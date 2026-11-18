# Decisions

Each record says what was decided, why, and what follows from it. They are the reasons behind the
design; the team's working log of the same decisions is `.claude/context/DECISIONS.md`.

| No. | Decision |
|---|---|
| [0001](0001-owner-keeps-the-discount-size.md) | The owner keeps the discount size; TrueLift chooses who sees it and how |
| [0002](0002-hashed-control-group.md) | One hashed control group, shared by serving and measurement |
| [0003](0003-combined-estimate.md) | The weekly result combines the offer's own control group with the model |
| [0004](0004-simulator-as-primary-evidence.md) | A simulated market with a known truth is the main evidence |
| [0005](0005-static-demo-as-public-link.md) | The public demo is a static copy of the service's answers |
| [0006](0006-learner-choice.md) | Two gradient-boosted models (a T-learner), checked against other learners |
| [0007](0007-ten-percent-holdout.md) | One customer in ten is held out |
| [0008](0008-measurement-defaults.md) | How the weekly measurement computes its noise |
| [0009](0009-percentage-offers-at-their-average-discount.md) | Percentage offers are scored at their average discount per use |
| [0010](0010-tools-not-adopted.md) | Tools considered and not adopted |
