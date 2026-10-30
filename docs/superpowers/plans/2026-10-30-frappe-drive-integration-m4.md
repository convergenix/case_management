# Frappe Drive Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch LawERP's file storage from plain `Attach` fields to Frappe Drive — files attached through `Matter File Item`, `Intake Evidence`, and `Conflict Review.waiver_evidence` become genuine Drive files organized into one folder per Matter, without changing the upload UX.

**Architecture:** A new `case_management/case_management/drive_integration.py` module owns every Drive-side operation (team/folder get-or-create, per-file organization, team-membership sync) as plain functions — no new doctypes. Non-restricted matters share one firm-wide `LawERP` Drive Team; a restricted matter gets its own dedicated Drive Team instead, since Drive's actual access boundary is team membership, not `Drive Permission` rows (verified against Drive's own source — see the spec). Three existing doctype controllers (`Matter`, `Matter File Item`, `Intake Evidence`, `Conflict Review`) call into the Drive module from their existing `validate()`/`after_insert()`/`on_update()` hooks. A `File` record stays exactly what it's always been (a normal Frappe attachment with `attached_to_doctype`/`attached_to_name`) and simultaneously becomes a properly organized Drive file (`team` + `folder` set) — the same record, not a duplicate.

**Tech Stack:** Frappe v15/v16, Frappe Drive (installed as the `drive` app), `FrappeTestCase`.

**Spec:** `docs/superpowers/specs/2026-10-30-frappe-drive-integration-design.md`

## Global Constraints

