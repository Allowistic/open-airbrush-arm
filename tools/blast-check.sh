#!/usr/bin/env bash
# blast-check.sh — Blast Radius Protocol verification script
# Input:  directory to check (default: current directory); --changed flag for git-diff-only mode
# Output: advisory report of contract violations, orphaned versions, assembly layer issues, missing .desc files
# Must never: modify files, block CI by default, or replace the protocol's structural discipline
#
# Usage:
#   ./tools/blast-check.sh              # check entire project
#   ./tools/blast-check.sh src/         # check specific directory
#   ./tools/blast-check.sh --changed    # check only git-changed files
#   BLAST_STRICT=1 ./tools/blast-check.sh   # exit non-zero when findings exist
#
# This is advisory tooling (Part VII of the whitepaper). It detects mechanical issues:
# contract presence, orphaned version files, assembly layer logic, missing .desc files.
# It cannot check whether contracts are ACCURATE — only whether they EXIST.
# Correctness requires the human/agent verification gate, not this script.

TARGET="${1:-.}"
CHANGED_ONLY=false
[[ "${1:-}" == "--changed" ]] && CHANGED_ONLY=true && TARGET="."
STRICT="${BLAST_STRICT:-0}"
FINDINGS=0

RED='\033[0;31m'
YLW='\033[1;33m'
GRN='\033[0;32m'
CYN='\033[0;36m'
NC='\033[0m'

warn()   { echo -e "${YLW}  ⚠  $*${NC}"; FINDINGS=$((FINDINGS + 1)); }
info()   { echo -e "${CYN}  →  $*${NC}"; }
ok()     { echo -e "${GRN}  ✓  $*${NC}"; }
header() { echo -e "\n${CYN}══ $* ══${NC}"; }

# Collect source files to check
collect_files() {
  local exts=("$@")
  if $CHANGED_ONLY; then
    git diff --name-only HEAD 2>/dev/null | grep -E "\.($(IFS='|'; echo "${exts[*]}"))$" || true
  else
    local find_args=("$TARGET" -not -path "*/node_modules/*" -not -path "*/.git/*" -not -path "*/dist/*" -not -path "*/build/*")
    # Exclude version files themselves from contract checks
    for ext in "${exts[@]}"; do
      find_args+=(-not -name "*.v[0-9].$ext" -not -name "*-v[0-9].$ext")
    done
    local name_args=()
    for ext in "${exts[@]}"; do
      name_args+=(-o -name "*.$ext")
    done
    # Remove leading -o
    find "${find_args[@]}" \( "${name_args[@]:1}" \) 2>/dev/null || true
  fi
}

# ─────────────────────────────────────────────
# CHECK 1: Contract presence
# ─────────────────────────────────────────────
header "Contract Presence"
info "Checking for Input / Output / Must never in first 5 lines (TS/TSX/JS) or first 10 lines (PY)..."

check_contract() {
  local file="$1"
  local lines="$2"
  local head
  head=$(head -"$lines" "$file" 2>/dev/null)
  if ! echo "$head" | grep -q "Input:" || \
     ! echo "$head" | grep -q "Output:" || \
     ! echo "$head" | grep -q "Must never:"; then
    warn "Missing contract: $file"
  fi
}

missing=0
while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  head5=$(head -5 "$f" 2>/dev/null)
  if ! echo "$head5" | grep -q "Input:" || \
     ! echo "$head5" | grep -q "Output:" || \
     ! echo "$head5" | grep -q "Must never:"; then
    warn "Missing contract: $f"
    missing=$((missing + 1))
  fi
done < <(collect_files ts tsx js)

while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  head10=$(head -10 "$f" 2>/dev/null)
  if ! echo "$head10" | grep -q "Input:" || \
     ! echo "$head10" | grep -q "Output:" || \
     ! echo "$head10" | grep -q "Must never:"; then
    warn "Missing contract: $f"
    missing=$((missing + 1))
  fi
done < <(collect_files py)

[[ $missing -eq 0 ]] && ok "All checked files have contracts"

# ─────────────────────────────────────────────
# CHECK 2: Orphaned version files
# ─────────────────────────────────────────────
header "Orphan Detection"
info "Scanning for .v1/.v2/-v1/-v2 version files with no live import..."

orphans=0
while IFS= read -r vfile; do
  [[ -z "$vfile" || ! -f "$vfile" ]] && continue
  # Strip version suffix to get the base name the live file would import
  base=$(basename "$vfile" | sed -E 's/[._-]v[0-9]+\.[^.]+$//' | sed -E 's/\.[^.]+$//')
  hits=$(grep -r --include="*.ts" --include="*.tsx" --include="*.js" \
         --include="*.py" --include="*.sh" \
         -l "$base" "$TARGET" 2>/dev/null | grep -v "$(basename "$vfile")" || true)
  if [[ -z "$hits" ]]; then
    warn "Orphaned version file (no live import found): $vfile"
    orphans=$((orphans + 1))
  fi
