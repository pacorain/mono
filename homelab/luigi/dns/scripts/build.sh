#!/usr/bin/env bash
# Assemble the luigi DNS config artifact.
#
# Usage: build.sh <output-dir>
#
# Copies the static dnsmasq.d confs, downloads and sanity-checks the
# blocklists listed in blocklists.txt, and writes a VERSION file. The caller
# (CI) is responsible for running `dnsmasq --test` against the result and
# tarring it up.
set -euo pipefail

DNS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:?usage: build.sh <output-dir>}"

# Truncated downloads and upstream error pages must fail the build; a real
# blocklist is far bigger than the floor (hagezi light is ~40k entries) and
# far smaller than the ceiling.
BLOCKLIST_MIN_ENTRIES=20000
BLOCKLIST_MAX_ENTRIES=500000

mkdir -p "$OUT_DIR/dnsmasq.d"
cp "$DNS_DIR"/dnsmasq.d/*.conf "$OUT_DIR/dnsmasq.d/"

fetch() {
  curl -fsSL --retry 3 --retry-delay 2 --max-time 120 -o "$2" "$1"
}

count_and_check() { # <file> <name>
  local entries
  entries=$(wc -l <"$1")
  if [ "$entries" -lt "$BLOCKLIST_MIN_ENTRIES" ] || [ "$entries" -gt "$BLOCKLIST_MAX_ENTRIES" ]; then
    echo "error: blocklist '$2' has $entries entries, outside [$BLOCKLIST_MIN_ENTRIES, $BLOCKLIST_MAX_ENTRIES]" >&2
    return 1
  fi
  echo "$entries"
}

TOTAL_BLOCKED=0
while read -r name format url; do
  case "$name" in ''|'#'*) continue ;; esac

  raw=$(mktemp)
  echo "fetching blocklist '$name' ($format) from $url" >&2
  fetch "$url" "$raw"

  case "$format" in
    dnsmasq)
      # Keep only local=/server=/address= directives; drop comments/blanks.
      # Anything else in the payload means the source changed shape — fail.
      body=$(mktemp)
      grep -v -e '^#' -e '^$' "$raw" > "$body"
      if bad=$(grep -c -E -v '^(local|server|address)=/[^/]+/(0\.0\.0\.0|::|#)?$' "$body") && [ "$bad" -gt 0 ]; then
        echo "error: blocklist '$name' contains $bad unexpected lines, e.g.:" >&2
        grep -E -v -m 3 '^(local|server|address)=/[^/]+/(0\.0\.0\.0|::|#)?$' "$body" >&2
        exit 1
      fi
      entries=$(count_and_check "$body" "$name")
      {
        echo "# Blocklist '$name' fetched from $url"
        echo "# $entries entries"
        cat "$body"
      } > "$OUT_DIR/dnsmasq.d/50-blocklist-$name.conf"
      rm -f "$body"
      ;;
    hosts)
      # Convert a 0.0.0.0-style hosts file into an addn-hosts file plus the
      # conf stub that loads it. conf-dir only picks up *.conf, so the .hosts
      # file rides along in the same directory without being parsed as config.
      hosts=$(mktemp)
      awk '$1 == "0.0.0.0" && $2 != "0.0.0.0" { print "0.0.0.0", $2 }' "$raw" > "$hosts"
      entries=$(count_and_check "$hosts" "$name")
      cp "$hosts" "$OUT_DIR/dnsmasq.d/$name.hosts"
      {
        echo "# Blocklist '$name' fetched from $url"
        echo "# $entries entries"
        echo "addn-hosts=/etc/dnsmasq.d/$name.hosts"
      } > "$OUT_DIR/dnsmasq.d/55-blocklist-$name.conf"
      rm -f "$hosts"
      ;;
    *)
      echo "error: unknown blocklist format '$format' for '$name'" >&2
      exit 1
      ;;
  esac
  rm -f "$raw"
  TOTAL_BLOCKED=$((TOTAL_BLOCKED + entries))
done < "$DNS_DIR/blocklists.txt"

GIT_SHA="${GITHUB_SHA:-$(git -C "$DNS_DIR" rev-parse HEAD 2>/dev/null || echo unknown)}"
# Lives inside dnsmasq.d/ so it survives the directory swap on the node;
# conf-dir only loads *.conf, so dnsmasq ignores it.
{
  echo "git_sha=$GIT_SHA"
  echo "built_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "blocked_domains=$TOTAL_BLOCKED"
} > "$OUT_DIR/dnsmasq.d/VERSION"

LOCAL_RECORDS=$(grep -c -E '^(host-record|address|cname)=' "$OUT_DIR/dnsmasq.d/10-local-records.conf" || true)
echo "build complete: $LOCAL_RECORDS local records, $TOTAL_BLOCKED blocked domains"
