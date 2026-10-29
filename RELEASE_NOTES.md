# InventOR v1.3.0 — verified archive and subsequent paper corrections

## Secondary offline support — 29 October 2026 (later local extension)

The working revision now credits Yan–Ji, SimGPT and InvEvolve (explicit arXiv v4
preprint), with preview/abstract access limits. Training-free proposal screening
leads the framing. New, separate `outputs/secondary_admission/` evidence reuses
fixed policies and compares frozen clipping with strict MOQ/capacity admission.
`docs/secondary_admission.md` supplies reproducible methods, a conditional
invariant, finite-state/counterexample checks and adverse cost/service examples.
Anonymous CIE S2 support is private; screened replay code/inputs/results are local
public-repository support. This is no longer a manuscript-only working change,
but no new archive, tag, DOI, remote publication or submission is authorized.
Archived software v1.3.0 and preprint v3 remain unchanged; any future archive
refresh requires separate approval. Source semantics, privacy/rights, historical
inference reconstruction and prospective planner benefits remain unresolved.

## Working C&IE revision — 29 October 2026 (superseding status)

The current manuscript prepares a fresh Computers & Industrial Engineering
submission after ESWA novelty rejection, not a transfer or a new published
preprint. It emphasizes reproducible industrial comparisons and trajectory
validation, removes unsupported priority/runtime claims, and corrects percentage
denominators. LLM cost is about 6%/8%/18% above history-only/SBA/empirical costs;
the cheaper-baseline findings, Plant C losses and service trade-offs remain.
The n=346 original and n=338 same-panel six-run protocols remain distinct.

