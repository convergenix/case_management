# Frappe Drive Integration — Design

## Intent

Switch LawERP's file storage from the vanilla Frappe file manager to Frappe Drive — a real document-management experience (folders, previews, sharing) instead of files that only ever exist as isolated attachments on the one form they were uploaded through.

## Why now

Staff currently attach files (matter documents, intake evidence, conflict-waiver evidence) through plain `Attach` fields, each file reachable only from the specific record it's attached to. There's no way to browse "everything tied to this matter" as a folder, preview a document without downloading it, or share a document link the way Drive supports natively.

## Current state (confirmed by reading Frappe Drive's source, not assumed)

Frappe Drive does **not** replace Frappe's native `File` doctype — it extends it. Installing Drive adds custom fields to `File` (`team`, `status`, `mime_type`, `file_modified`, `content_doctype`/`content_docname`) via a fixture, plus its own supporting doctypes (`Drive Team`, `Drive Permission`, folders-as-`File`-records with `is_folder=1`). A `File` record can simultaneously be a normal Frappe attachment (`attached_to_doctype`/`attached_to_name`, what our existing `Attach` fields already populate) **and** a properly organized, Drive-browsable file (`team` + `folder` set) — these are not mutually exclusive, and nothing requires choosing one over the other.

This means the integration doesn't require replacing the `Attach` fields or reworking any upload UX. It requires: (a) a Drive folder structure to put files into, and (b) a hook that, after today's existing upload flow creates a `File` record the normal way, also sets that same record's Drive fields so it shows up properly organized inside Drive.

## Goals

- Every file attached through `Matter File Item`, `Intake Evidence`, or `Conflict Review.waiver_evidence` becomes a genuine Drive file: browsable, previewable, and (for restricted matters) shared only with the matter's own team — without changing the upload experience staff already use.
- One Drive folder per Matter, auto-created when the matter opens, holding everything tied to that matter.
- A restricted matter's folder is visible in Drive only to that matter's own team (mirrors the existing ethical wall; does not replace it).
- Pre-matter files (`Conflict Review.waiver_evidence` **and** `Intake Evidence`, both of which exist before any matter does) land somewhere sane and get moved into the matter's own folder the moment the matter opens.
- Evidence tied to an escalated/restricted conflict review (`Conflict Review.decision == "Restricted Match - Escalated"`) is never visible, in Drive, to anyone that review's own existing permission check (`conflict_review.py`) would already exclude — the confidentiality this design protects for restricted matters applies one step earlier, to the conflict stage itself.

## Non-goals

- No change to the `Attach` field upload UX on any of the three doctypes. Staff keep using the same upload control they already know.
- No per-matter Drive Team. One shared firm-wide team holds every matter's folder — a Team per matter would duplicate membership/storage-quota machinery the ethical wall already handles at the matter level, for no benefit.
- No retrofit of files already attached before this ships — this covers files attached from here forward. (Flagged as a known gap below, not solved by this design.)
- No change to who can read/write the `Matter File Item` / `Intake Evidence` / `Conflict Review` records themselves — their existing ethical-wall coverage (where it applies) is untouched. This only adds a *second*, Drive-side visibility control on the underlying file.

## Anti-goals

A restricted matter's documents must never become visible in Drive to someone the ethical wall would otherwise exclude from that matter. Getting the Drive Permission sync wrong in a way that's more permissive than the existing wall is worse than not building this at all.

## Constraints

- Reuses this app's established conventions: `is_new()` treated as an implicit transition (no bypassing a gate by creating directly into a state that should require one), real `FrappeTestCase` fixtures, no mocks.
- Drive's own `create_drive_file()` helper (in `drive/utils/__init__.py`) is built for Drive's own chunked-upload endpoint and always creates a **new** `File` record — it is not used here. Instead, the hook updates the Drive fields (`team`, `folder`, `is_private`, `mime_type`, `file_type`, `status`) directly on the **same** `File` record the existing `Attach` field upload already created, via `frappe.db.set_value`/`doc.save()` — no duplicate file, no new upload mechanism.
- Folder-level sharing uses Drive's own `Drive Permission` doctype (`user` + `entity` (the folder's File record) + `read`/`write`/`share`/`upload` booleans) — the documented, intended mechanism for per-folder access in Drive, not a new permission layer invented for this.
- **A pre-existing hook actively fights this design and must be fixed as part of it, not separately.** `hooks.py`'s `doc_events["File"]["validate"]` already points at `case_management.client.validate_update_tabfile_private`, which unconditionally sets `is_private = False` on every non-folder File, on every save, app-wide. `is_private` is what gates whether Frappe serves a file's raw URL without an auth check — independent of anything Drive's own `team`/`Drive Permission` model controls — and Drive re-saves File records routinely (renames, moves), so this hook would silently flip a restricted matter's files back to publicly fetchable by URL on the next such save, defeating the Anti-Goal outright. Fix: scope that existing function to skip Drive-managed files (`if doc.team: return` before the unconditional set) — a one-line, backward-compatible change; every other File record keeps today's behavior exactly.

