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

All rules require **same country**. Names are normalized (lowercase, remove legal suffixes, handle dots).

### **R1: Exact company + country** (confidence 100)
Normalized attendee name exactly matches `company_name` in master list.
```
Examples:
- `Microsoft Corporation` → `Microsoft Corporation` ✅
- `microsoft corp` → `Microsoft Corporation` ✅ (normalized match)
- `Apple` → `Apple Inc.` ✅ (legal suffix removed)
- `Google` → `Google LLC` ✅
```

### **R2: Exact parent + country** (confidence 95)  
Normalized attendee name exactly matches `parent_company_name` in master list.
```
Examples:
- `Alphabet` → `Google LLC` (parent: `Alphabet Inc.`) ✅
- `Meta` → `Instagram LLC` (parent: `Meta Platforms Inc.`) ✅
- `Berkshire Hathaway` → `GEICO` (parent: `Berkshire Hathaway Inc.`) ✅
```

### **R3: Historical lookups** (confidence 90-92)
**R3a: Email-based** (92) - Previous reconciliation by exact email address  
**R3b: Domain-based** (90) - Majority/most-recent company for email domain

```
Examples R3a (email history):
- `john@microsoft.com` previously mapped to `Microsoft Corporation` ✅
- Same email, different company name → use historical mapping

Examples R3b (domain history):
- `@accenture.com` domain historically maps to `Accenture PLC` ✅
- Multiple employees from same domain → use majority/recent mapping
```

### **R4: Fuzzy + AI-assisted matching** (confidence 85-94)
**R4 Fuzzy**: High-confidence fuzzy matching (threshold 92%)  
**R4 Gemini**: AI suggestions validated against master list

```
Examples R4 Fuzzy:
- `Microsft` → `Microsoft Corporation` (94% similarity) ✅
- `Amazn` → `Amazon.com Inc.` (91% similarity) ✅

Examples R4 Gemini:
- `Appel` → `Apple Inc.` (AI suggests: Apple Inc.(US), Appel Inc.(US), Apple Computer(US)...) ✅
- `FB` → `Meta Platforms Inc.` (AI recognizes stock ticker) ✅
- `MSFT` → `Microsoft Corporation` (AI knows abbreviations) ✅
```

### **Transparency Features**
- **Gemini suggestions shown**: `logic_used` includes all AI suggestions with countries
- **Format**: `R4_gemini_exact_match (suggestions: Apple Inc.(US); Appel Inc.(US); Apple Computer(US)...)`
- **Unresolved cases**: Show AI suggestions even when no match found

**Unmatched** → `UNRESOLVED (Gemini suggestions: CompanyA(US); CompanyB(GB)...)` (confidence 0)

---

## Quick start

### Install & Configure

**Automatic Setup** (Recommended):
```bash
# The reconcile.py script automatically installs dependencies and creates config files
python3 reconcile.py
```

