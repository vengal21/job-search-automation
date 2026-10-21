# Personal job dashboard

Double-click `START_JOB_BOT.bat` to start the local dashboard at `http://127.0.0.1:8765/`. It stays bound to this computer.
If an older dashboard is still using that port, the launcher starts the updated version on the next free port in `8765`-`8784`; use the URL printed by the launcher.

## Find and review jobs

1. Choose any indexed date, the last 24 hours, past 3 days, or past 7 days.
2. Click **Search job boards**. The configured search provider searches public listings across job boards and selected company-career pages.
3. Review company, location, fit, and freshness at the original posting; search snippets may be incomplete or stale.
4. Select jobs and click **Start selected jobs**. Gogoi opens one posting at a time in visible Chrome and fills fields it can match to your saved profile. Sign in yourself and answer anything missing.
5. Gogoi stops before **Submit**. Review and submit the form yourself, then click **I submitted — next job** to record the result and continue, or skip the posting.

The shortlist uses title and indexed-snippet terms from `data_folder/plain_text_resume.yaml` and the role preferences. Results are prioritized in this order: product-company Chennai onsite/hybrid, product-company Bengaluru onsite/hybrid, product remote India then worldwide, service-company Chennai, service-company Bengaluru, service remote India then worldwide. Company type is not guessed. It does not fetch full job descriptions or verify location, work eligibility, experience requirements, work mode, or whether a listing remains open. The freshness options are search-provider date filters and are not guaranteed to match the employer's actual posting date.

## Company priority

Listings are ordered by the configured location preference, then by fit. Company type is not guessed. Add verified names to `data_folder/company_classifications.yaml` under `product` or `service` to rank product companies ahead of service companies using the requested location order. Unclassified companies appear after those known groups.

## Source access

The collector uses the search API selected in `src/config.py` and configured in `.env`. Search-provider accounts can have usage limits or fees. The collector searches public index results; it does not scrape logged-in board pages. Search logs are written to `data_folder/output/dashboard_discovery.log`.
