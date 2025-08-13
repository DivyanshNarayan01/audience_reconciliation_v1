# Attendee ↔ Company Reconciliation

Map event **attendees** to a **master company list** with clear rules, country scoping, and **Gemini AI assistance** for complex cases. Output is auditable with confidence scores and detailed `logic_used` tracking.

---

## 🎯 Why this repo?
- **Deterministic first pass**: Exact matching + historical lookups
- **AI-powered fallback**: Gemini AI for typos, abbreviations, and complex cases  
- **Full transparency**: Every match shows exactly which method was used
- **Country-scoped matching**: Always matches on (company + country)
- **High success rate**: 90%+ matching with AI assistance

## ✨ Key Features
- **40+ test cases** covering basic typos to complex abbreviations
- **Real-time Gemini integration** with intelligent prompting
- **Improved normalization** for better fuzzy matching
- **Transparent auditing** showing AI suggestions even for failed cases

---

## Data contracts

**master_company_list**
- `company_name` (STRING)
- `parent_company_name` (STRING)
- `company_country` (ISO-2 recommended, e.g., `GB`, `US`)

**attendee_list**
- `attendee_email_address` (STRING)
- `attendee_company_name` (STRING, free text)
- `attendee_country` (ISO-2)

**historical_reconciliation**
- `attendee_email_address` (STRING)
- `company_name` (STRING, canonical at the time)
- `attendee_country` (ISO-2)

> All matching is **country-scoped**.

---

## What you get

A single table/view with 100% match rate on current test data:

| column | example |
|---|---|
| `attendee_email_address` | `typo4@amazn.com` |
| `attendee_company_name` | `Amazn` |
| `attendee_country` | `US` |
| `company_name` | `Amazon.com Inc.` |
| `parent_company_name` | `Amazon.com Inc.` |
| `company_country` | `US` |
| `match_confidence` | `94` |
| `logic_used` | `R4_gemini_exact_match` |

**Current test results**: 40/40 matches (0 unresolved cases)

---

## Matching rules (in order)

All rules require **same country**.

1. **R1: Exact company + country**  
   Normalize names; exact match to `company_name`.  
   → `R1_exact_company_country` (confidence 100)

2. **R2: Exact parent + country**  
   Normalize names; exact match to `parent_company_name`.  
   → `R2_exact_parent_country` (95)

3. **R3: Historical / domain (country-scoped)**  
   - **R3a**: historical by **email** → `company_name` → master (92)  
   - **R3b**: historical by **domain** (majority/most-recent) → master  
     → `R3b_hist_domain_company` (90) or `R3b_hist_domain_parent` (88)

4. **R4: Gemini AI-assisted matching** (only unresolved rows)  
   - Use Gemini AI to suggest the best match from the exact master company list
   - Show complete database context to Gemini for accurate suggestions
   - **R4**: Gemini suggestion → exact match in master list (same country) → `R4_gemini_exact_match` (94)
   - For unresolved cases, show Gemini suggestions in `logic_used` field for transparency
   - Never accept AI outputs without **master-list exact validation**

Unmatched → `UNRESOLVED` (0).

---

## Quick start

### Install
```bash
pip install -r requirements.txt
# or minimal (CSV version):
pip install pandas rapidfuzz pyarrow tldextract pyyaml python-dotenv google-generativeai
```

### Configure

**Environment variables** (`.env`):
```bash
# Copy .env.example to .env and add your API keys
cp .env.example .env
# Edit .env with your actual API keys
GEMINI_API_KEY=your_actual_key_here
```

**Settings** (`.config`):
```yaml
data_source: csv
data_dir: data
output_dir: output
files:
  attendees: attendee_list.csv
  master: master_company_list.csv
  history: historical_reconciliation.csv
output_files:
  final_results: reconciliation_results.csv
  unresolved: unresolved_cases.csv
  audit_log: matching_audit.csv
thresholds:
  fuzzy_company: 92
  fuzzy_parent: 90
confidence_caps:
  r4_company: 94
  r4_parent: 92
llm:
  provider: gemini    # or "disabled"
  max_candidates: 10
privacy:
  send_email_full: false  # only send root domain externally
```

### Run
```bash
python reconcile.py
```

