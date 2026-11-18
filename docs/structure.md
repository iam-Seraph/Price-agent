# Repository structure

- `price_agent.py`: backwards-compatible command-line launcher.
- `src/price_agent.py`: agent implementation, mock catalog and offline scenarios.
- `data/price_history.json`: simulated sample price-history summaries.
- `requirements.txt`: dependencies.
- `.env.example`: configuration template; do not commit actual secrets.

## GitHub Codespaces

```bash
python -m pip install -r requirements.txt
python price_agent.py
```

For the optional Groq model run, set a new `GROQ_API_KEY` as a Codespaces secret or in a local ignored `.env` file:

```bash
python price_agent.py --product headphones-a --budget 280
```

The current CLI uses generated temporary history fixtures for its tests. The `data/` JSON file is reference sample data, not yet a live price-history database.