- `FrappeTestCase` against the real bench DB, no mocks, fixtures built via `.insert()` — this app's standing house rule.
- Always pass `--skip-test-records` to `bench run-tests`.
- Sync doctype/JSON changes via `bench --site <site> --force reload-doc case_management doctype <docname>` (never `bench migrate` on the canonical dev bench — pre-existing, unrelated broken fixtures make it fail there; `bench migrate` is fine on a clean v16 verification bench specifically).
- This build assumes the `drive` app is installed on any site that needs its file-organization behavior. Not declared as a hard dependency anywhere (`required_apps` isn't a pattern this codebase already uses) — same soft-dependency posture already taken toward `erpnext`/`hrms`.
- Known bug class this app has hit repeatedly: a `validate()` that lets a document be created directly into a privileged state by returning early for `is_new()` before its gates run. Every new check in this plan treats `is_new()` as part of the normal path, never a bypass.
- **Drive's access grant is Team-membership-based, not `Drive Permission`-based.** Verified directly against Drive's own `get_access()` (`drive/api/permissions.py`): any member of a file's owning Team gets unconditional baseline read on every file in that team, and `Drive Permission` rows only ever add access, never subtract it. This plan never creates a `Drive Permission` row. Every access decision here is made by which Drive Team a folder (and its files) belong to, and who's listed on that team via its member child table.
- Reuse, don't reinvent: `matter.py`'s existing `has_permission()` already contains the exact membership-determination logic (`Matter Team Item` rows resolved via `Employee.user_id`, plus `responsible_solicitor`) — Task 6 mirrors that logic to compute a restricted matter's dedicated Drive Team membership; it does not invent a second version of it.
- Mime-type detection for an already-saved `File` record uses Python's standard-library `mimetypes.guess_type()` on the file's `file_name` — **not** Drive's own `mimemapper` library, which is built for its chunked-upload pipeline's fresh-temp-file-on-disk context and isn't the right tool for re-classifying a `File` record that already exists.

## Review Focus

- A Matter created through a direct API/import call (bypassing any UI flow) still gets its Drive folder created, in the correct team for its `is_restricted` value at creation time — the same `is_new()`-bypass bug class this app has hit twice before, now applied to folder creation instead of a status gate.
- A Matter with no originating Conflict Review waiver evidence and no Intake Evidence at all — relocation must no-op cleanly, never throw, since this is the common case (most matters have neither).
- Two different Intakes' evidence files landing in the same shared `Pending Intake Evidence` folder with the same file name — `organize_file_in_drive` reassigns `folder`/`team` without renaming, so a collision here must not silently merge or overwrite one file's Drive record with another's.
- The retired `on_trash` guard's new behavior: it must still **block** deleting a Matter that has real files in its Drive folder, and must **not** block deleting an empty matter — the new folder exists unconditionally once a Matter opens, so a naive "does the folder exist" check would block every deletion, which is not what the original guard was for.
- A file's own `team` field must always match whichever team currently owns its folder — true right after initial organization, after relocation out of `Pending Intake Evidence` into a matter's folder, and after a later `is_restricted` toggle moves the folder itself to or from a dedicated team — because Drive's access check reads each file's own `team` field, not its parent folder's, so a folder move that doesn't cascade to its children's `team` leaves them with stale, wrong access.

---

### Task 1: Drive setup module — teams, root folders, membership sync, per-file organizer

**Files:**
- Create: `case_management/case_management/drive_integration.py`
- Test: `case_management/case_management/test_drive_integration.py`

**Interfaces:**
- Produces: `get_or_create_lawerp_team() -> str`, `get_or_create_matter_team(matter_name: str) -> str`, `sync_team_membership(team_name: str, user_emails: set[str]) -> None`, `get_or_create_matters_root_folder() -> str`, `get_or_create_pending_intake_evidence_folder() -> str`, `get_or_create_matter_folder(matter_name: str, is_restricted: bool) -> str` (folder's File name — creates it, or moves it between teams if `is_restricted` no longer matches where it currently lives, cascading the move to every File inside it), `organize_file_in_drive(file_url: str, folder_name: str, team_name: str) -> None`. Every later task calls these by name.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase


class TestDriveIntegration(FrappeTestCase):
	def test_get_or_create_lawerp_team_is_idempotent(self):
		from case_management.case_management.drive_integration import get_or_create_lawerp_team
		first = get_or_create_lawerp_team()
		second = get_or_create_lawerp_team()
		self.assertEqual(first, second)
		self.assertTrue(frappe.db.exists("Drive Team", first))

	def test_matters_root_and_pending_evidence_folders_are_idempotent_and_distinct(self):
		from case_management.case_management.drive_integration import (
			get_or_create_matters_root_folder,
			get_or_create_pending_intake_evidence_folder,
		)
		matters_root = get_or_create_matters_root_folder()
		pending = get_or_create_pending_intake_evidence_folder()
		self.assertNotEqual(matters_root, pending)
		self.assertEqual(matters_root, get_or_create_matters_root_folder())
		self.assertEqual(pending, get_or_create_pending_intake_evidence_folder())
		self.assertEqual(frappe.db.get_value("File", matters_root, "file_name"), "Matters")
		self.assertEqual(frappe.db.get_value("File", pending, "file_name"), "Pending Intake Evidence")

	def test_get_or_create_matter_folder_nests_under_matters_root_when_not_restricted(self):
		from case_management.case_management.drive_integration import (
			get_or_create_matter_folder,
			get_or_create_matters_root_folder,
			get_or_create_lawerp_team,
		)
		folder = get_or_create_matter_folder("DRIVE-TEST-MATTER-001", is_restricted=False)
		self.assertEqual(frappe.db.get_value("File", folder, "folder"), get_or_create_matters_root_folder())
		self.assertEqual(frappe.db.get_value("File", folder, "team"), get_or_create_lawerp_team())
		self.assertEqual(get_or_create_matter_folder("DRIVE-TEST-MATTER-001", is_restricted=False), folder)

	def test_get_or_create_matter_folder_gets_its_own_team_when_restricted(self):
		from case_management.case_management.drive_integration import (
			get_or_create_matter_folder,
			get_or_create_matter_team,
			get_or_create_lawerp_team,
		)
		folder = get_or_create_matter_folder("DRIVE-TEST-MATTER-002", is_restricted=True)
		team = get_or_create_matter_team("DRIVE-TEST-MATTER-002")
		self.assertNotEqual(team, get_or_create_lawerp_team())
		self.assertEqual(frappe.db.get_value("File", folder, "team"), team)

	def test_toggling_restriction_moves_the_folder_and_cascades_to_its_files(self):
		from case_management.case_management.drive_integration import (
			get_or_create_matter_folder,
			get_or_create_matter_team,
			get_or_create_lawerp_team,
		)
		folder = get_or_create_matter_folder("DRIVE-TEST-MATTER-003", is_restricted=False)
		child = frappe.get_doc({
			"doctype": "File", "file_name": "inside.pdf", "content": "x",
			"folder": folder, "team": get_or_create_lawerp_team(), "is_private": 1,
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "File", child.name, force=True)

		moved_folder = get_or_create_matter_folder("DRIVE-TEST-MATTER-003", is_restricted=True)
		dedicated_team = get_or_create_matter_team("DRIVE-TEST-MATTER-003")
		self.assertEqual(moved_folder, folder)
		self.assertEqual(frappe.db.get_value("File", folder, "team"), dedicated_team)
		self.assertEqual(frappe.db.get_value("File", child.name, "team"), dedicated_team)

	def test_sync_team_membership_matches_exactly(self):
		from case_management.case_management.drive_integration import get_or_create_matter_team, sync_team_membership
		team = get_or_create_matter_team("DRIVE-TEST-MATTER-004")
		sync_team_membership(team, {"a@example.com"})
		sync_team_membership(team, {"b@example.com"})
		members = set(frappe.get_all("Drive Team Member", filters={"parent": team}, pluck="user"))
		self.assertEqual(members, {"b@example.com"})

	def test_organize_file_in_drive_sets_team_folder_and_privacy(self):
		from case_management.case_management.drive_integration import (
			get_or_create_pending_intake_evidence_folder,
			get_or_create_lawerp_team,
			organize_file_in_drive,
		)
		test_file = frappe.get_doc({
			"doctype": "File", "file_name": "evidence.pdf", "content": "test content", "is_private": 0,
		}).insert()
		self.addCleanup(frappe.delete_doc, "File", test_file.name, force=True)

		pending = get_or_create_pending_intake_evidence_folder()
		team = get_or_create_lawerp_team()
		organize_file_in_drive(test_file.file_url, pending, team)

		reloaded = frappe.db.get_value(
			"File", {"file_url": test_file.file_url},
			["team", "folder", "is_private", "status", "mime_type"], as_dict=True,
		)
		self.assertEqual(reloaded.team, team)
		self.assertEqual(reloaded.folder, pending)
		self.assertEqual(reloaded.is_private, 1)
		self.assertEqual(reloaded.status, "Active")
		self.assertEqual(reloaded.mime_type, "application/pdf")

	def test_organize_file_in_drive_is_a_noop_for_missing_file_url(self):
		from case_management.case_management.drive_integration import organize_file_in_drive
		organize_file_in_drive(None, "irrelevant", "irrelevant")
		organize_file_in_drive("", "irrelevant", "irrelevant")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.test_drive_integration`
Expected: FAIL — `ModuleNotFoundError: No module named 'case_management.case_management.drive_integration'`

- [ ] **Step 3: Before implementing, confirm the Drive Team membership child-table shape**

Read `drive/drive/doctype/drive_team/drive_team.json` and `drive_team.py` directly (don't guess): confirm the exact fieldname of the child-table field on `Drive Team` that holds `Drive Team Member` rows (referenced below as `<members_fieldname>`), and confirm `Drive Team Member`'s own field for the user's email (referenced below as `user`, but verify — it may be named differently).

- [ ] **Step 4: Implement `case_management/case_management/drive_integration.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import mimetypes
import frappe
from drive.utils import get_file_type, get_home_folder

LAWERP_TEAM_TITLE = "LawERP"
MATTERS_FOLDER_NAME = "Matters"
PENDING_EVIDENCE_FOLDER_NAME = "Pending Intake Evidence"


def get_or_create_lawerp_team():
	existing = frappe.db.get_value("Drive Team", {"title": LAWERP_TEAM_TITLE}, "name")
	if existing:
		return existing
	team = frappe.get_doc({"doctype": "Drive Team", "title": LAWERP_TEAM_TITLE}).insert(ignore_permissions=True)
	return team.name


def get_or_create_matter_team(matter_name):
	title = f"Matter: {matter_name}"
	existing = frappe.db.get_value("Drive Team", {"title": title}, "name")
	if existing:
		return existing
	team = frappe.get_doc({"doctype": "Drive Team", "title": title}).insert(ignore_permissions=True)
	return team.name


def sync_team_membership(team_name, user_emails):
	# Use the <members_fieldname>/`user` names confirmed in Step 3, via the parent
	# Drive Team doc's own child table (mirrors how drive_team.py's own
	# after_insert() already adds the creator) -- not a bare Drive Team Member insert.
	user_emails = set(user_emails)
	team = frappe.get_doc("Drive Team", team_name)
	current = {row.user for row in team.get("<members_fieldname>")}
	for user in current - user_emails:
		team.set("<members_fieldname>", [r for r in team.get("<members_fieldname>") if r.user != user])
	for user in user_emails - current:
		team.append("<members_fieldname>", {"user": user})
	team.save(ignore_permissions=True)


def _get_or_create_subfolder(team, folder_name, parent_folder_name):
	existing = frappe.db.get_value(
		"File",
		{"team": team, "folder": parent_folder_name, "file_name": folder_name, "is_folder": 1},
		"name",
	)
	if existing:
		return existing
	folder = frappe.get_doc({
		"doctype": "File", "file_name": folder_name, "is_folder": 1, "is_private": 1,
		"team": team, "folder": parent_folder_name,
	})
	folder.flags.allow_storage_change = True
	folder.insert(ignore_permissions=True)
	return folder.name


def get_or_create_matters_root_folder():
	team = get_or_create_lawerp_team()
	home = get_home_folder(team)
	return _get_or_create_subfolder(team, MATTERS_FOLDER_NAME, home.name)


def get_or_create_pending_intake_evidence_folder():
	team = get_or_create_lawerp_team()
	home = get_home_folder(team)
	return _get_or_create_subfolder(team, PENDING_EVIDENCE_FOLDER_NAME, home.name)


def get_or_create_matter_folder(matter_name, is_restricted):
	target_team = get_or_create_matter_team(matter_name) if is_restricted else get_or_create_lawerp_team()
	target_parent = (
		get_home_folder(target_team).name if is_restricted
		else get_or_create_matters_root_folder()
	)
	existing = frappe.db.get_value(
		"File", {"file_name": matter_name, "is_folder": 1}, ["name", "team"], as_dict=True,
	)
	if not existing:
		folder = frappe.get_doc({
			"doctype": "File", "file_name": matter_name, "is_folder": 1, "is_private": 1,
			"team": target_team, "folder": target_parent,
		})
		folder.flags.allow_storage_change = True
		folder.insert(ignore_permissions=True)
		return folder.name
	if existing.team != target_team:
		frappe.db.set_value(
			"File", existing.name, {"team": target_team, "folder": target_parent}, update_modified=False,
		)
		frappe.db.set_value("File", {"folder": existing.name}, "team", target_team, update_modified=False)
	return existing.name


def organize_file_in_drive(file_url, folder_name, team_name):
	if not file_url:
		return
	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		return
	underlying_file_name = frappe.db.get_value("File", file_name, "file_name")
	mime_type, _ = mimetypes.guess_type(underlying_file_name or "")
	file_type = get_file_type(mime_type) if mime_type else "Unknown"
	frappe.db.set_value(
		"File", file_name,
		{
			"team": team_name, "folder": folder_name, "is_private": 1,
			"mime_type": mime_type, "file_type": file_type, "status": "Active",
		},
		update_modified=False,
	)
```

Replace every `<members_fieldname>` placeholder with the real fieldname confirmed in Step 3 before running the tests.

- [ ] **Step 5: Sync the drive app's custom fields on File if not already present on this bench, then run the test**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.test_drive_integration`
Expected: PASS (8/8)

- [ ] **Step 6: Commit**

```bash
git add case_management/case_management/drive_integration.py case_management/case_management/test_drive_integration.py
git commit -m "feat: add Drive team/folder/membership/file-organization helpers"
```

---

### Task 2: Fix the pre-existing hook that fights Drive's privacy model

**Files:**
- Modify: `case_management/client.py`
- Test: `case_management/case_management/test_drive_integration.py` (same file as Task 1, new test class)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this closes a correctness gap, no new public interface.

- [ ] **Step 1: Read the current function**

Read `case_management/client.py` around `def validate_update_tabfile_private(doc, event):` — confirm it still reads exactly:
```python
def validate_update_tabfile_private(doc, event):
	if(doc.is_folder==False):
		doc.is_private= False
```

- [ ] **Step 2: Write the failing test**

```python
class TestValidateUpdateTabfilePrivate(FrappeTestCase):
	def test_drive_managed_file_keeps_is_private_true(self):
		test_file = frappe.get_doc({
			"doctype": "File", "file_name": "drive-managed.pdf",
			"content": "x", "is_private": 1, "team": "irrelevant-team-name",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "File", test_file.name, force=True)
		test_file.reload()
		self.assertEqual(test_file.is_private, 1)

	def test_non_drive_file_is_still_forced_public(self):
		test_file = frappe.get_doc({
			"doctype": "File", "file_name": "ordinary.pdf",
			"content": "x", "is_private": 1,
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "File", test_file.name, force=True)
		test_file.reload()
		self.assertEqual(test_file.is_private, 0)
```

- [ ] **Step 3: Run test to verify the first assertion fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.test_drive_integration`
Expected: FAIL on `test_drive_managed_file_keeps_is_private_true` — `is_private` gets forced to `0` even though `team` is set.

- [ ] **Step 4: Fix `validate_update_tabfile_private` in `case_management/client.py`**

```python
def validate_update_tabfile_private(doc, event):
	if doc.team:
		return
	if(doc.is_folder==False):
		doc.is_private= False
```

- [ ] **Step 5: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.test_drive_integration`
Expected: PASS (both tests in this class)

- [ ] **Step 6: Commit**

```bash
git add case_management/client.py case_management/case_management/test_drive_integration.py
git commit -m "fix: stop forcing is_private=False on Drive-managed File records"
```

---

### Task 3: Wire `Matter File Item` into `Matter`, create the Matter's Drive folder on open, retire the legacy folder tree

**Files:**
- Modify: `case_management/case_management/doctype/matter/matter.json`
- Modify: `case_management/case_management/doctype/matter/matter.py`
- Modify: `case_management/hooks.py`
- Test: `case_management/case_management/doctype/matter/test_matter_drive_folder.py`

**Interfaces:**
- Consumes: `drive_integration.get_or_create_matter_folder(matter_name, is_restricted)` (Task 1).
- Produces: `Matter.files` (new Table field, options `Matter File Item`) — Task 4 relies on this field existing so `Matter File Item` rows have a real parent.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate


class TestMatterDriveFolder(FrappeTestCase):
	def _make_matter(self, label="Drive Folder Test"):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": f"{label} Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": f"{label} Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search
		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		review.decision = "Clear"
		review.save()
		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()

		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": f"{label} Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)

		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": f"{label} Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name

		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": f"{label} Transaction", "responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)
		return matter

	def test_opening_a_matter_creates_its_drive_folder(self):
		from case_management.case_management.drive_integration import get_or_create_matter_folder
		matter = self._make_matter()
		folder = get_or_create_matter_folder(matter.name, matter.is_restricted)
		self.assertTrue(frappe.db.exists("File", folder))
		self.assertEqual(frappe.db.get_value("File", folder, "file_name"), matter.name)

	def test_matter_has_a_files_table_using_matter_file_item(self):
		meta = frappe.get_meta("Matter")
		field = meta.get_field("files")
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Table")
		self.assertEqual(field.options, "Matter File Item")

	def test_on_trash_allows_deleting_an_empty_matter(self):
		matter = self._make_matter(label="Empty Matter For Trash")
		# Should not raise even though the matter's Drive folder now exists.
		frappe.delete_doc("Matter", matter.name, force=True)
		self.assertFalse(frappe.db.exists("Matter", matter.name))

	def test_on_trash_blocks_deleting_a_matter_with_files_in_its_folder(self):
		from case_management.case_management.drive_integration import get_or_create_matter_folder
		matter = self._make_matter(label="Matter With Files For Trash")
		folder = get_or_create_matter_folder(matter.name, matter.is_restricted)
		file_in_folder = frappe.get_doc({
			"doctype": "File", "file_name": "exhibit.pdf", "content": "x",
			"folder": folder, "is_private": 1,
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "File", file_in_folder.name, force=True)

		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("Matter", matter.name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.matter.test_matter_drive_folder`
Expected: FAIL — `files` field doesn't exist on Matter; no Drive folder gets created on matter open.

- [ ] **Step 3: Add the `files` field to `matter.json`**

Read the current `field_order` array. Add `"files"` to it (a sensible position near the other child-table fields such as `legal_team`/`check_list` — exact position doesn't matter functionally). Add the matching field object to `fields`:

```json
{
 "fieldname": "files",
 "fieldtype": "Table",
 "label": "Files",
 "options": "Matter File Item"
}
```

- [ ] **Step 4: Call `get_or_create_matter_folder` from `Matter.after_insert()` in `matter.py`**

The current `after_insert()` reads:

```python
    def after_insert(self):
        row = self.append("state_log", {
            "previous_state": "",
            "new_state": self.status,
            "changed_by": frappe.session.user,
            "changed_at": frappe.utils.now_datetime(),
            "reason": "Matter opened",
        })
        row.db_insert()

        frappe.db.set_value("Intake", self.intake, {
            "status": "Converted",
            "converted_matter": self.name,
        })
```

Add a call to create the Drive folder, at the top of the method:

```python
    def after_insert(self):
        from case_management.case_management.drive_integration import get_or_create_matter_folder
        get_or_create_matter_folder(self.name, self.is_restricted)

        row = self.append("state_log", {
```
(the rest of the method is unchanged — Task 6 extends this same method further)

- [ ] **Step 5: Update `on_trash()`'s guard to check the Drive folder for actual file contents, not just the legacy path**

Replace:
```python
    def on_trash(self):
        file = frappe.db.sql("select name from `tabFile` where file_name = \"Home/Clients/{0}\"".format(self.name))
        if len(file) > 0:
            frappe.throw("Sorry, Matter cannot be deleted. Case files exist for matter.")
```
with:
```python
    def on_trash(self):
        from case_management.case_management.drive_integration import get_or_create_matter_folder
        folder = get_or_create_matter_folder(self.name, self.is_restricted)
        has_files = frappe.db.exists("File", {"folder": folder, "is_folder": 0})
        if has_files:
            frappe.throw("Sorry, Matter cannot be deleted. Case files exist for matter.")
```
(The guard must check for **files inside** the folder, not merely that the folder exists — every matter's folder exists unconditionally once opened, so an existence-only check would block every deletion.)

- [ ] **Step 6: Remove the legacy per-matter folder-tree hook from `hooks.py`**

Find the line registering `doc_events["Matter"]["on_update"] = "case_management.client.update_all_matter"` (or the equivalent dict entry) and remove it. Leave `update_all_matter`/`update_customer_matter_folder_structure` in `client.py` itself, unregistered — do not delete those functions in this task.

- [ ] **Step 7: Sync and run the tests**

Run:
```bash
bench --site home.com --force reload-doc case_management doctype matter
bench --site home.com --force reload-doc case_management doctype matter_file_item
bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.matter.test_matter_drive_folder
```
Expected: PASS (4/4)

- [ ] **Step 8: Run the existing Matter test suite to confirm no regression**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.matter.test_matter_access` (and any other existing `test_matter*.py` files in this doctype's folder)
Expected: PASS, unchanged

- [ ] **Step 9: Commit**

```bash
git add case_management/case_management/doctype/matter/ case_management/hooks.py
git commit -m "feat: wire Matter File Item into Matter, create Drive folder on open, retire legacy folder tree"
```

---

### Task 4: Organize `Matter File Item` and `Intake Evidence` files into Drive on save

**Files:**
- Modify: `case_management/case_management/doctype/matter_file_item/matter_file_item.py`
- Modify: `case_management/case_management/doctype/intake_evidence/intake_evidence.py`
- Test: `case_management/case_management/doctype/matter_file_item/test_matter_file_item_drive.py`
- Test: `case_management/case_management/doctype/intake_evidence/test_intake_evidence_drive.py`

**Interfaces:**
- Consumes: `drive_integration.organize_file_in_drive(file_url, folder_name, team_name)`, `drive_integration.get_or_create_matter_folder(matter_name, is_restricted)`, `drive_integration.get_or_create_pending_intake_evidence_folder()`, `drive_integration.get_or_create_lawerp_team()` (Task 1).

- [ ] **Step 1: Write the failing test for `Matter File Item`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate


class TestMatterFileItemDrive(FrappeTestCase):
	def _make_matter(self, label="MFI Drive Test"):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": f"{label} Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)
		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": f"{label} Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)
		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)
		from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search
		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		review.decision = "Clear"
		review.save()
		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()
		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": f"{label} Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)
		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			employee = frappe.get_doc({
				"doctype": "Employee", "employee_name": f"{label} Solicitor", "status": "Active",
			}).insert(ignore_mandatory=True).name
		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": f"{label} Transaction", "responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)
		return matter

	def test_attaching_a_matter_file_organizes_it_into_the_matter_folder(self):
		from case_management.case_management.drive_integration import get_or_create_matter_folder
		matter = self._make_matter()
		test_file = frappe.get_doc({
			"doctype": "File", "file_name": "exhibit-a.pdf", "content": "x",
			"attached_to_doctype": "Matter", "attached_to_name": matter.name,
		}).insert()
		self.addCleanup(frappe.delete_doc, "File", test_file.name, force=True)

		matter.reload()
		matter.append("files", {"title": "Exhibit A", "file": test_file.file_url})
		matter.save()

		reloaded = frappe.db.get_value("File", {"file_url": test_file.file_url}, ["folder", "team"], as_dict=True)
		self.assertEqual(reloaded.folder, get_or_create_matter_folder(matter.name, matter.is_restricted))
		self.assertEqual(reloaded.team, frappe.db.get_value("File", reloaded.folder, "team"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.matter_file_item.test_matter_file_item_drive`
Expected: FAIL — the file's `folder`/`team` stay unset.

- [ ] **Step 3: Add `validate()` to `matter_file_item.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document


class MatterFileItem(Document):
	def validate(self):
		if not self.file or self.parenttype != "Matter":
			return
		from case_management.case_management.drive_integration import (
			get_or_create_matter_folder,
			organize_file_in_drive,
		)
		is_restricted = frappe.db.get_value("Matter", self.parent, "is_restricted")
		folder = get_or_create_matter_folder(self.parent, is_restricted)
		team = frappe.db.get_value("File", folder, "team")
		organize_file_in_drive(self.file, folder, team)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.matter_file_item.test_matter_file_item_drive`
Expected: PASS

- [ ] **Step 5: Write the failing tests for `Intake Evidence`, including the shared-folder filename-collision case**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase


class TestIntakeEvidenceDrive(FrappeTestCase):
	def test_attaching_intake_evidence_organizes_it_into_pending_evidence_folder(self):
		from case_management.case_management.drive_integration import get_or_create_pending_intake_evidence_folder

		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "Intake Evidence Drive Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		test_file = frappe.get_doc({
			"doctype": "File", "file_name": "intake-evidence.pdf", "content": "x",
		}).insert()
		self.addCleanup(frappe.delete_doc, "File", test_file.name, force=True)

		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
			"evidence": [{"attachment": test_file.file_url}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)

		reloaded = frappe.db.get_value("File", {"file_url": test_file.file_url}, "folder")
		self.assertEqual(reloaded, get_or_create_pending_intake_evidence_folder())

	def test_two_intakes_with_same_evidence_filename_do_not_clobber_each_others_file_record(self):
		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "Collision Drive Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)

		file_a = frappe.get_doc({"doctype": "File", "file_name": "evidence.pdf", "content": "content A"}).insert()
		self.addCleanup(frappe.delete_doc, "File", file_a.name, force=True)
		file_b = frappe.get_doc({"doctype": "File", "file_name": "evidence.pdf", "content": "content B"}).insert()
		self.addCleanup(frappe.delete_doc, "File", file_b.name, force=True)
		self.assertNotEqual(file_a.name, file_b.name)
		self.assertNotEqual(file_a.file_url, file_b.file_url)

		intake_a = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
			"evidence": [{"attachment": file_a.file_url}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake_a.name, force=True)
		intake_b = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
			"evidence": [{"attachment": file_b.file_url}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake_b.name, force=True)

		reloaded_a = frappe.db.get_value("File", file_a.name, ["folder", "content_hash"], as_dict=True)
		reloaded_b = frappe.db.get_value("File", file_b.name, ["folder", "content_hash"], as_dict=True)
		self.assertEqual(reloaded_a.folder, reloaded_b.folder)
		self.assertNotEqual(reloaded_a.content_hash, reloaded_b.content_hash)
		self.assertEqual(frappe.get_doc("File", file_a.name).get_content(), b"content A")
		self.assertEqual(frappe.get_doc("File", file_b.name).get_content(), b"content B")

	def test_escalated_reviews_evidence_is_not_organized_into_drive(self):
		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "Escalated IE Drive Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)
		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)
		from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search
		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		review.decision = "Restricted Match - Escalated"
		review.save()

		test_file = frappe.get_doc({"doctype": "File", "file_name": "escalated-intake-evidence.pdf", "content": "x"}).insert()
		self.addCleanup(frappe.delete_doc, "File", test_file.name, force=True)
		intake.reload()
		intake.append("evidence", {"attachment": test_file.file_url})
		intake.save()

		self.assertIsNone(frappe.db.get_value("File", test_file.name, "team"))
```

`File.get_content()`/`content_hash` confirm the two same-named files stay genuinely distinct records with distinct content — not just distinct `name`s with one's bytes silently overwritten.

- [ ] **Step 6: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.intake_evidence.test_intake_evidence_drive`
Expected: FAIL (the collision/escalated tests should already incidentally pass against a no-op implementation, but the first test fails; implement all three together)

- [ ] **Step 7: Add `validate()` to `intake_evidence.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document


class IntakeEvidence(Document):
	def validate(self):
		if not self.attachment:
			return
		escalated = frappe.db.get_value(
			"Conflict Review", {"intake": self.parent}, "decision"
		) == "Restricted Match - Escalated"
		if escalated:
			return
		from case_management.case_management.drive_integration import (
			get_or_create_pending_intake_evidence_folder,
			get_or_create_lawerp_team,
			organize_file_in_drive,
		)
		organize_file_in_drive(
			self.attachment, get_or_create_pending_intake_evidence_folder(), get_or_create_lawerp_team()
		)
```

- [ ] **Step 8: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.intake_evidence.test_intake_evidence_drive`
Expected: PASS (3/3)

- [ ] **Step 9: Commit**

```bash
git add case_management/case_management/doctype/matter_file_item/ case_management/case_management/doctype/intake_evidence/
git commit -m "feat: organize Matter File Item and Intake Evidence files into Drive on save"
```

---

### Task 5: `Conflict Review` waiver evidence — Drive organization, kept out of Drive while escalated

**Files:**
- Modify: `case_management/case_management/doctype/conflict_review/conflict_review.py`
- Test: `case_management/case_management/doctype/conflict_review/test_conflict_review_drive.py`

**Interfaces:**
- Consumes: `drive_integration.organize_file_in_drive`, `drive_integration.get_or_create_pending_intake_evidence_folder`, `drive_integration.get_or_create_lawerp_team` (Task 1).
- Produces: nothing a later task calls directly — Task 6's relocation reads the same `waiver_evidence`/`Intake Evidence.attachment` fields this task writes to, not a function this task exports.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.tests.utils import FrappeTestCase


class TestConflictReviewDrive(FrappeTestCase):
	def _make_intake_with_review(self, label="Conflict Review Drive Test"):
		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": f"{label} Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)
		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)
		from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search
		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		return intake, frappe.get_doc("Conflict Review", review_name)

	def test_waiver_evidence_is_organized_into_pending_evidence_folder(self):
		from case_management.case_management.drive_integration import get_or_create_pending_intake_evidence_folder
		intake, review = self._make_intake_with_review()
		test_file = frappe.get_doc({"doctype": "File", "file_name": "waiver.pdf", "content": "x"}).insert()
		self.addCleanup(frappe.delete_doc, "File", test_file.name, force=True)

		review.decision = "Waiver Granted"
		review.waiver_evidence = test_file.file_url
		review.save()

		reloaded = frappe.db.get_value("File", {"file_url": test_file.file_url}, "folder")
		self.assertEqual(reloaded, get_or_create_pending_intake_evidence_folder())

	def test_escalated_review_does_not_organize_waiver_evidence_into_drive(self):
		intake, review = self._make_intake_with_review(label="Escalated Drive Test")
		test_file = frappe.get_doc({"doctype": "File", "file_name": "escalated-waiver.pdf", "content": "x"}).insert()
		self.addCleanup(frappe.delete_doc, "File", test_file.name, force=True)

		review.decision = "Restricted Match - Escalated"
		review.waiver_evidence = test_file.file_url
		review.save()

		self.assertIsNone(frappe.db.get_value("File", {"file_url": test_file.file_url}, "team"))

	def test_escalating_an_already_organized_review_pulls_evidence_back_out_of_drive(self):
		intake, review = self._make_intake_with_review(label="Escalate Later Drive Test")
		test_file = frappe.get_doc({"doctype": "File", "file_name": "later-waiver.pdf", "content": "x"}).insert()
		self.addCleanup(frappe.delete_doc, "File", test_file.name, force=True)

		review.decision = "Waiver Granted"
		review.waiver_evidence = test_file.file_url
		review.save()
		self.assertIsNotNone(frappe.db.get_value("File", {"file_url": test_file.file_url}, "team"))

		review.decision = "Restricted Match - Escalated"
		review.save()
		self.assertIsNone(frappe.db.get_value("File", {"file_url": test_file.file_url}, "team"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.conflict_review.test_conflict_review_drive`
Expected: FAIL — `waiver_evidence` is never organized; escalation never withdraws it.

- [ ] **Step 3: Add the Drive logic to `conflict_review.py`**

The current file's `validate()` reads `self._validate_decision_authority()`. Extend it:

```python
	def validate(self):
		self._validate_decision_authority()
		self._organize_waiver_evidence()
		self._withdraw_evidence_from_drive_if_escalated()

	def _organize_waiver_evidence(self):
		if not self.waiver_evidence or self.decision == "Restricted Match - Escalated":
			return
		from case_management.case_management.drive_integration import (
			get_or_create_pending_intake_evidence_folder,
			get_or_create_lawerp_team,
			organize_file_in_drive,
		)
		organize_file_in_drive(
			self.waiver_evidence, get_or_create_pending_intake_evidence_folder(), get_or_create_lawerp_team()
		)

	def _withdraw_evidence_from_drive_if_escalated(self):
		if self.decision != "Restricted Match - Escalated":
			return
		file_urls = [self.waiver_evidence] if self.waiver_evidence else []
		file_urls += [
			row.attachment for row in frappe.get_all(
				"Intake Evidence", filters={"parent": self.intake}, fields=["attachment"]
			) if row.attachment
		]
		for file_url in file_urls:
			frappe.db.set_value(
				"File", {"file_url": file_url}, {"team": None, "folder": None}, update_modified=False,
			)
```

(`PRIVILEGED_ROLES` is not imported here — escalated evidence is kept out of Drive entirely rather than narrowed inside it, per the spec's corrected mechanism.)

- [ ] **Step 4: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.conflict_review.test_conflict_review_drive`
Expected: PASS (3/3)

- [ ] **Step 5: Run the existing Conflict Review test suite to confirm no regression**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.conflict_review.test_conflict_review` (and any other existing test files in this doctype's folder)
Expected: PASS, unchanged

- [ ] **Step 6: Commit**

```bash
git add case_management/case_management/doctype/conflict_review/
git commit -m "feat: organize waiver evidence into Drive, withdraw it on escalation"
```

---

### Task 6: Restricted matters get their own Drive Team; pre-matter evidence relocates on open

**Files:**
- Modify: `case_management/case_management/doctype/matter/matter.py`
- Test: `case_management/case_management/doctype/matter/test_matter_drive_folder.py` (same file as Task 3, new test methods)

**Interfaces:**
- Consumes: `drive_integration.get_or_create_matter_folder(matter_name, is_restricted)`, `drive_integration.get_or_create_matter_team(matter_name)`, `drive_integration.sync_team_membership(team_name, user_emails)` (Task 1); `matter.py`'s existing `has_permission()` membership logic (mirrored, not called directly, since `has_permission` takes a `user` and answers yes/no for one user, while this needs the full set of users to grant).

- [ ] **Step 1: Write the failing test**

Append to `case_management/case_management/doctype/matter/test_matter_drive_folder.py`:

```python
	def test_restricted_matter_gets_its_own_dedicated_drive_team_with_correct_membership(self):
		matter = self._make_matter(label="Restricted Drive Test")
		matter.is_restricted = 1
		matter.save()

		from case_management.case_management.drive_integration import get_or_create_matter_team
		team = get_or_create_matter_team(matter.name)
		members = set(frappe.get_all("Drive Team Member", filters={"parent": team}, pluck="user"))

		responsible_user = frappe.db.get_value("Employee", matter.responsible_solicitor, "user_id")
		self.assertIn(responsible_user, members)

	def test_non_restricted_matter_folder_stays_in_the_shared_lawerp_team(self):
		matter = self._make_matter(label="Open Drive Test")
		from case_management.case_management.drive_integration import get_or_create_matter_folder, get_or_create_lawerp_team
		folder = get_or_create_matter_folder(matter.name, matter.is_restricted)
		self.assertEqual(frappe.db.get_value("File", folder, "team"), get_or_create_lawerp_team())

	def test_toggling_is_restricted_after_the_matter_has_a_file_moves_folder_and_file_to_the_dedicated_team(self):
		matter = self._make_matter(label="Toggle Drive Test")
		test_file = frappe.get_doc({
			"doctype": "File", "file_name": "pre-toggle.pdf", "content": "x",
			"attached_to_doctype": "Matter", "attached_to_name": matter.name,
		}).insert()
		self.addCleanup(frappe.delete_doc, "File", test_file.name, force=True)
		matter.reload()
		matter.append("files", {"title": "Pre Toggle", "file": test_file.file_url})
		matter.save()

		matter.is_restricted = 1
		matter.save()

		from case_management.case_management.drive_integration import get_or_create_matter_folder, get_or_create_matter_team
		dedicated_team = get_or_create_matter_team(matter.name)
		folder = get_or_create_matter_folder(matter.name, True)
		self.assertEqual(frappe.db.get_value("File", folder, "team"), dedicated_team)
		self.assertEqual(frappe.db.get_value("File", test_file.name, "team"), dedicated_team)

	def test_waiver_evidence_is_relocated_into_the_matter_folder_and_team_on_open(self):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "Relocation Test Customer", "customer_type": "Company",
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Customer", customer.name, force=True)
		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "Relocation Test Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)
		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)
		from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search
		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)

		test_file = frappe.get_doc({"doctype": "File", "file_name": "waiver-relocate.pdf", "content": "x"}).insert()
		self.addCleanup(frappe.delete_doc, "File", test_file.name, force=True)
		review.decision = "Waiver Granted"
		review.waiver_evidence = test_file.file_url
		review.save()

		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()
		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "Relocation Test Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)
		employee = frappe.db.get_value("Employee", {}, "name")
		matter = frappe.get_doc({
			"doctype": "Matter", "client": customer.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": "Relocation Test Transaction", "responsible_solicitor": employee,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		from case_management.case_management.drive_integration import get_or_create_matter_folder
		folder = get_or_create_matter_folder(matter.name, matter.is_restricted)
		reloaded = frappe.db.get_value("File", {"file_url": test_file.file_url}, ["folder", "team"], as_dict=True)
		self.assertEqual(reloaded.folder, folder)
		self.assertEqual(reloaded.team, frappe.db.get_value("File", folder, "team"))

	def test_escalated_evidence_lands_directly_in_a_restricted_matters_dedicated_team_on_open(self):
		client = frappe.get_doc({
			"doctype": "Legal Party", "party_name": "Escalated Relocation Client", "party_type": "Organization",
		}).insert()
		self.addCleanup(frappe.delete_doc, "Legal Party", client.name, force=True)
		intake = frappe.get_doc({
			"doctype": "Intake", "proposed_client": client.name, "scope": "Advisory",
			"parties": [{"legal_party": client.name, "role": "Proposed Client"}],
		}).insert()
		self.addCleanup(frappe.delete_doc, "Intake", intake.name, force=True)
		from case_management.case_management.doctype.conflict_review.conflict_review import run_conflict_search
		review_name = run_conflict_search(intake.name)
		self.addCleanup(frappe.delete_doc, "Conflict Review", review_name, force=True)
		review = frappe.get_doc("Conflict Review", review_name)
		test_file = frappe.get_doc({"doctype": "File", "file_name": "escalated-relocate.pdf", "content": "x"}).insert()
		self.addCleanup(frappe.delete_doc, "File", test_file.name, force=True)
		review.decision = "Restricted Match - Escalated"
		review.waiver_evidence = test_file.file_url
		review.save()
		self.assertIsNone(frappe.db.get_value("File", test_file.name, "team"))

		intake.status = "Under Review"
		intake.save()
		intake.status = "Approved"
		intake.save()
		practice_area = frappe.get_doc({"doctype": "Practice Area", "practice_area": "Escalated Relocation Practice Area"}).insert()
		self.addCleanup(frappe.delete_doc, "Practice Area", practice_area.name, force=True)
		employee = frappe.db.get_value("Employee", {}, "name")
		matter = frappe.get_doc({
			"doctype": "Matter", "client": client.name, "intake": intake.name, "status": "Open",
			"open_date": nowdate(), "practice_area": practice_area.name,
			"transaction": "Escalated Relocation Transaction", "responsible_solicitor": employee,
			"is_restricted": 1,
		}).insert()
		self.addCleanup(frappe.delete_doc, "Matter", matter.name, force=True)

		from case_management.case_management.drive_integration import get_or_create_matter_team
		dedicated_team = get_or_create_matter_team(matter.name)
		self.assertEqual(frappe.db.get_value("File", test_file.name, "team"), dedicated_team)

	def test_opening_a_matter_with_no_waiver_or_intake_evidence_does_not_throw(self):
		# _make_matter's own intake has a Clear review with no waiver_evidence and no
		# Intake Evidence rows -- this is already exercised by every other test in this
		# file succeeding, but assert it directly as the documented common case.
		matter = self._make_matter(label="No Evidence Drive Test")
		self.assertTrue(frappe.db.exists("Matter", matter.name))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.matter.test_matter_drive_folder`
Expected: FAIL — no dedicated team gets created for restricted matters; waiver/escalated evidence doesn't relocate with a correct `team`.

- [ ] **Step 3: Add team-membership sync and relocation to `matter.py`**

`get_or_create_matter_folder` needs the Matter's final `name`, which for a new document (this doctype defines its own `autoname()`) is only guaranteed set *after* `insert()` completes — not during `validate()`, which runs before naming on a new document. So the sync call lives in `after_insert()` (the creation case) and a new `on_update()` method (every later edit — e.g. `is_restricted` or `legal_team` changing), never in `validate()`.

Add `on_update()`:

```python
    def on_update(self):
        self._sync_drive_team_membership()
```

Add `_sync_drive_team_membership()`:

```python
    def _sync_drive_team_membership(self):
        from case_management.case_management.drive_integration import (
            get_or_create_matter_folder,
            get_or_create_matter_team,
            sync_team_membership,
        )
        get_or_create_matter_folder(self.name, self.is_restricted)
        if not self.is_restricted:
            return
        team = get_or_create_matter_team(self.name)
        users = set()
        if self.responsible_solicitor:
            user_id = frappe.db.get_value("Employee", self.responsible_solicitor, "user_id")
            if user_id:
                users.add(user_id)
        for row in self.legal_team:
            user_id = frappe.db.get_value("Employee", row.employee, "user_id")
            if user_id:
                users.add(user_id)
        sync_team_membership(team, users)
```

Then extend `after_insert()` (already modified in Task 3) to also relocate pre-matter evidence and sync membership, after the folder-creation line already added there:

```python
    def after_insert(self):
        from case_management.case_management.drive_integration import get_or_create_matter_folder
        get_or_create_matter_folder(self.name, self.is_restricted)
        self._relocate_pending_evidence()
        self._sync_drive_team_membership()

        row = self.append("state_log", {
            ...
        })
        ... # rest unchanged
```

Add `_relocate_pending_evidence()`:

```python
    def _relocate_pending_evidence(self):
        if not self.intake:
            return
        from case_management.case_management.drive_integration import get_or_create_matter_folder
        matter_folder = get_or_create_matter_folder(self.name, self.is_restricted)
        matter_team = frappe.db.get_value("File", matter_folder, "team")

        reviews = frappe.get_all(
            "Conflict Review", filters={"intake": self.intake}, fields=["waiver_evidence"]
        )
        evidence_rows = frappe.get_all(
            "Intake Evidence", filters={"parent": self.intake}, fields=["attachment"]
        )
        file_urls = [r.waiver_evidence for r in reviews if r.waiver_evidence]
        file_urls += [r.attachment for r in evidence_rows if r.attachment]

        for file_url in file_urls:
            file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
            if file_name:
                frappe.db.set_value(
                    "File", file_name, {"folder": matter_folder, "team": matter_team}, update_modified=False,
                )
```

(Setting `team` here, not just `folder`, is what makes this correct both for ordinary pre-matter evidence moving out of the shared `Pending Intake Evidence`/`LawERP` pairing, and for escalated evidence that had neither field set at all before this point.)

- [ ] **Step 4: Sync and run the tests**

Run:
```bash
bench --site home.com --force reload-doc case_management doctype matter
bench --site home.com run-tests --skip-test-records --module case_management.case_management.doctype.matter.test_matter_drive_folder
```
Expected: PASS (9/9, all tests in this file across Task 3 and Task 6)

- [ ] **Step 5: Run the full app test suite to confirm no regression anywhere**

Run: `bench --site home.com run-tests --skip-test-records --app case_management`
Expected: PASS, no failures

- [ ] **Step 6: Commit**

```bash
git add case_management/case_management/doctype/matter/
git commit -m "feat: give restricted matters their own Drive Team, relocate pre-matter evidence on open"
```

---

### Task 7: Sync every employee into the firm-wide `LawERP` Drive Team

**Files:**
- Modify: `case_management/case_management/drive_integration.py`
- Modify: `case_management/hooks.py`
- Test: `case_management/case_management/test_drive_integration.py` (same file as Task 1, new test class)

**Interfaces:**
- Consumes: `get_or_create_lawerp_team()`, `sync_team_membership()` (Task 1).

Drive's `Drive Team.after_insert()` only ever adds the team's *creator* as a member — nobody else. Without this task, a non-restricted matter's folder is unreachable to anyone but whoever happened to trigger `LawERP`'s creation, since Drive's access grant is team-membership-based (see Global Constraints). This task keeps `LawERP`'s membership in step with every `Employee` that has a linked `User`.

- [ ] **Step 1: Write the failing test**

```python
class TestLawerpTeamMembershipSync(FrappeTestCase):
	def test_creating_an_employee_with_a_linked_user_adds_them_to_the_lawerp_team(self):
		from case_management.case_management.drive_integration import get_or_create_lawerp_team
		user = frappe.get_doc({
			"doctype": "User", "email": "drive-team-sync-test@example.com", "first_name": "Drive",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User", user.name, force=True)
		employee = frappe.get_doc({
			"doctype": "Employee", "employee_name": "Drive Team Sync Test", "status": "Active",
			"user_id": user.name,
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Employee", employee.name, force=True)

		team = get_or_create_lawerp_team()
		members = frappe.get_all("Drive Team Member", filters={"parent": team}, pluck="user")
		self.assertIn(user.name, members)

	def test_syncing_one_employee_does_not_remove_an_existing_unrelated_member(self):
		from case_management.case_management.drive_integration import get_or_create_lawerp_team, sync_team_membership
		team = get_or_create_lawerp_team()
		sync_team_membership(team, {"pre-existing-member@example.com"})

		user = frappe.get_doc({
			"doctype": "User", "email": "drive-team-sync-test-2@example.com", "first_name": "Drive",
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User", user.name, force=True)
		employee = frappe.get_doc({
			"doctype": "Employee", "employee_name": "Drive Team Sync Test 2", "status": "Active",
			"user_id": user.name,
		}).insert(ignore_mandatory=True)
		self.addCleanup(frappe.delete_doc, "Employee", employee.name, force=True)

		members = set(frappe.get_all("Drive Team Member", filters={"parent": team}, pluck="user"))
		self.assertIn("pre-existing-member@example.com", members)
		self.assertIn(user.name, members)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.test_drive_integration`
Expected: FAIL — no hook adds the new employee's user to `LawERP`.

- [ ] **Step 3: Add `sync_employee_into_lawerp_team` to `drive_integration.py`**

```python
def sync_employee_into_lawerp_team(doc, event=None):
	if not doc.user_id:
		return
	team = get_or_create_lawerp_team()
	current = {row.user for row in frappe.get_all("Drive Team Member", filters={"parent": team}, fields=["user"])}
	if doc.user_id in current:
		return
	sync_team_membership(team, current | {doc.user_id})
```

- [ ] **Step 4: Register the hook in `hooks.py`**

Add (merging into the existing `doc_events` dict, not replacing it):

```python
doc_events = {
    ...,
    "Employee": {
        "after_insert": "case_management.case_management.drive_integration.sync_employee_into_lawerp_team",
        "on_update": "case_management.case_management.drive_integration.sync_employee_into_lawerp_team",
    },
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `bench --site home.com run-tests --skip-test-records --module case_management.case_management.test_drive_integration`
Expected: PASS (2/2 new, plus all earlier tests in this module)

- [ ] **Step 6: Run the full app test suite to confirm no regression anywhere**

Run: `bench --site home.com run-tests --skip-test-records --app case_management`
Expected: PASS, no failures

- [ ] **Step 7: Commit**

```bash
git add case_management/case_management/drive_integration.py case_management/hooks.py case_management/case_management/test_drive_integration.py
git commit -m "feat: sync every employee into the firm-wide LawERP Drive Team"
```
