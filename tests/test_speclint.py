from datetime import date, timedelta
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

test_db = tempfile.NamedTemporaryFile(delete=False)
test_db.close()
os.environ["SPECLINT_DB_PATH"] = test_db.name

from backend.app.analyzer import SpecInputError, analyze_spec
from backend.app.main import app
from backend.app.models import Strictness


class SpecLintTests(unittest.TestCase):
    def test_invite_spec_flags_missing_edges(self):
        report = analyze_spec(
            title="Workspace invites",
            spec_text="Users can invite teammates to a workspace. Guests can view projects.",
        )

        issue_titles = {issue.title for issue in report.issues}
        self.assertIn("Permission boundary is underspecified", issue_titles)
        self.assertIn("Invitation lifecycle is incomplete", issue_titles)
        self.assertGreaterEqual(len(report.acceptance_tests), 3)
        self.assertLess(report.score, 90)

    def test_api_returns_compiler_style_report(self):
        client = TestClient(app)
        response = client.post(
            "/api/analyze",
            json={
                "title": "Exports",
                "spec_text": "Users should be able to quickly export all data.",
                "strictness": "balanced",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("score", payload)
        self.assertIn("spec_version_id", payload)
        self.assertEqual(payload["score_breakdown"]["base_score"], 100)
        self.assertIn("severity_counts", payload)
        self.assertTrue(payload["issues"])
        self.assertTrue(payload["rewritten_spec"])

    def test_suppression_decision_log_can_accept_and_reopen_risk(self):
        client = TestClient(app)
        analysis = client.post(
            "/api/analyze",
            json={
                "title": "Team member removal",
                "spec_text": (
                    "Admins can remove members from a workspace. "
                    "Removed members lose access immediately and the team is notified. "
                    "The process should be simple."
                ),
                "strictness": "ruthless",
            },
        )

        self.assertEqual(analysis.status_code, 200)
        report = analysis.json()
        issue = next(item for item in report["issues"] if item["type"] == "permission_gap")
        expires_at = (date.today() + timedelta(days=30)).isoformat()
        created = client.post(
            "/api/suppressions",
            json={
                "spec_version_id": report["spec_version_id"],
                "issue_id": issue["id"],
                "issue_type": issue["type"],
                "severity": issue["severity"],
                "issue_title": issue["title"],
                "evidence_snapshot": issue["evidence"],
                "owner": "Product Owner",
                "reason": "MVP only supports single-admin workspaces for the first release.",
                "expires_at": expires_at,
                "created_by": "Product Owner",
            },
        )

        self.assertEqual(created.status_code, 200)
        suppression = created.json()
        self.assertEqual(suppression["status"], "active")
        self.assertEqual(suppression["issue_id"], issue["id"])
        self.assertLessEqual(len(suppression["evidence_snapshot"]), 240)

        listed = client.get(
            "/api/suppressions",
            params={"spec_version_id": report["spec_version_id"], "status": "active"},
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

        reopened = client.patch(
            f"/api/suppressions/{suppression['id']}/reopen",
            json={
                "reopened_by": "Security Reviewer",
                "reopened_reason": "Workspace ownership rules changed.",
            },
        )

        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["status"], "reopened")
        self.assertEqual(reopened.json()["reopened_reason"], "Workspace ownership rules changed.")

    def test_requirement_decisions_can_be_logged_and_exported(self):
        client = TestClient(app)
        analysis = client.post(
            "/api/analyze",
            json={
                "title": "Workspace ownership",
                "spec_text": (
                    "Workspace owners can transfer ownership to another member. "
                    "The new owner gets admin access immediately. "
                    "The process should be simple."
                ),
            },
        )

        self.assertEqual(analysis.status_code, 200)
        report = analysis.json()
        issue = next(item for item in report["issues"] if item["type"] == "consent_gap")
        created = client.post(
            "/api/decisions",
            json={
                "spec_version_id": report["spec_version_id"],
                "issue_id": issue["id"],
                "issue_type": issue["type"],
                "severity": issue["severity"],
                "issue_title": issue["title"],
                "evidence_snapshot": issue["evidence"],
                "owner": "Product Lead",
                "decision_note": "Receiving owner must accept before transfer takes effect.",
                "created_by": "Product Lead",
            },
        )

        self.assertEqual(created.status_code, 200)
        decision = created.json()
        self.assertEqual(decision["status"], "decided")
        self.assertEqual(decision["issue_id"], issue["id"])
        self.assertLessEqual(len(decision["evidence_snapshot"]), 240)

        listed = client.get(
            "/api/decisions",
            params={"spec_version_id": report["spec_version_id"]},
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

        exported = client.get(
            "/api/decisions/export",
            params={"spec_version_id": report["spec_version_id"]},
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn("Receiving owner must accept", exported.text)
        self.assertIn("SpecLint Requirements Decisions", exported.text)

    def test_public_share_links_flag_lifecycle_and_do_not_treat_signing_in_as_action(self):
        report = analyze_spec(
            title="Public share links",
            spec_text=(
                "Users can share any project with a public link. "
                "The link should be easy to copy and safe to use. "
                "Viewers can open the project without signing in."
            ),
            strictness=Strictness.ruthless,
        )

        issue_titles = {issue.title for issue in report.issues}
        self.assertIn("Permission boundary is underspecified", issue_titles)
        self.assertIn("Public link lifecycle is incomplete", issue_titles)
        self.assertIn("Security and abuse controls are unstated", issue_titles)
        self.assertIn("open", report.intent.actions)
        self.assertIn("share", report.intent.actions)
        self.assertNotIn("sign", report.intent.actions)
        self.assertLess(report.score, 35)

    def test_rejects_placeholder_noise_before_linting(self):
        noisy_text = (
            "aaknjdn fskjdfkjn dsknkan dlj fpowejf sdvnlnwoe fslncv lsdf "
            "ejadcmsdkf jolsnlfmds mflsndf lsndfl nsdln skdf kalf lkdnf."
        )
        with self.assertRaises(SpecInputError):
            analyze_spec(title="blah blah potato hehe", spec_text=noisy_text)

        client = TestClient(app)
        response = client.post(
            "/api/analyze",
            json={
                "title": "blah blah potato hehe",
                "spec_text": noisy_text,
                "strictness": "ruthless",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "IMPROPER INPUT")

    def test_rejects_text_with_no_extractable_requirement_intent(self):
        client = TestClient(app)
        response = client.post(
            "/api/analyze",
            json={
                "title": "dsf",
                "spec_text": (
                    "skjdi hsdfn shfd sdho fskldf jsriio jorijgsljfgsjrfigo slkf jls "
                    "lsjd iosjfljsirj gsjvoijpf wljfpw4j4 35slf wsdf lksnv sj "
                    "lsfklwjsdlf nvslk lksls glwsrflksjdlv jsgjiperjg sio js jsl osnv"
                ),
                "strictness": "balanced",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "IMPROPER INPUT")

    def test_unless_clause_is_not_contradiction_by_default(self):
        report = analyze_spec(
            title="Project deletion",
            spec_text=(
                "Project owners can delete projects. "
                "All project data is removed unless billing records must be kept. "
                "The user gets a confirmation."
            ),
        )

        self.assertNotIn("contradiction", {issue.type.value for issue in report.issues})
        self.assertIn("score_breakdown", report.model_dump())

    def test_ownership_transfer_requires_receiver_consent(self):
        report = analyze_spec(
            title="Transfer workspace ownership",
            spec_text=(
                "The current workspace owner can transfer ownership to another team member. "
                "The new owner gets full admin access and the previous owner becomes a regular member. "
                "The system sends a confirmation email to both parties. "
                "Ownership transfer is permanent."
            ),
        )

        issue_types = {issue.type.value for issue in report.issues}
        self.assertIn("consent_gap", issue_types)
        self.assertEqual(report.severity_counts["critical"], 1)
        self.assertLess(report.score, 75)
        self.assertIn("transfer", report.intent.actions)
        self.assertIn("send", report.intent.actions)
        self.assertIn("Primary object: workspace ownership.", report.rewritten_spec)
        self.assertNotIn("action the email", report.rewritten_spec)
        self.assertTrue(
            any("receiving party has not accepted" in test.when for test in report.acceptance_tests)
        )

    def test_destructive_deletion_confirmation_and_shared_content_are_flagged(self):
        report = analyze_spec(
            title="User account deletion",
            spec_text=(
                "Members can delete their account from settings. "
                "The user receives a confirmation email before deletion is processed. "
                "All personal data is removed, but shared content remains visible to other team members. "
                "The action cannot be undone."
            ),
        )

        issue_titles = {issue.title for issue in report.issues}
        issue_types = {issue.type.value for issue in report.issues}
        self.assertIn("Destructive confirmation consent is ambiguous", issue_titles)
        self.assertIn("Shared content ownership after deletion is undefined", issue_titles)
        self.assertIn("consent_gap", issue_types)
        self.assertIn("lifecycle_gap", issue_types)
        self.assertLess(report.score, 70)

    def test_traceability_uses_source_spec_when_current_draft_is_rewritten(self):
        source_spec = (
            "Members can delete their account from settings. "
            "The user receives a confirmation email before deletion is processed."
        )
        rewritten_draft = (
            "# User account deletion\n\n"
            "Primary actor: member.\n"
            "Primary object: account.\n"
            "Rules:\n"
            "- The user must confirm deletion before processing."
        )
        report = analyze_spec(
            title="User account deletion",
            spec_text=rewritten_draft,
            source_spec_text=source_spec,
        )

        requirements = [item.requirement for item in report.traceability]
        self.assertTrue(requirements[0].startswith("R1: Members can delete their account"))
        self.assertNotIn("Primary actor", " ".join(requirements))

    def test_project_invite_flags_member_removal_and_better_failure_evidence(self):
        report = analyze_spec(
            title="Invite someone to a project",
            spec_text=(
                "Project admins can invite people to join their project by entering an email address. "
                "The invited person gets an email with a link to join. "
                "If they don't have an account they'll be prompted to sign up first. "
                "Admins can also remove people from the project whenever they want. "
                "Members can see who else is in the project."
            ),
        )

        issue_titles = {issue.title for issue in report.issues}
        self.assertIn("Member removal lifecycle is undefined", issue_titles)
        failure_issue = next(
            issue for issue in report.issues if issue.title == "Failure behavior is not specified"
        )
        self.assertIn("email with a link", failure_issue.evidence)
        self.assertNotIn("Members can see who else is in the project", failure_issue.evidence)

    def test_member_removal_uses_specific_scope_issue_instead_of_generic_permission_and_data_noise(self):
        report = analyze_spec(
            title="Team member removal",
            spec_text=(
                "Admins can remove members from a workspace. "
                "Removed members lose access immediately and the team is notified. "
                "The process should be simple."
            ),
            strictness=Strictness.ruthless,
        )

        issue_titles = {issue.title for issue in report.issues}
        self.assertIn("Member removal lifecycle is undefined", issue_titles)
        self.assertIn("Protected member removal rules are undefined", issue_titles)
        self.assertIn("Security and abuse controls are unstated", issue_titles)
        self.assertNotIn("Permission boundary is underspecified", issue_titles)
        self.assertNotIn("Data constraints are missing", issue_titles)
        self.assertEqual(report.intent.actions, ["remove"])
        self.assertLess(report.score, 35)

    def test_password_reset_flags_security_and_token_lifecycle_gaps(self):
        report = analyze_spec(
            title="Password reset",
            spec_text=(
                "If a user forgets their password they can request a reset link from the login page. "
                "We'll send them an email with a link that lets them set a new password. "
                "The link should expire after some time. "
                "Users can't reuse their old password. "
                "Once they reset it they're logged in automatically."
            ),
        )

        issue_titles = {issue.title for issue in report.issues}
        self.assertIn("Reset link lifecycle is incomplete", issue_titles)
        self.assertIn("Password reset identity disclosure is undefined", issue_titles)
        self.assertIn("Password reuse rule is underspecified", issue_titles)
        self.assertIn("Post-reset session behavior is undefined", issue_titles)
        self.assertIn("Unverifiable language needs a measurable target", issue_titles)
        self.assertLess(report.score, 40)
        self.assertEqual(report.verdict, "does_not_compile")
        self.assertIn("Primary object: password reset token.", report.rewritten_spec)
        self.assertNotIn("reset the password reset token", report.rewritten_spec)

    def test_file_upload_prefers_file_and_flags_shared_delete_gaps(self):
        report = analyze_spec(
            title="File upload",
            spec_text=(
                "Users can upload files to their project. "
                "We support common file types and the upload should be reasonably fast. "
                "If the upload fails they'll see an error. "
                "Files can be shared with other project members and deleted by whoever uploaded them. "
                "Deleted files are gone permanently."
            ),
        )

        issue_titles = {issue.title for issue in report.issues}
        self.assertIn("Supported file types are undefined", issue_titles)
        self.assertIn("File deletion permissions are underspecified", issue_titles)
        self.assertIn("Shared file deletion semantics conflict", issue_titles)
        self.assertIn("Unverifiable language needs a measurable target", issue_titles)
        self.assertEqual(report.verdict, "does_not_compile")
        self.assertIn("delete", report.intent.actions)
        self.assertIn("share", report.intent.actions)
        self.assertIn("upload", report.intent.actions)
        self.assertIn("Primary object: file.", report.rewritten_spec)
        self.assertNotIn("upload the project", report.rewritten_spec)
        self.assertTrue(
            any("upload the file" in test.when for test in report.acceptance_tests)
        )

    def test_primary_object_uses_action_receivers_and_never_actor_fallback(self):
        review_report = analyze_spec(
            title="Review moderation",
            spec_text="Users can edit, delete, and share a review.",
        )
        member_report = analyze_spec(
            title="Team members",
            spec_text="Admins can invite, remove, and manage members.",
        )
        vague_report = analyze_spec(
            title="Vague workflow",
            spec_text="Users can view and edit whenever needed.",
        )

        self.assertIn("Primary object: review.", review_report.rewritten_spec)
        self.assertIn("Primary object: member.", member_report.rewritten_spec)
        self.assertIn("Primary object: unspecified.", vague_report.rewritten_spec)
        self.assertIn(
            "Primary object could not be determined. Spec may be too vague to compile.",
            {issue.title for issue in vague_report.issues},
        )
        self.assertEqual(vague_report.verdict, "does_not_compile")
        self.assertNotIn("Primary object: user.", vague_report.rewritten_spec)
        self.assertTrue(
            any("complete the requested action" in test.when for test in vague_report.acceptance_tests)
        )


if __name__ == "__main__":
    unittest.main()
