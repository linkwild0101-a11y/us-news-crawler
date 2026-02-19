# Worldmonitor Source Extraction

- Extracted from `worldmonitor` latest `main` branch.
- RSS entries: 318 (full=112, tech=206)
- Railway-proxied RSS entries: 8
- Google News query feeds: 189
- New RSS domains vs `data/sources.json`: 73

## New RSS Domains (Top 30)

| domain | count | sample names |
|---|---:|---|
| `news.google.com` | 189 | AP News, Reuters World, Politico |
| `techcrunch.com` | 5 | TechCrunch Layoffs, TechCrunch, TechCrunch Startups |
| `technologyreview.com` | 4 | MIT Tech Review, MIT Tech Review AI |
| `theverge.com` | 4 | The Verge, The Verge AI |
| `export.arxiv.org` | 3 | ArXiv AI, ArXiv ML |
| `hnrss.org` | 3 | Hacker News, Show HN |
| `rsshub.app` | 3 | NHK World, MIIT (China), MOFCOM (China) |
| `venturebeat.com` | 3 | VentureBeat AI, VentureBeat |
| `feeds.arstechnica.com` | 2 | Ars Technica |
| `ansa.it` | 1 | ANSA |
| `arabnews.com` | 1 | Arab News |
| `asahi.com` | 1 | Asahi Shimbun |
| `cbinsights.com` | 1 | CB Insights |
| `changelog.com` | 1 | Changelog |
| `channelnewsasia.com` | 1 | CNA |
| `cisa.gov` | 1 | CISA |
| `clarin.com` | 1 | Clarín |
| `coindesk.com` | 1 | CoinDesk |
| `crisisgroup.org` | 1 | CrisisWatch |
| `darkreading.com` | 1 | Dark Reading |
| `dev.to` | 1 | Dev.to |
| `devops.com` | 1 | DevOps.com |
| `dn.se` | 1 | Dagens Nyheter |
| `e00-elmundo.uecdn.es` | 1 | El Mundo |
| `eltiempo.com` | 1 | El Tiempo |
| `eluniversal.com.mx` | 1 | El Universal |
| `engadget.com` | 1 | Engadget |
| `feed.infoq.com` | 1 | InfoQ |
| `feeds.capi24.com` | 1 | News24 |
| `feeds.elpais.com` | 1 | El País |

## Signal / Macro API Sources

| endpoint | env keys | upstream domains |
|---|---|---|
| `/api/acled` | ACLED_ACCESS_TOKEN | acleddata.com |
| `/api/acled-conflict` | ACLED_ACCESS_TOKEN | acleddata.com |
| `/api/classify-batch` | GROQ_API_KEY | api.groq.com |
| `/api/classify-event` | GROQ_API_KEY | api.groq.com |
| `/api/climate-anomalies` | - | archive-api.open-meteo.com |
| `/api/cloudflare-outages` | CLOUDFLARE_API_TOKEN | api.cloudflare.com |
| `/api/coingecko` | - | api.coingecko.com |
| `/api/country-intel` | GROQ_API_KEY | api.groq.com |
| `/api/data/military-hex-db` | - | - |
| `/api/earthquakes` | - | earthquake.usgs.gov |
| `/api/eia/[[...path]]` | EIA_API_KEY | api.eia.gov |
| `/api/etf-flows` | - | query1.finance.yahoo.com |
| `/api/faa-status` | - | nasstatus.faa.gov |
| `/api/finnhub` | FINNHUB_API_KEY | finnhub.io |
| `/api/firms-fires` | FIRMS_API_KEY, NASA_FIRMS_API_KEY | firms.modaps.eosdis.nasa.gov |
| `/api/fred-data` | FRED_API_KEY | api.stlouisfed.org |
| `/api/gdelt-doc` | - | api.gdeltproject.org |
| `/api/gdelt-geo` | - | api.gdeltproject.org |
| `/api/hapi` | - | hapi.humdata.org |
| `/api/macro-signals` | - | api.alternative.me, mempool.space, query1.finance.yahoo.com |
| `/api/nga-warnings` | - | msi.nga.mil |
| `/api/og-story` | - | www.w3.org |
| `/api/pizzint/gdelt/batch` | - | www.pizzint.watch |
| `/api/polymarket` | - | gamma-api.polymarket.com |
| `/api/risk-scores` | ACLED_ACCESS_TOKEN | acleddata.com |
| `/api/rss-proxy` | - | - |
| `/api/service-status` | - | azure.status.microsoft, bitbucket.status.atlassian.com, confluence.status.atlassian.com, discordstatus.com |
| `/api/stablecoin-markets` | - | api.coingecko.com |
| `/api/tech-events` | - | collisionconf.com, dev.events, dubai.stepconference.com, websummit.com |
| `/api/ucdp` | - | ucdpapi.pcr.uu.se |
| `/api/ucdp-events` | - | ucdpapi.pcr.uu.se |
| `/api/unhcr-population` | - | api.unhcr.org |
| `/api/worldbank` | - | api.worldbank.org, worldmonitor.app |
| `/api/worldpop-exposure` | - | - |
| `/api/yahoo-finance` | - | query1.finance.yahoo.com |

## Output Files

- `data/worldmonitor_rss_sources.json`
- `data/worldmonitor_rss_new_domains.json`
- `data/worldmonitor_signal_sources.json`
