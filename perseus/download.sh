#!/bin/bash
set -euo pipefail

BASE_URL="https://www.perseus.tufts.edu/hopper/opensource/downloads/data"
DEST="$(dirname "$0")/dumps"

mkdir -p "$DEST"

FILES=(
    "hib_artifact_keywords.tar.gz"
    "hib_artifacts.tar.gz"
    "hib_atomic_artifacts.tar.gz"
    "hib_building_artifacts.tar.gz"
    "hib_chunks.tar.gz"
    "hib_citations.tar.gz"
    "hib_coin_artifacts.tar.gz"
    "hib_date_ranges.tar.gz"
    "hib_dates.tar.gz"
    "hib_entities.tar.gz"
    "hib_entity_occurrences.tar.gz"
    "hib_frequencies.tar.gz"
    "hib_gem_artifacts.tar.gz"
    "hib_image_names.tar.gz"
    "hib_images.tar.gz"
    "hib_lang_abbrevs.tar.gz"
    "hib_languages.tar.gz"
    "hib_lemmas.tar.gz"
    "hib_parses.tar.gz"
    "hib_person_names.tar.gz"
    "hib_places.tar.gz"
    "hib_sculpture_artifacts.tar.gz"
    "hib_site_artifacts.tar.gz"
    "hib_toc_chunks.tar.gz"
    "hib_tocs.tar.gz"
    "hib_vase_artifacts.tar.gz"
    "hib_word_counts.tar.gz"
    "metadata.tar.gz"
    "morph_frequencies.tar.gz"
    "morph_votes.tar.gz"
    "prior_frequencies.tar.gz"
    "senses.tar.gz"
    "sense_votes.tar.gz"
)

download() {
    local file="$1"
    local url="$BASE_URL/$file"
    local dest="$DEST/$file"
    local max_attempts=20

    for attempt in $(seq 1 "$max_attempts"); do
        local current_size=0
        [ -f "$dest" ] && current_size=$(stat -c%s "$dest")

        # Try wget with continue, or curl with resume
        if command -v wget &>/dev/null; then
            wget -c -q --timeout=30 --tries=1 "$url" -O "$dest" 2>/dev/null && \
                [ "$(stat -c%s "$dest")" -gt "$current_size" ] && return 0
        else
            curl -sL -C - -o "$dest" "$url" 2>/dev/null && \
                [ "$(stat -c%s "$dest")" -gt "$current_size" ] && return 0
        fi

        # If no progress and file exists, server may be done or stuck
        if [ -f "$dest" ] && [ "$(stat -c%s "$dest")" -eq "$current_size" ] && [ "$current_size" -gt 0 ]; then
            # Try fresh download (no resume) to see if server sends more
            rm -f "$dest"
            if command -v wget &>/dev/null; then
                wget -q --timeout=30 --tries=1 "$url" -O "$dest" 2>/dev/null
            else
                curl -sL -o "$dest" "$url" 2>/dev/null
            fi
        fi

        sleep 2
    done

    return 1
}

echo "=== Perseus MySQL Dump Downloader ==="
echo "Source: $BASE_URL"
echo "Destination: $DEST"
echo "Files: ${#FILES[@]}"
echo ""

ok=0
fail=0

for file in "${FILES[@]}"; do
    echo -n "Downloading $file ... "
    if download "$file"; then
        size=$(stat -c%s "$DEST/$file" 2>/dev/null)
        echo "OK ($size bytes)"
        ok=$((ok + 1))
    else
        size=$(stat -c%s "$DEST/$file" 2>/dev/null || echo 0)
        echo "INCOMPLETE ($size bytes)"
        fail=$((fail + 1))
    fi
    sleep 1
done

echo ""
echo "=== Summary ==="
echo "Downloaded: $ok"
echo "Incomplete: $fail"
echo "Total: ${#FILES[@]}"
