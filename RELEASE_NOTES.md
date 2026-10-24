# InventOR v1.3.0 — prepared release notes

Prepared 24 October 2026. **Not yet an archived release.** Version 1.3.0 is a
candidate only; if that tag already names another commit, stop and select a new
version consistently in these notes, `.zenodo.json` and `CITATION.cff`. Never
overwrite or force-move an existing tag. No new version DOI is asserted here.

## Contents and boundaries

- Approved masked industrial panel: 233,078 daily records, 411 plant-material pairs.
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

## Verification before the author publishes

Optional commercial generation adds manual ChatGPT/Claude handoff, offline strict
validation/replay and opt-in OpenAI Responses/Code Interpreter or Anthropic
Messages/code-execution adapters. Only selected normalized training rows and
allowlisted parameters may be uploaded after explicit consent. New candidates
stay in ignored workspaces and are not paper evidence or proprietary-inference
replication. The original six-run evidence, prompts, figures and tables remain
frozen. No paid call is required for release verification. See
`docs/commercial_alternatives.md`.

```sh
python3 -S -m unittest discover -s tests -v
python3 -S scripts/verify_public.py --recompute
git diff --check
git rev-parse HEAD
git status --short
```

Run from the public snapshot without credentials. Record the reviewed full commit
and `PUBLIC_MANIFEST.json` hash in the GitHub release body. Do not fabricate them
in a template. Existing concept DOI: https://doi.org/10.5281/zenodo.22262051 .
Its latest checked version is v1.2.0, not this masked release.

## Author-only publication and archive inspection

1. Obtain explicit authorization for this external publication action. Preparation
   and company permission do not themselves authorize an agent to publish.
2. In Zenodo account settings, connect the owning GitHub account. Profile → GitHub
   → Sync now → enable `DressPD/inventor_public`; verify the enabled repository.
3. Inspect local and remote tags/releases before choosing the candidate version.
   Create the GitHub release on the reviewed full commit only after approval.
4. Check Zenodo's GitHub ingestion status and open the resulting record. If it
   fails, inspect the integration error; do not create a guessed DOI or an
   unrelated upload as a silent substitute.
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

The commercial path is a **software upgrade**. Before author publication, inspect
existing local and remote tags/releases and choose an unused software version;
update canonical `.zenodo.json`, `CITATION.cff` and these notes consistently.
No local tags were present at implementation baseline; remote checks and version
selection remain with the controlling session/author. Preserve software concept
DOI `10.5281/zenodo.22262051`, then inspect the actual newly archived source and
returned version DOI. No version DOI is preassigned here.

A **paper upgrade** is separate: if an existing manuscript/preprint record must
change, use that record's New version workflow and preserve its own concept DOI,
not the software DOI. Upload only the author-approved manuscript/supplementary
package, inspect the archived PDF and metadata, then cite the returned version
DOI honestly. Software release ingestion does not update a paper record or submit
to a journal. No paper DOI is guessed and no publication occurs automatically.
