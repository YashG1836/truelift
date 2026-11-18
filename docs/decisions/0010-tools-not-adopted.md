# 0010 Tools considered and not adopted

The audit listed tools that would add weight without adding evidence. Each was set aside for a
reason that still holds; any of them could be revisited inside Zomato.

| Tool | Why not here |
|---|---|
| A front-end framework (React and similar) | The page is one HTML file, one script and one stylesheet; a build step would add failure points to a demo that must open from a file |
| Causal-inference libraries (EconML, CausalML) | The learners needed are a few dozen lines on scikit-learn; own code is easier to explain and check, and the libraries' wheels lagged the Python in use |
| Neural uplift models, bandits | No evidence they would beat gradient-boosted trees on tabular order history; bandits change who is held out, which breaks the measurement |
| Pyodide (the model in the browser) | The static demo replays the service's own answers; running the model in the page adds megabytes and a second code path |
| Kafka, Airflow, a feature store, Kubernetes | Zomato already has its own; the blueprint names the events and jobs they would carry |
| WhatsApp Business Platform, Twilio | Sending messages needs accounts and consent flows the prototype cannot own; the page uses click-to-chat links |
| Hugging Face Spaces and similar hosting | The live service runs locally and in Docker (decision with the team); the public link is static |
| Analytics on the public page | A judged page should not track its visitors |
| A chat assistant | It would answer questions the page already answers, with less control over the wording |
| Experiment-tracking services | One pipeline with a metadata block on every report and a reproduce command covers the need |