## The how, as decided

**Firm-wide structure:**
- One Drive Team, created once (call it `LawERP`).
- One organizational root folder inside that team, `Matters`, holding one subfolder per Matter — avoids a flat folder list of every matter directly in the team root.
- One additional folder, `Pending Intake Evidence`, shared (not per-intake) — a short-lived staging area for conflict-waiver evidence uploaded before a matter exists. Low-stakes, low-volume, short-lived content; one shared folder is simpler than one per intake for something that's always relocated within days.

**Matter folder lifecycle:**
- A Matter's own folder is created when the Matter is first inserted (`is_new()`, the same point this app already treats as the matter's "opening" for every other purpose) — named after the matter, parented under `Matters`.
- At that same moment: (a) if the Matter's originating `Intake` has a `Conflict Review` with `waiver_evidence` set, that file's `folder` is updated to the new matter folder; (b) every `Intake Evidence` row's file on that same `Intake` is relocated the same way. Both are a field update on the existing `File` record — not a new upload, not a copy. No-op when there's nothing to relocate.

**Restricted-matter folder permissions:**
- When a Matter is `is_restricted`, the matter's own folder gets `Drive Permission` rows (`read`, at minimum) for exactly the users the ethical wall already grants matter access to (`Matter Team Item` rows + the responsible solicitor) — kept in sync whenever that membership changes, at the same trigger points the existing ethical-wall logic already uses.
- A non-restricted matter's folder needs no special `Drive Permission` rows — ordinary Drive team membership plus the folder's own default visibility covers it, same as any other firm document.

**Pre-matter (`Pending Intake Evidence`) folder permissions:**
- By default, ordinary Drive team visibility (any firm staff member) — the same low-stakes default already stated for this folder.
- When the owning `Intake`'s `Conflict Review` has `decision == "Restricted Match - Escalated"`, that specific review's `waiver_evidence` file (and any `Intake Evidence` files on the same intake) get `Drive Permission` rows narrowed to exactly the same role set `conflict_review.py`'s own `has_permission` already restricts that review to (`System Manager` / `Managing Partner` / `Conflicts Reviewer`) — mirroring, at the pre-matter stage, the same principle the restricted-matter folder already applies post-matter. These narrowed grants are superseded once the matter opens and the file is relocated under the matter's own (possibly also restricted) folder permissions.

**Per-file hook (`Matter File Item`, `Intake Evidence`, `Conflict Review.waiver_evidence`):**
- On save, when the attach field's value is new or changed, look up the resulting `File` record (by its stored file URL) and set: `team` = the firm's `LawERP` team, `folder` = the owning matter's folder (or `Pending Intake Evidence` for `Conflict Review`, until the matter exists), `is_private = 1`, `mime_type`/`file_type` (computed with `mimemapper`, the same library Drive's own upload path already uses), `status = "Active"`.

**`Matter File Item` wiring (new — confirmed, not currently live):**
- `Matter File Item` is a child-table doctype (`title` + `file`) with no existing field on `Matter` using it. This build adds a new `files` (Table → `Matter File Item`) field to `Matter` — staff attach matter documents there going forward, the same way `legal_team`/`check_list`/`activities`/`expense`/`invoice` already work as child tables on `Matter`.

**Retiring the legacy per-matter folder tree:**
- `hooks.py`'s `doc_events["Matter"]["on_update"] = "case_management.client.update_all_matter"` (which builds a `Home/Clients/<client>/<matter>/...` tree of ordinary, non-Drive folders from a `Folder Structure` template) is removed from `hooks.py` as part of this build — one per-matter folder tree going forward, not two competing ones. The function itself can stay in `client.py` unregistered (deleting it outright is a separate, smaller cleanup, not required here).
- `Matter.on_trash`'s delete-guard (`matter.py:135-136`, currently checking for a `File` named `Home/Clients/{matter.name}`) is updated to check for the new Drive matter folder instead, so the guard keeps doing its job (preventing deletion of a matter with attached documents) against the folder that's now actually in use.

## Known gap, left open

Files already attached through these three doctypes **before** this ships won't retroactively gain Drive organization — they stay plain attachments. Backfilling them (a one-time migration pass that walks existing records and re-homes their files) is a separate, smaller follow-up if wanted; not part of this build.

## What's left to the builder

- The exact field names linking `Matter File Item`/`Intake Evidence` back to their owning `Matter` (verifiable directly against the existing doctype JSON — this design doesn't guess at them).
- Exact hook placement (`validate()` vs `on_update` vs `after_insert`) for each of the three doctypes — functionally equivalent choices here, follow whichever this app's existing file-handling code (if any) already uses as precedent, else `on_update`.
- Test fixture construction — follow this app's established builder pattern (Customer → Legal Party → Intake → Conflict Review → Matter → Employee) already used across every test file in this app.
