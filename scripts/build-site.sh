#!/usr/bin/env bash
#
# build-site.sh — assemble the GitHub Pages publication tree into _site/.
#
# Published layout (https://observability.getamazednow.ai/):
#
#   /                     product page          <- index.html
#   /demo/                demo dashboard        <- dashboard/
#   /dashboard/           redirect -> /demo/    (back-compat for older links)
#   /training/diagrams/   architecture diagrams referenced by the product page
#   /CNAME                custom domain
#   /404.html             branded not-found page
#
# The repo keeps `dashboard/` as its source folder name — 30+ references across
# the README, docs, training material and Python generators depend on it. Only
# the *published* copy is exposed as /demo/.
#
# Local preview:
#   ./scripts/build-site.sh && python3 -m http.server 8080 --directory _site
#   (a real HTTP server is required — the dashboard fetches JSON, which
#    browsers block over file://)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$REPO_ROOT/_site}"
DOMAIN="observability.getamazednow.ai"

cd "$REPO_ROOT"

rm -rf "$OUT"
mkdir -p "$OUT"

# 1. Product page -> site root
cp index.html "$OUT/index.html"

# 2. Demo dashboard -> /demo/
mkdir -p "$OUT/demo"
cp -R dashboard/. "$OUT/demo/"
find "$OUT" -name ".DS_Store" -delete

# 3. Diagrams referenced by the product page
mkdir -p "$OUT/training/diagrams/exports"
cp training/diagrams/exports/*.png "$OUT/training/diagrams/exports/"

# 4. Back-compat redirect: /dashboard/ -> /demo/
mkdir -p "$OUT/dashboard"
cat > "$OUT/dashboard/index.html" <<'HTML'
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Redirecting to /demo/</title>
<link rel="canonical" href="/demo/" />
<meta http-equiv="refresh" content="0; url=/demo/" />
<script>window.location.replace("/demo/" + window.location.search + window.location.hash);</script>
</head>
<body>
<p>This page has moved to <a href="/demo/">/demo/</a>.</p>
</body>
</html>
HTML

# 5. Custom domain. Pages stores this server-side, but including it in the
#    artifact prevents the domain being dropped on a deploy.
printf '%s\n' "$DOMAIN" > "$OUT/CNAME"

# 6. 404 page -> nudge visitors back to the two real entry points
cat > "$OUT/404.html" <<'HTML'
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Not found — GenAI Observability</title>
<link rel="icon" type="image/svg+xml" href="/demo/assets/Getamazednow-AI-Favicon.svg" />
<style>
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif; background:#0B1220; color:#E6ECF5; }
  .wrap { text-align:center; padding:2rem; }
  h1 { font-size:3rem; margin:0 0 .5rem; font-weight:700; }
  p { color:#93A4BF; margin:0 0 1.75rem; }
  a { display:inline-block; margin:0 .35rem; padding:.7rem 1.3rem; border-radius:8px;
      text-decoration:none; font-weight:600; background:#3B82F6; color:#fff; }
  a.ghost { background:transparent; border:1px solid #33415C; color:#E6ECF5; }
</style>
</head>
<body>
  <div class="wrap">
    <h1>404</h1>
    <p>That page doesn&rsquo;t exist.</p>
    <a href="/">Product overview</a>
    <a class="ghost" href="/demo/">Demo dashboard</a>
  </div>
</body>
</html>
HTML

echo "Built $OUT"
find "$OUT" -maxdepth 2 -mindepth 1 | sed "s|$OUT|  _site|" | sort