done < <(find "$TARGET" \
  -not -path "*/node_modules/*" \
  -not -path "*/.git/*" \
  -not -path "*/dist/*" \
  -not -path "*/build/*" \
  -type f 2>/dev/null \
  | grep -E '[._-]v[0-9]+\.(ts|tsx|js|jsx|py|sh)$' || true)

[[ $orphans -eq 0 ]] && ok "No orphaned version files detected"

# ─────────────────────────────────────────────
# CHECK 3: Assembly layer purity (heuristic)
# ─────────────────────────────────────────────
header "Assembly Layer Purity"
info "Checking App.tsx / *Section.tsx / *Layout.tsx for logic indicators (heuristic)..."

asm_issues=0
while IFS= read -r afile; do
  [[ -f "$afile" ]] || continue
  # Flags: if/switch/for/while/useState/useEffect/useReducer in the file body
  if grep -qE "^\s*(if |switch\(|for\(|while\(|const .* = use(State|Effect|Reducer|Callback|Memo))" "$afile" 2>/dev/null; then
    warn "Possible logic in assembly layer: $afile"
    info "  Review manually — flags: if/switch/for/while/useState/useEffect"
    asm_issues=$((asm_issues + 1))
  fi
done < <(find "$TARGET" \
  -not -path "*/node_modules/*" \
  -not -path "*/.git/*" \
  -not -path "*/dist/*" \
  \( -name "App.tsx" -o -name "*Section.tsx" -o -name "*Layout.tsx" -o -name "*Orchestrator.tsx" \) \
  2>/dev/null || true)

[[ $asm_issues -eq 0 ]] && ok "Assembly files look clean (heuristic — false positives possible)"

# ─────────────────────────────────────────────
# CHECK 4: .desc file coverage
# ─────────────────────────────────────────────
header ".desc File Coverage"

desc_count=$(find "$TARGET" -name "*.desc" \
  -not -path "*/node_modules/*" -not -path "*/.git/*" 2>/dev/null | wc -l | tr -d ' ')

if [[ "$desc_count" -eq 0 ]]; then
  info "No .desc files found — Hologram Pyramid not adopted (or not in scope). Skipping."
else
  info "Found $desc_count .desc file(s). Checking @context pointers and layer completeness..."

  desc_issues=0

  # Check @context pointers resolve
  while IFS= read -r src; do
    [[ -f "$src" ]] || continue
    ref=$(grep "@context:" "$src" 2>/dev/null | head -1 | sed 's/.*@context: *//' | tr -d ' ')
    [[ -z "$ref" ]] && continue
    desc_path="$(dirname "$src")/$ref"
    if [[ ! -f "$desc_path" ]]; then
      warn "Missing .desc file: $desc_path (referenced from $src)"
      desc_issues=$((desc_issues + 1))
    fi
  done < <(grep -r --include="*.ts" --include="*.tsx" --include="*.py" \
    -l "@context:" "$TARGET" 2>/dev/null || true)

  # Check .desc files have required layers
  while IFS= read -r desc; do
    [[ -f "$desc" ]] || continue
    name=$(basename "$desc")
    if echo "$name" | grep -qi "section"; then
      if ! grep -q "^APP:" "$desc" || ! grep -q "^SECTION:" "$desc"; then
        warn "Section .desc missing APP or SECTION layer: $desc"
        desc_issues=$((desc_issues + 1))
      fi
    else
      missing_layers=""
      grep -q "^FEATURE:" "$desc" || missing_layers="FEATURE "
      grep -q "^BLOCK:"   "$desc" || missing_layers="${missing_layers}BLOCK "
      grep -q "^WIRING:"  "$desc" || missing_layers="${missing_layers}WIRING"
      if [[ -n "$missing_layers" ]]; then
        warn "Block .desc missing layers [${missing_layers}]: $desc"
        desc_issues=$((desc_issues + 1))
      fi
    fi
  done < <(find "$TARGET" -name "*.desc" \
    -not -path "*/node_modules/*" -not -path "*/.git/*" 2>/dev/null || true)

  [[ $desc_issues -eq 0 ]] && ok ".desc coverage looks good"
fi

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────
echo ""
echo "────────────────────────────────────────"
if [[ $FINDINGS -eq 0 ]]; then
  echo -e "${GRN}✓ blast-check passed — no findings${NC}"
else
  echo -e "${YLW}⚠ blast-check: $FINDINGS finding(s) above are advisory${NC}"
  echo -e "${CYN}  Findings detect presence issues only — accuracy requires human/agent review.${NC}"
  echo -e "${CYN}  Set BLAST_STRICT=1 to exit non-zero on findings (for CI advisory gates).${NC}"
fi
echo "────────────────────────────────────────"

[[ "$STRICT" == "1" && $FINDINGS -gt 0 ]] && exit 1
exit 0
