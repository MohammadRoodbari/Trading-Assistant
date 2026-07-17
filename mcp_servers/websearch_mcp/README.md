# MCP SearXNG Enhanced

An MCP server that gives AI agents (Claude, and any other MCP client) private, self-hosted web search and page scraping through your own [SearXNG](https://docs.searxng.org/) instance — no third-party search API, no API keys, no per-query billing.

Based on [OvertliDS/mcp-searxng-enhanced](https://github.com/OvertliDS/mcp-searxng-enhanced).

## Features

- **Web search** over your SearXNG instance, with results for web, images, video, files, maps, and social — each with its own configurable result cap.
- **Page scraping** — fetch a URL and get cleaned, extracted page content (via Trafilatura), word-limited so it stays chat-friendly.
- **Current date/time** tool, timezone-aware.
- **Citations** — search results can carry citation links back to their sources.
- **Caching & rate limiting** built in, so repeated lookups and scraping stay fast and don't hammer the same domain.
- **Site ignore list** to exclude specific domains from results.
- Runs as a normal MCP server (stdio) or as an HTTP server.

## Tools & Aliases

| Tool | Purpose | Aliases |
|---|---|---|
| `search_web` | Web search via SearXNG | `search`, `web_search`, `find`, `lookup_web`, `search_online`, `access_internet`, `lookup`* |
| `get_website` | Scrape website content | `fetch_url`, `scrape_page`, `get`, `load_website`, `lookup`* |
| `get_current_datetime` | Current date/time | `current_time`, `get_time`, `current_date` |

*`lookup` is context-sensitive: called with a `url` argument it maps to `get_website`, otherwise it maps to `search_web`.

## Requirements

- A running [SearXNG](https://github.com/searxng/searxng) instance reachable from wherever this server runs.
- Docker (recommended) or Python, to run the MCP server itself.

## Environment Variables

Set these in your MCP client's config, or when running the Docker container manually.

| Variable | Description | Default | Notes |
|---|---|---|---|
| `SEARXNG_ENGINE_API_BASE_URL` | SearXNG search endpoint | `http://host.docker.internal:8080/search` | Crucial for server operation |
| `MCP_HTTP_HOST` | Bind address for HTTP server mode | `0.0.0.0` | Only used with `--http` |
| `MCP_HTTP_PORT` | Port for HTTP server mode | `8000` | Only used with `--http` |
| `DESIRED_TIMEZONE` | Timezone for the date/time tool | `America/New_York` | e.g. `America/Los_Angeles` — see [tz database list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) |
| `ODS_CONFIG_PATH` | Path to persistent config file | `/config/ods_config.json` | Typically left as default in-container |
| `RETURNED_SCRAPPED_PAGES_NO` | Max pages returned per search | `3` | |
| `SCRAPPED_PAGES_NO` | Max pages attempted per search | `5` | |
| `PAGE_CONTENT_WORDS_LIMIT` | Max words per scraped page | `5000` | |
| `CITATION_LINKS` | Enable/disable citation events | `True` | `True` or `False` |
| `MAX_IMAGE_RESULTS` | Max image results | `10` | |
| `MAX_VIDEO_RESULTS` | Max video results | `10` | |
| `MAX_FILE_RESULTS` | Max file results | `5` | |
| `MAX_MAP_RESULTS` | Max map results | `5` | |
| `MAX_SOCIAL_RESULTS` | Max social media results | `5` | |
| `TRAFILATURA_TIMEOUT` | Content extraction timeout (s) | `15` | |
| `SCRAPING_TIMEOUT` | HTTP request timeout (s) | `20` | |
| `CACHE_MAXSIZE` | Max cached websites | `100` | |
| `CACHE_TTL_MINUTES` | Cache time-to-live (min) | `5` | |
| `CACHE_MAX_AGE_MINUTES` | Max age for cached content (min) | `30` | |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | Max requests per domain per minute | `10` | |
| `RATE_LIMIT_TIMEOUT_SECONDS` | Rate limit tracking window (s) | `60` | |
| `IGNORED_WEBSITES` | Comma-separated sites to ignore | `""` (empty) | e.g. `"example.com,another.org"` |

## License

See the [repository](https://github.com/OvertliDS/mcp-searxng-enhanced) for license details.
