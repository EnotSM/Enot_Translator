import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import json
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DISPLAY"] = ""

from constants import LANGUAGES, CONTEXT_SIZES
from enot_translator import (
    OllamaClient,
    TranslationWorker,
    repair_json,
)


class TestIsTranslatable(unittest.TestCase):
    def setUp(self):
        self.worker = TranslationWorker.__new__(TranslationWorker)

    def test_empty_string(self):
        self.assertFalse(self.worker.is_translatable(""))
        self.assertFalse(self.worker.is_translatable("   "))
        self.assertFalse(self.worker.is_translatable("\t\n"))

    def test_only_punctuation(self):
        self.assertFalse(self.worker.is_translatable("..."))
        self.assertFalse(self.worker.is_translatable("—   ---   "))
        self.assertFalse(self.worker.is_translatable("?!"))

    def test_alpha_strings(self):
        self.assertTrue(self.worker.is_translatable("Hello"))
        self.assertTrue(self.worker.is_translatable("  Привіт  "))
        self.assertTrue(self.worker.is_translatable("a"))

    def test_mixed_content(self):
        self.assertTrue(self.worker.is_translatable("Hello world!"))
        self.assertTrue(self.worker.is_translatable("123 test 456"))
        self.assertTrue(self.worker.is_translatable("   A   "))


class TestIsBadTranslation(unittest.TestCase):
    def make_worker(self, tgt_lang):
        w = TranslationWorker.__new__(TranslationWorker)
        w.tgt_lang = tgt_lang
        return w

    def test_identical_long_alpha(self):
        w = self.make_worker("English 🇬🇧")
        self.assertTrue(w._is_bad_translation("The quick brown fox jumps over the lazy dog", "The quick brown fox jumps over the lazy dog"))

    def test_identical_short_allowed(self):
        w = self.make_worker("English 🇬🇧")
        self.assertFalse(w._is_bad_translation("Hi", "Hi"))
        self.assertFalse(w._is_bad_translation("A", "A"))

    def test_identical_empty(self):
        w = self.make_worker("English 🇬🇧")
        self.assertFalse(w._is_bad_translation("", ""))

    def test_cyrillic_in_non_cyrillic_target(self):
        w = self.make_worker("English 🇬🇧")
        self.assertTrue(w._is_bad_translation("Hello", "Привет"))

    def test_cyrillic_allowed_in_cyrillic_target(self):
        for lang in ["Russian 🇺🇦", "Ukrainian 🇺🇦", "Bulgarian 🇧🇬"]:
            w = self.make_worker(lang)
            self.assertFalse(w._is_bad_translation("Hello", "Привет"), f"Failed for {lang}")

    def test_good_translation(self):
        w = self.make_worker("German 🇩🇪")
        self.assertFalse(w._is_bad_translation("Hello", "Hallo"))

    def test_same_short_strings(self):
        w = self.make_worker("French 🇫🇷")
        self.assertFalse(w._is_bad_translation("oui", "oui"))


class TestOllamaClient(unittest.TestCase):
    def test_url_normalization(self):
        client = OllamaClient("http://localhost:11434/")
        self.assertEqual(client.base_url, "http://localhost:11434")

    def test_url_no_change(self):
        client = OllamaClient("http://localhost:11434")
        self.assertEqual(client.base_url, "http://localhost:11434")


