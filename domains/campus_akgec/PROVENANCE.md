# Knowledge Base Provenance

The retrieval corpus in `docs/` is what makes Resolvix answer for a specific
institution. This file records where each section came from, so that anyone
auditing the system can tell a sourced fact from a placeholder.

Current institution: **Ajay Kumar Garg Engineering College (AKGEC), Ghaziabad**
— affiliated to Dr. A.P.J. Abdul Kalam Technical University, Lucknow, College
Code 027.

Corpus retrieved: **1 August 2026.**

## How provenance is recorded

Every doc in `corpus/` carries an HTML comment under its title listing the source
pages it was built from. Individual sections carry a `<!-- provenance: sourced -->`
or `<!-- provenance: synthetic -->` marker, machine-read at index time (§10.3 of
the PRD) — synthetic sections get a mandatory verbal hedge and an answerability
penalty rather than relying on a human remembering to flag them.

## Sourced from akgec.ac.in

These sections are built from the public AKGEC website and the local crawl in
`../../research/` (135 URLs, 3,305 extracted chunks).

| Doc | Sourced sections | Primary pages |
|---|---|---|
| `fee_structure.md` | All fee tables, payment details, refund norms, caution money, scholarships, loan documents | `/fee-structure-for-new-students2026-27`, `/fee-refund-norms`, `/scholarship`, `/academics/policy-and-process-for-refund-of-caution-money` |
| `hostel_rules.md` | Blocks and occupancy, allotment, fee and security, withdrawal refund, amenities, medical, anti-ragging | `/about/infrastructure-visual-tour/hostel`, `/uptac`, `/life-akgec/mediclaim` |
| `exam_schedule.md` | Examination pattern, end semester exam, academic calendar, question paper bank | `/academics/academic-calendar`, `/central-library`, `aktu.ac.in` |
| `admissions.md` | Every section | `/uptac`, `/courses-offered`, `/admissions`, `/scholarship` |
| `placements.md` | T&P department, placement record, highest package, recruiters, training, industrial training | `/placements/tp-department`, `/placements/placement-records`, `/placements/our-recruiters` |
| `application_forms.md` | ERP, passout certificates, educational verification, ID card, library, mediclaim, grievance, anti-ragging, ICC, address | `/academics/issuance-of-certificates-for-passout-students`, `/grievance-committee`, `/central-library`, `/life-akgec/mediclaim` |

## Synthetic placeholders

Three of the six IVR categories are only partly covered by the public website.
Hostel discipline rules, internal examination policy, and several
current-student service processes live in ERP circulars and the hostel
handbook, which are not published publicly. Those sections are written to be
realistic and internally consistent with AKTU norms, and are flagged
`SYNTHETIC` in the doc.

| Doc | Synthetic sections |
|---|---|
| `fee_structure.md` | Late Payment and Instalments |
| `hostel_rules.md` | Mess Facility and Timings · Entry Timings and Curfew · Leave and Outing Permission · Visitors · Prohibited Items and Conduct · Room Change and Vacating |
| `exam_schedule.md` | Sessional Examinations · Pre-University Test · Attendance Requirement · Carry Over Papers · Admit Card · Results and Revaluation |
| `placements.md` | Placement Eligibility and Process · Placement Preparation Timeline |
| `application_forms.md` | Bonafide Certificate · Marksheets and Transcripts · Transport |

**Before any real deployment**, replace every synthetic section with the
corresponding official document. Grep for the marker:

```bash
grep -rn "provenance: synthetic" domains/campus_akgec/corpus/
```

## Raw crawl

`../../research/` holds the crawl this corpus was distilled from:

| File | Contents | Status |
|---|---|---|
| `rag_cleaned_1.json` | 3,305 chunks with `text` / `source` / `title` / `domain` | Usable; JSON is malformed at ~char 19.3M and needs lenient parsing |
| `akg_data.csv` | 304 rows of `link` + `content_chunk` | Clean |
| `akgec_markdown.csv` | 137 pages of markdown with links preserved | Clean |
| `raw_data.txt` / `fit_data.txt` | Unsegmented scrape | Raw source |
| `akg_links.txt` | 135 crawled URLs | Crawl manifest |
| `rag_cleaned_2.json` | 1,438 records | **Corrupt** — 22.6% printable bytes, `text` fields are binary garbage. Re-scrape or discard. |

The crawler is `../data/web-markdown.py` (crawl4ai with a pruning content
filter). Re-running it against `akg_links.txt` regenerates the corpus.
