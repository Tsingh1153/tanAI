# Finance corpus

Seed knowledge base for tanAI's finance personas. These files are **original,
plain-English reference notes** written for this project — not copied from any
copyrighted source. They cover personal finance, markets & investing, corporate
finance/accounting, and a shared glossary.

They exist so the finance personas have something to ground on via RAG out of the
box. To load them into tanAI, start the backend and run:

```bash
cd backend && source .venv/bin/activate
python ../scripts/seed_corpus.py
```

The script uploads each file as a **global** document (available in every chat),
and is idempotent — re-running skips anything already indexed.

## Making it better

For real depth, add authoritative primary sources yourself (they carry more
weight than these summaries). Good public, freely usable starting points:

- **investor.gov** (U.S. SEC investor education)
- **consumerfinance.gov** (CFPB)
- **irs.gov** (tax rules and current limits)
- **sec.gov / EDGAR** (company filings, for corporate-finance work)
- Federal Reserve and FINRA education portals

Drop PDFs or text into this folder (or upload them in the app) and re-run the
seed script. Prefer official/public-domain material and respect each source's
terms; don't bulk-copy copyrighted articles into the corpus.
