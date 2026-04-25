You are an expert Python + Flask engineer. Build this project from scratch as a uv-based Python app.

Project goal:
- Parse Re:Zero web novel translations from https://witchculttranslation.com/table-of-content/
- Save chapters as Markdown (preserving formatting like bold/italic)
- Keep data incremental (download only new/changed entries)
- Provide a Flask + Jinja reading UI with saved progress

Tech and architecture requirements (must follow):
1) Use uv project layout and Python 3.14+
2) Split project into 2 parts:
   - parser layer (HTTP, TOC parsing, chapter parsing, markdown writing, incremental state)
   - web UI layer (Flask app + Jinja templates + static assets)
3) Store generated outputs under a gitignored data directory
4) Web app must be Flask (not FastAPI, not React-only frontend)

Critical caveats (must not ignore):
1) DO NOT assume TOC is hierarchical with nested Arc blocks.
2) Real TOC must be parsed by scanning top-to-bottom inside:
   - article#post-35 .entry-content
3) Parsing state machine logic:
   - When h1 starts with "Arc N", set current_arc = that heading, reset current_phase
   - When h1 starts with "Phase ...", set current_phase = that heading
   - For each ul encountered while current_arc is set, parse chapter links from li > a
4) Include external links too (Arc 2 may point to external domains, not only witchculttranslation.com)
5) Do not dedupe chapters by URL only:
   - Multiple distinct entries can share same URL (example: Arc 3 interludes PDF)
   - Identity key must include at least: canonical_url + arc + phase + chapter_title
6) Stop parsing when clearly outside Arc content (for example "Side Content" section)
7) Never “guess” arc/chapter structure from URL patterns alone; HTML stream context is source of truth.

Implementation details:
1) Parser
   - Fetch TOC URL with retry/backoff, polite User-Agent, timeout
   - Parse TOC entries with fields:
     - title
     - url
     - arc
     - phase (nullable)
     - chapter
     - order
   - Fetch chapter page/content and convert to markdown preserving formatting (bold/italic/lists/headings/links)
   - Save markdown per chapter with front matter:
     - title, source_url, arc, phase, chapter, order, fetched_at, content_hash
   - Save files in gitignored data dir, arc-based folders
   - Maintain state + manifest JSON for incremental sync
   - Incremental policy:
     - new entry key => download/write
     - known key + same hash => skip
     - known key + changed hash => update
2) Web UI (Flask + Jinja)
   - Routes:
     - /library
     - /read/<chapter_path>
     - /read/<chapter_path>/toc (separate TOC page; no left sidebar TOC)
     - /api/progress (save reading progress)
   - Reader UX requirements:
     - width-limited content column
     - serif font
     - black/dark background
     - previous button on left, next button on right (top and bottom)
     - contents button linking to separate TOC page
     - internal heading links from TOC page into chapter anchors
   - Progress persistence:
     - server-side SQLite in data directory
     - restore scroll position on reload
3) CLI
   - sync command (full and filtered, e.g. --arc 1)
   - status command
   - serve command
4) Configuration and docs
   - update pyproject dependencies
   - document setup/run in README
   - keep data dir in .gitignore

Working techniques you must use:
1) Start with source-grounding:
   - fetch and inspect real TOC HTML before coding parser logic
   - use curl to get the real html of pages to implement parser in a way that's tailored to actual structure, not semantical guessing
2) Build parser as deterministic state machine over DOM stream
3) Add debug/inspection command:
   - print arc -> phase -> chapter counts from TOC without downloading chapters
4) Validate with fixture tests + live smoke checks
5) Validate incremental behavior with repeated sync runs
6) Avoid broad regex-only approaches for structural parsing

Quality/robustness requirements:
1) Strong error handling:
   - network retries
   - continue on chapter-level failures
   - summarize new/updated/skipped/errors
2) Stable file naming with slugification
3) Canonicalize URLs for consistency
4) Keep parser logic independent from UI layer

Acceptance criteria:
1) Arc 2 is present after full TOC parse/sync
2) Arc 3 chapter count matches live TOC entries (including distinct same-URL interludes)
3) Running sync twice does not re-download unchanged chapters
4) Markdown files include preserved emphasis formatting (bold/italic) and valid front matter
5) Reader works end-to-end:
   - chapter page loads
   - separate TOC page loads and links to anchors
   - prev/next placement is logical
   - progress saves/restores
6) All generated outputs are inside gitignored data directory

Deliverables:
1) Full code implementation
2) Updated README with exact run commands
3) Short verification report showing:
   - TOC arc/phase counts
   - Arc 2/Arc 3 sample results
   - incremental sync result from two consecutive runs
   - reader route checks

Now implement everything end-to-end without placeholder code.