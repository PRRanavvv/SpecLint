import unittest

from fastapi.testclient import TestClient

from backend.app.analyzer import SpecInputError, analyze_spec
from backend.app.main import app


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
        self.assertEqual(payload["score_breakdown"]["base_score"], 100)
        self.assertIn("severity_counts", payload)
        self.assertTrue(payload["issues"])
        self.assertTrue(payload["rewritten_spec"])

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
        self.assertIn("product requirement", response.json()["detail"])

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
