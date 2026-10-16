"""Failure-mode checks for the dependency-free static source gate."""

import importlib.util
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "verify_static_site", Path(__file__).with_name("verify-static-site.py")
)
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class StaticSourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for page in VERIFY.ENTRYPOINTS:
            (self.root / page).write_text(
                '<html><head><title>Fixture</title></head><body>'
                '<img src="asset%20name.png?v=1#fragment">'
                '<script src="js/main.js"></script></body></html>'
            )
        (self.root / "asset name.png").write_bytes(b"fixture")
        (self.root / "js").mkdir()
        for name in VERIFY.JAVASCRIPT:
            (self.root / name).write_text("const fixture = 1;\n")

    def test_valid_local_resources_and_javascript(self):
        self.assertEqual(VERIFY.verify(self.root), 2)

    def test_missing_referenced_asset_fails(self):
        (self.root / "asset name.png").unlink()
        with self.assertRaisesRegex(ValueError, "Missing file"):
            VERIFY.verify(self.root)

    def test_filename_case_is_checked_on_every_platform(self):
        with self.assertRaisesRegex(ValueError, "wrong filename case"):
            VERIFY.require_file(self.root, "Asset name.png")

    def test_invalid_javascript_fails(self):
        (self.root / "js/main.js").write_text("const = ;\n")
        with self.assertRaisesRegex(ValueError, "JavaScript syntax check failed"):
            VERIFY.verify(self.root)

    def test_missing_entrypoint_fails(self):
        (self.root / "OGOD.html").unlink()
        with self.assertRaisesRegex(ValueError, "OGOD.html"):
            VERIFY.verify(self.root)

    def test_document_structure_is_required(self):
        (self.root / "index.html").write_text("Not an HTML entrypoint")
        with self.assertRaisesRegex(ValueError, "Missing document structure"):
            VERIFY.verify(self.root)

    def test_symlink_and_empty_file_fail(self):
        (self.root / "link.png").symlink_to("asset name.png")
        with self.assertRaisesRegex(ValueError, "symlink"):
            VERIFY.require_file(self.root, "link.png")
        (self.root / "empty.png").touch()
        with self.assertRaisesRegex(ValueError, "nonempty"):
            VERIFY.require_file(self.root, "empty.png")

    def test_external_and_fragment_references_are_not_network_checks(self):
        for value in ("https://example.com/a", "//example.com/a", "mailto:a@b", "#id", ""):
            self.assertIsNone(VERIFY.local_reference("index.html", value))
        with self.assertRaisesRegex(ValueError, "escapes"):
            VERIFY.local_reference("index.html", "../outside.png")


if __name__ == "__main__":
    unittest.main()