This status supersedes the preparation wording below, not the underlying
scientific/access limitations. Source semantics, privacy and release rights
remain unverified; tests/replay do not close those gates. The working PDF/source
differs from archived preprint v3 (https://doi.org/10.5281/zenodo.23628463).
Software v1.3.0, historical evidence, tags and DOIs remain unchanged.
The private CIE packet/declaration is not exported. No new software archive is
needed for a manuscript-only revision. An optional new paper-preprint version
requires separate authorization after final review; never overwrite v3.

Review-fix follow-up: highlights now affirm training-free configuration,
comparative evidence, reproducible replay and trajectory checks. Stronger
baselines/Plant C losses remain in the manuscript and cover. The local
robustness paragraph explicitly defines penalties 1/5 as multiples of unit cost
per shortage unit; all frozen numerical values remain unchanged.

## Current-snapshot HOLD — 25 October 2026

**Major Revision.** Data grain/additivity and demand semantics remain unvalidated;
privacy/confidentiality and publication/release rights remain separate holds.
This later local snapshot fixes transport/parser/cache and export-integrity defects
and corrects reporting/citations, without changing frozen numerical evidence.
The panel is pseudonymized, not demonstrated anonymous: dated lead-time/normalized
demand signatures and invariant economic products retain linkage exposure.
Tests/replay do not grant scientific clearance or redistribution rights.
No new release, push, submission or published-history change is authorized here.

Verified 25 October 2026. Software **v1.3.0 is published and archived**:

- GitHub release: https://github.com/DressPD/inventor_public/releases/tag/v1.3.0
- Version DOI: https://doi.org/10.5281/zenodo.23627916
- Record: https://zenodo.org/records/23627916
- Frozen public commit: `d1d602d7087714e6430fe9ac551ab086800b4608`.
- Archived manifest SHA-256:
  `024d64eb793078a15f70e95d3f38c2c5557fe00e55cbd14e36d939f1c1e73003`.

The actual archived ZIP passed checksum, 4,800-file manifest, 51 credential-free
tests and frozen numerical replay verification. Its temporary downloaded ZIP and
extracted verification copy were subsequently deleted at the author's request;
verification evidence was retained. No published files or tags were changed.

This **later working snapshot** includes corrected manuscript reporting, Figure 1
labels and the verified DOI. It is not the source tree or manifest of the published
v1.3.0 archive. Numerical results, tables and historical prompts are unchanged.
Do not overwrite or force-move the published tag. A separately authorized new
version is needed if the later corrected files must themselves be archived.

## Contents and boundaries

- Masked industrial panel: 233,078 daily records, 411 plant-material pairs.
- O1*–O3*: frozen original policies rescaled to the masked panel, not fresh inference.
- M1–M3: three fresh masked generations; missing and invalid outputs retained.
- Six-run evidence, table and Figures 2–4 use 338 shared feasible pairs and seven
  comparators. Six generations reuse one panel, not six independent datasets.
- Sanitized provenance retains original hashes and runner-hash amendment histories.
- APA seventh-edition manuscript sources build with `pdflatex`, `biber`, then
  `pdflatex` twice. Figures 1–4 and original headline results are preserved.
- MIT licensing; `.zenodo.json` is authoritative for Zenodo GitHub ingestion.
- No masking factors, private gateway credentials or raw gateway responses.
- Original confidential numerical results and fresh proprietary inference cannot
  be independently regenerated. Clipped orders can violate MOQ; capacity replay
  does not establish simultaneous MOQ/capacity feasibility.

## Verification for a later working snapshot or separately authorized release

Optional commercial generation adds manual ChatGPT/Claude handoff, offline strict
validation/replay and opt-in OpenAI Responses/Code Interpreter or Anthropic
Messages/code-execution adapters. Only selected normalized training rows and
allowlisted parameters may be uploaded after explicit consent. New candidates
stay in ignored workspaces and are not paper evidence or proprietary-inference
replication. The original six-run evidence, prompts, numerical Figures 2–4 and
tables remain frozen; Figure 1 labels are corrected in this later snapshot.
No paid call is required for release verification. See
`docs/commercial_alternatives.md`.

```sh
python3 -B -S scripts/verify_public.py --strict  # fresh snapshot, before generated files
python3 -S -m unittest discover -s tests -v
python3 -S scripts/verify_public.py --recompute
git diff --check
git rev-parse HEAD
git status --short
```

Run from the public snapshot without credentials. Record the reviewed full commit
and `PUBLIC_MANIFEST.json` hash in the GitHub release body. Do not fabricate them
in a template. Software concept DOI: https://doi.org/10.5281/zenodo.22262051 .
The verified v1.3.0 version DOI above identifies the frozen release, not later edits.

## Reference procedure for future publication and archive inspection

The v1.3.0 publication and archive inspection above are complete. These instructions
apply only to a future, separately approved release with an unused version/tag.

1. Obtain explicit authorization for this external publication action.
   Preparation does not authorize an agent to publish.
2. In Zenodo account settings, connect the owning GitHub account. Profile → GitHub
   → Sync now → enable `DressPD/inventor_public`; verify the enabled repository.
3. Inspect local and remote tags/releases before choosing the candidate version.
   If a candidate tag already exists, stop; never reuse or force-move it.
   Create the GitHub release on the reviewed full commit only after approval.
4. Check Zenodo's GitHub ingestion status and open the resulting record. If it
   fails, inspect the integration error; do not create a guessed DOI or an
   unrelated upload as a silent substitute.
   No new version DOI may be inferred from a tag; use the actual returned DOI.
5. Confirm the record belongs to concept `22262051`, has the intended version,
   title, creator and MIT license, and contains the actual GitHub source archive.
   Download/extract it; run the manifest verifier and offline replay there. Compare
   the archived manifest hash with the reviewed release. Check the archived PDF,
   masked panel, six-run evidence and retained amendment histories.
6. Copy the returned version DOI verbatim into the **canonical private sources**:
   editor-facing availability in `manuscript/main.tex` and
   `public_release/RELEASE_NOTES.md`. Record the full archived commit separately.
   Retain the concept DOI for discovery; never guess a DOI or relabel an old archive.
   Do not hand-edit exported notes or amend the archived commit/published tag.
7. Rebuild the submission package, retaining anonymized reviewer files. From the
   private project, run `python3 scripts/export_public.py --dest ../inventor_public_candidate`
   using a new, disposable, non-Git destination outside the private repository.
   This regenerates `PUBLIC_MANIFEST.json` for the changed notes, sources and PDFs.
   In that exported snapshot, without credentials, rerun the public tests and
   `python3 -S scripts/verify_public.py --recompute`. Review and safely synchronize
   the verified snapshot into the current public worktree without replacing `.git`
   or unrelated work; record a new reviewed commit and manifest hash.

The DOI-bearing current snapshot is a **later commit**, not the preserved archived
commit or its manifest. Cite the verified archived DOI/commit honestly. If the
updated files themselves must be archived, obtain authorization for a **new version**
with an unused tag and repeat archive inspection; never edit or move published tags.

Zenodo allows limited minor file corrections within 30 days, with republication
within 45 days of the original publication. Later modifications require justified
support approval; substantial changes should use a new version. Do not promise
absolute immutability or silently replace files. See official instructions:

- https://help.zenodo.org/docs/github/enable-repository/
- https://help.zenodo.org/docs/github/archive-software/github-upload/
- https://help.zenodo.org/docs/github/describe-software/zenodo-json/
- https://help.zenodo.org/docs/deposit/manage-files/#modify

Archiving is not journal submission, disclosure clearance or journal acceptance.

## Software version versus paper version

The commercial path is included in the archived **software v1.3.0**. Before any
future software publication, inspect local and remote tags/releases, choose an
unused version and update canonical metadata consistently. Preserve software
concept DOI `10.5281/zenodo.22262051`; inspect the actual new archive and returned
version DOI. Never reuse v1.3.0 for later manuscript edits.

A **paper upgrade** is separate: if an existing manuscript/preprint record must
change, use that record's New version workflow and preserve its own concept DOI,
not the software DOI. Upload only the author-approved manuscript/supplementary
package, inspect the archived PDF and metadata, then cite the returned version
DOI honestly. Software release ingestion does not update a paper record or submit
to a journal. No paper DOI is guessed and no publication occurs automatically.