class TestCheckpointing(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.in_path = os.path.join(self.tmpdir, "test.txt")
        self.out_path = os.path.join(self.tmpdir, "test_translated.txt")
        Path(self.in_path).write_text("hello\nworld\n", encoding="utf-8")
        self.worker = TranslationWorker.__new__(TranslationWorker)
        self.worker.in_path = self.in_path
        in_p = Path(self.in_path)
        self.worker.state_file = str(in_p.with_name(f"{in_p.stem}_enot.state.json"))

    def tearDown(self):
        for f in [self.in_path, self.out_path, self.worker.state_file, self.worker.state_file + ".tmp"]:
            try:
                os.remove(f)
            except OSError:
                pass
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass

    def test_save_and_load_checkpoint(self):
        state = {"0": "hello translated", "1": "world translated"}
        self.worker._save_checkpoint(state)
        loaded = self.worker._load_checkpoint()
        self.assertEqual(loaded, state)

    def test_load_missing_checkpoint(self):
        loaded = self.worker._load_checkpoint()
        self.assertEqual(loaded, {})

    def test_save_atomicity(self):
        self.worker._save_checkpoint({"a": "b"})
        self.assertTrue(os.path.exists(self.worker.state_file))
        self.assertFalse(os.path.exists(self.worker.state_file + ".tmp"))


class TestLineReconstruction(unittest.TestCase):
    def test_positional_rebuild_basic(self):
        line = "Hello world\n"
        prefix = line[:len(line) - len(line.lstrip())]
        suffix = line[len(line.rstrip()):]
        result = prefix + "Bonjour le monde" + suffix
        self.assertEqual(result, "Bonjour le monde\n")

    def test_positional_rebuild_leading_whitespace(self):
        line = "    Hello world\n"
        prefix = line[:len(line) - len(line.lstrip())]
        suffix = line[len(line.rstrip()):]
        result = prefix + "Bonjour le monde" + suffix
        self.assertEqual(result, "    Bonjour le monde\n")

    def test_positional_rebuild_trailing_whitespace(self):
        line = "Hello world   \n"
        prefix = line[:len(line) - len(line.lstrip())]
        suffix = line[len(line.rstrip()):]
        result = prefix + "Bonjour le monde" + suffix
        self.assertEqual(result, "Bonjour le monde   \n")

    def test_positional_rebuild_duplicate_content(self):
        line = "Hello. Hello.\n"
        prefix = line[:len(line) - len(line.lstrip())]
        suffix = line[len(line.rstrip()):]
        result = prefix + "Bonjour. Bonjour." + suffix
        self.assertEqual(result, "Bonjour. Bonjour.\n")

    def test_positional_rebuild_tabs_and_spaces(self):
        line = "\t\tHello\tworld\t\n"
        prefix = line[:len(line) - len(line.lstrip())]
        suffix = line[len(line.rstrip()):]
        result = prefix + "translated" + suffix
        self.assertEqual(result, "\t\ttranslated\t\n")

    def test_positional_rebuild_no_newline(self):
        line = "Hello world"
        prefix = line[:len(line) - len(line.lstrip())]
        suffix = line[len(line.rstrip()):]
        result = prefix + "Bonjour le monde" + suffix
        self.assertEqual(result, "Bonjour le monde")


class TestProgressCallback(unittest.TestCase):
    def test_translate_batch_accepts_progress_callback(self):
        client = OllamaClient("http://localhost:11434")
        import inspect
        sig = inspect.signature(client.translate_batch)
        self.assertIn("progress_callback", sig.parameters)

    def test_translate_isolated_accepts_progress_callback(self):
        client = OllamaClient("http://localhost:11434")
        import inspect
        sig = inspect.signature(client._translate_isolated)
        self.assertIn("progress_callback", sig.parameters)


class TestRepairJson(unittest.TestCase):
    def test_clean_json_passes_through(self):
        self.assertEqual(repair_json('{"a": 1}'), '{"a": 1}')

    def test_strips_markdown_fence(self):
        raw = "```json\n{\"a\": 1}\n```"
        self.assertEqual(repair_json(raw), '{"a": 1}')

    def test_strips_code_fence_no_lang(self):
        raw = "```\n{\"a\": 1}\n```"
        self.assertEqual(repair_json(raw), '{"a": 1}')

    def test_extracts_json_from_surrounding_text(self):
        raw = "Here is the result: {\"a\": 1}"
        self.assertEqual(repair_json(raw), '{"a": 1}')

    def test_fixes_trailing_comma_in_object(self):
        self.assertEqual(repair_json('{"a": 1,}'), '{"a": 1}')

    def test_fixes_trailing_comma_in_array(self):
        self.assertEqual(repair_json('[1, 2,]'), '[1, 2]')

    def test_empty_object(self):
        self.assertEqual(repair_json('{}'), '{}')

    def test_nested_json_extraction(self):
        raw = "text before {\"outer\": {\"inner\": 1}} text after"
        self.assertEqual(repair_json(raw), '{"outer": {"inner": 1}}')


class TestConstants(unittest.TestCase):
    def test_languages_have_entries(self):
        self.assertGreater(len(LANGUAGES), 5)

    def test_context_sizes(self):
        self.assertIn("4096", CONTEXT_SIZES)
        self.assertIn("8192", CONTEXT_SIZES)

    def test_first_language_empty(self):
        self.assertEqual(LANGUAGES[0], "")


if __name__ == "__main__":
    unittest.main()
