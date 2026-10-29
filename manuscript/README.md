# Manuscript build

## Working revision and archives

As of 29 October 2026, these sources prepare a **fresh Computers & Industrial
Engineering submission**, distinct from archived paper preprint v3
(https://doi.org/10.5281/zenodo.23628463) and software v1.3.0
(https://doi.org/10.5281/zenodo.23627916). Archives/tags and frozen evidence remain
unchanged. The revision reports industrial evidence and trajectory validation,
not a new algorithm, measured runtime/fee savings or observed planner benefit.
Original results use n=346; six-run replay uses n=338 on the same masked panel.

Canonical source: `main.tex` with `refs.bib`, `elsarticle.cls`, `Six_Run_Table.tex`
and the four figure PDFs. APA seventh edition uses installed `biblatex-apa`
(9.20), `biblatex` (3.22) and Biber (2.22), tested with TeX Live 2026.
Standard TeX packages include `babel`, `csquotes`, `lmodern` and the packages
listed in the preamble; install a matching TeX Live distribution, not a legacy
numeric `.bst` approximation. Existing `.bst` files are not used by this build.

```sh
pdflatex -interaction=nonstopmode -halt-on-error Figure_1_Workflow.tex
pdflatex -interaction=nonstopmode -halt-on-error Figure_2_Cost_Decomposition.tex
pdflatex -interaction=nonstopmode -halt-on-error Figure_3_Segments.tex
pdflatex -interaction=nonstopmode -halt-on-error Figure_S1_Three_Run_Reproducibility.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
biber main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

When migrating a previous numeric build, remove only its generated `main.bbl`
before the first LaTeX pass; the private package builder handles that stale file.
Do not remove source files. `\cite` aliases `\parencite` for existing parenthetical
citations; narrative citations use `\textcite`. APA's own sorting and
disambiguation rules apply. The reference metadata is not regenerated or invented.

The private `scripts/build_submission_packages.py --venue CIE` rebuilds the main and
reviewer PDFs, rejects unresolved citations/references and a page count over 35,
and scans reviewer PDFs, DOCX and source ZIP for identifying strings. The ZIP
includes all local inputs, `main.bbl` and its own build instructions. System TeX
packages are prerequisites, not private source dependencies. The private CIE
package contains the checked anonymous `01c_Manuscript_Anonymized.docx`, six
separate editable table DOCXs (`12_Table_1.docx` through `17_Table_6.docx`) and the
identified `02_Title_Page.docx`. C&IE requires editable source and mandatory
highlights; authenticated portal requirements remain unverified. The existing
ESWA packet is historical preparation and must not be rebuilt for this task.
The private packet verifier requires all 26 artifacts and refuses optimized
Python execution. It compares current source-derived abstract/body prose with
Word text independently of table/equation counts; text checks do not establish
visual correctness.
PDFs and LaTeX remain backups/previews. Final author visual approval remains
required. The unchanged third-party APA7 CSL, its pinned revision, attribution
and CC BY-SA 3.0 license exception are documented in `styles/NOTICE.md` in the
private source tree. No financial support or company clearance is inferred from
the disclosed employment and non-financial operational-data access.

The public guide specifies no page/spacing ceiling; 35 pages is the author's
stricter local constraint. Current layout: 12 pt, 1.85 spacing, one-inch margins;
tables and APA references are single-spaced. Identified public files are not
suitable for double-anonymized reviewer upload.