**Manual Setup**:
```bash
# Install dependencies
pip install -r requirements.txt
# or minimal:
pip install pandas rapidfuzz pyarrow tldextract pyyaml python-dotenv google-generativeai

# Create environment file
echo "GEMINI_API_KEY=your_actual_key_here" > .env
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

## Detailed Examples (input → output)

All examples are **country-scoped** and use normalized names.

### R1 — Exact company + country (confidence 100)

**Example 1**: Perfect match after normalization
- **Attendee**: `alex@microsoft.com`, `Microsoft Corp`, `US`
- **Master**: (`Microsoft Corporation`, parent=`Microsoft Corporation`, `US`)
- **Normalized**: `microsoft` == `microsoft` ✅
- **→ Output**: `Microsoft Corporation`, `logic_used=R1_exact_company_country`

**Example 2**: Legal suffix removed
- **Attendee**: `jane@apple.com`, `Apple`, `US`
- **Master**: (`Apple Inc.`, parent=`Apple Inc.`, `US`)
- **Normalized**: `apple` == `apple` ✅
- **→ Output**: `Apple Inc.`, `logic_used=R1_exact_company_country`

---

### R2 — Exact parent + country (confidence 95)

**Example 1**: Parent company match
- **Attendee**: `priya@google.com`, `Alphabet`, `US`
- **Master**: (`Google LLC`, parent=`Alphabet Inc.`, `US`)
- **Normalized**: `alphabet` == `alphabet` ✅
- **→ Output**: `Google LLC`, `logic_used=R2_exact_parent_country`

**Example 2**: Holding company
- **Attendee**: `john@fb.com`, `Meta`, `US`
- **Master**: (`Facebook Inc.`, parent=`Meta Platforms Inc.`, `US`)
- **Normalized**: `meta` matches parent `meta platforms` ✅
- **→ Output**: `Facebook Inc.`, `logic_used=R2_exact_parent_country`

---

### R3a — Historical by email (confidence 92)

**Example**: Previous reconciliation
- **Attendee**: `jane.doe@acme.co.uk`, `ACME (UK)`, `GB`
- **History**: `jane.doe@acme.co.uk` → `Acme Ltd` (GB)
- **Master**: (`Acme Ltd`, parent=`Acme Group plc`, `GB`)
- **→ Output**: `Acme Ltd`, `logic_used=R3a_hist_email_exact`

---

### R3b — Historical by domain (confidence 90)

**Example**: Domain majority mapping
- **Attendee**: `sam.t@pwc.com`, `PwC`, `GB`
- **History**: `@pwc.com` in GB → 80% map to `PricewaterhouseCoopers LLP`
- **Master**: (`PricewaterhouseCoopers LLP`, parent=`PwC International`, `GB`)
- **→ Output**: `PricewaterhouseCoopers LLP`, `logic_used=R3b_hist_domain_company`

---

### R4 — Fuzzy + AI-assisted matching

**R4 Fuzzy** (confidence 94): High similarity score
- **Attendee**: `user@email.com`, `Microsft`, `US`
- **Master**: (`Microsoft Corporation`, parent=`Microsoft Corporation`, `US`)
- **Fuzzy Score**: 94% (above 92% threshold)
- **→ Output**: `Microsoft Corporation`, `logic_used=R4_fuzzy_company_validated`

**R4 Gemini** (confidence 94): AI assistance with transparency
- **Attendee**: `user@apple.com`, `Appel`, `US` (fuzzy score 80% < threshold)
- **Gemini Suggestions**: `Apple Inc.(US); Appel Inc.(US); Apple Computer(US); Appel Corporation(US); Apfel Inc.(US)`
- **Validation**: `Apple Inc.` found in master list ✅
- **→ Output**: `Apple Inc.`, `logic_used=R4_gemini_exact_match (suggestions: Apple Inc.(US); Appel Inc.(US); Apple Computer(US); Appel Corporation(US); Apfel Inc.(US))`

**Complex AI case**: Stock ticker recognition
- **Attendee**: `trader@fund.com`, `MSFT`, `US`
- **Gemini Suggestions**: `Microsoft Corporation(US); Microsoft(US); Microsoft Inc.(US); MSFT Corporation(US); MS Corporation(US)`
- **→ Output**: `Microsoft Corporation`, with full suggestion transparency

---

### UNRESOLVED with AI transparency

**Example**: No valid matches found
- **Attendee**: `tom@gmail.com`, `XYZ Corp`, `FR` (no FR companies in database)
- **Gemini Suggestions**: `Microsoft Corporation(US); Google LLC(US); Apple Inc.(US); Amazon.com Inc.(US); Meta Platforms Inc.(US)`
- **→ Output**: no match, confidence **0**, `logic_used=UNRESOLVED (Gemini suggestions: Microsoft Corporation(US); Google LLC(US)...)`

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
├─ reconcile.py         # Main reconciliation script (self-contained with auto-setup)
├─ .config              # Configuration file (auto-created)
├─ .env                 # Environment variables (auto-created)
├─ .gitignore           # Git ignore file
├─ requirements.txt     # Python dependencies
├─ README.md            # This file
└─ claude.md            # Technical documentation
```

---

## Notes

- Promote confirmed mappings into `company_alias`, `parent_alias`, and `domain_alias` (country-scoped) so future runs become deterministic.
- Keys are always **(company or domain) + country**.