**Process:**
1) **Normalize** names/domains/countries (Python with pandas).  
2) Run **R1–R3** matching logic on CSV data to create `deterministic_matches`.  
3) Extract **unresolved** cases.  
4) Run **Rule 4**: get top-10 variations, validate to master, apply parent-of-attendee fallback.  
5) **Combine** results → export final CSV.  
6) Review low-confidence (e.g., <90) and write outcomes to alias tables.

---

## Data normalization helpers (Python)
```python
import re

def norm_name(s):
    """Normalize company name by removing legal suffixes and special chars"""
    if not s:
        return ''
    s = s.lower()
    s = re.sub(r'[^a-z0-9 ]', '', s)
    s = re.sub(r'\b(ltd|limited|plc|inc|llc|llp|pvt|private|co|company|corp|corporation|gmbh|sarl|sa|bv|oy|ab|as|sas|spa|ag|nv|bvba|oyj|pte|kft|aps|sro|sp zoo)\b', '', s)
    return re.sub(r'\s+', ' ', s.strip())
```

---

## Mini examples (input → output)

All examples are **country-scoped** and use normalized names.

### R1 — Exact company + country
**attendee**: `alex.jones@microsoft.com`, `Microsoft Ltd`, `GB`  
**master**: (`Microsoft`, parent=`Microsoft Corporation`, `GB`)  
**→ output**: `company_name=Microsoft`, confidence **100**, `logic_used=R1_exact_company_country`

---

### R2 — Exact parent + country
**attendee**: `priya.k@pwc.com`, `PricewaterhouseCoopers`, `GB`  
**master**: (`PricewaterhouseCoopers LLP`, parent=`PricewaterhouseCoopers International Limited`, `GB`)  
**→ output**: `company_name=PricewaterhouseCoopers LLP`, confidence **95**, `logic_used=R2_exact_parent_country`

---

### R3a — Historical by email + country
**attendee**: `jane.doe@acme.co.uk`, `ACME (UK)`, `GB`  
**history**: `jane.doe@acme.co.uk` → `Acme Ltd` (GB)  
**master**: (`Acme Ltd`, parent=`Acme Group plc`, `GB`)  
**→ output**: `company_name=Acme Ltd`, confidence **92**, `logic_used=R3a_hist_email_exact`

---

### R3b — Historical by domain + country
**attendee**: `sam.t@pwc.com`, `PwC`, `GB`  
**history**: `pwc.com` in GB → majority `PricewaterhouseCoopers LLP`  
**master**: (`PricewaterhouseCoopers LLP`, parent=`PricewaterhouseCoopers International Limited`, `GB`)  
**→ output**: `company_name=PricewaterhouseCoopers LLP`, confidence **90**, `logic_used=R3b_hist_domain_company`

---

### R4 — Gemini AI-assisted matching
**attendee**: `typo4@amazn.com`, `Amazn`, `US` (R1–R3 failed)  
**Gemini context**: Shows complete US company list from master database  
**Gemini suggestion**: `Amazon.com Inc.` (confidence assessment)  
**validation**: Exact match found in master list for `Amazon.com Inc.` (US)  
**→ output**: `company_name=Amazon.com Inc.`, confidence **94**, `logic_used=R4_gemini_exact_match`

---

### UNRESOLVED
**attendee**: `tom@gmail.com`, `ABC`, `US` (free domain; no solid variations in US)  
**→ output**: no match, confidence **0**, `logic_used=UNRESOLVED`

---

## Outputs & confidence

- ≥90: auto-accept (optional policy)  
- 80–89: review  
- <80 or conflicts: reject → `UNRESOLVED`  
Confidence bands are suggestions—tune to your data.

---

## Privacy

- Never send full emails to external services; use **root domains** only.  
- Keep a switch to disable LLM and run deterministic/fuzzy only.

---

## Folder layout
```
.
├─ data/                # CSV files (attendee_list.csv, master_company_list.csv, etc.)
├─ output/              # Results (reconciliation_results.csv, unresolved_cases.csv, etc.)
├─ reconcile.py         # Main reconciliation script
├─ .config              # configuration file
├─ .env.example         # environment variables template
├─ .gitignore           # git ignore file
├─ requirements.txt
└─ README.md
```

---

## Notes

- Promote confirmed mappings into `company_alias`, `parent_alias`, and `domain_alias` (country-scoped) so future runs become deterministic.
- Keys are always **(company or domain) + country**.
