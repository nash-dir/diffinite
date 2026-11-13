"""Regression tests for the 2026-11-10 code audit, parser group (#14-#19, #38, #45)."""

from __future__ import annotations

import pytest

from diffinite.languages import get_spec
from diffinite.models import AnalysisMetadata, deep_compare_comment_mode, stripped_comment_mode
from diffinite.parser import (
    comment_extensions_for_pair,
    extensions_without_comment_rules,
    has_comment_rules,
    strip_comments,
)

BS = "\\"


def _deep_meta() -> AnalysisMetadata:
    return AnalysisMetadata(exec_mode="deep", k=5, w=4, threshold=5.0)


# ── #14: '#' line markers need a token boundary where the language says so ──
class TestHashMarkerBoundary:
    def test_shell_dollar_hash_and_length_expansion_are_code(self):
        src = "if [ $# -lt 2 ]; then exit 1; fi\nn=${#arr[@]}\necho x#y # c\nls;#c"
        out = strip_comments(src, ".sh")
        assert out == "if [ $# -lt 2 ]; then exit 1; fi\nn=${#arr[@]}\necho x#y \nls;"

    def test_zsh_same_rule(self):
        assert strip_comments("n=${#a} # c", ".zsh") == "n=${#a} "

    def test_yaml_hash_inside_plain_scalar_is_value(self):
        src = "url: http://x/#anchor\ncolor: red#x # c\n# full"
        assert strip_comments(src, ".yaml") == "url: http://x/#anchor\ncolor: red#x \n"

    def test_perl_last_index_operator_is_code(self):
        src = "my $n = $#arr; # c\nmy $m = $#{$r};"
        assert strip_comments(src, ".pl") == "my $n = $#arr; \nmy $m = $#{$r};"

    def test_php8_attribute_is_code(self):
        src = "#[Route('/x')]\nfunction f() {} # c\n// d"
        assert strip_comments(src, ".php") == "#[Route('/x')]\nfunction f() {} \n"

    def test_python_hash_still_a_comment_anywhere(self):
        assert strip_comments("x=1# c", ".py") == "x=1"


# ── #15: triple quotes only where the language has them ──
class TestTripleQuotesPerLanguage:
    def test_sql_quoted_quote_is_not_a_multiline_string(self):
        src = "SELECT '''' || name FROM t; -- c1\nSELECT 1; -- c2\nSELECT 2; -- c3"
        assert strip_comments(src, ".sql") == "SELECT '''' || name FROM t; \nSELECT 1; \nSELECT 2; "

    def test_c_adjacent_empty_strings(self):
        assert strip_comments('char *s = """"; // c1\nint x; // c2', ".c") == (
            'char *s = """"; \nint x; '
        )

    @pytest.mark.parametrize("ext", [".py", ".java", ".kt", ".scala", ".swift", ".cs"])
    def test_triple_quote_languages_keep_multiline_strings(self, ext):
        src = 'x = """\n// not a comment\n# not a comment\n"""'
        assert strip_comments(src, ext) == src

    def test_python_single_triple_quote(self):
        src = "x = '''\n# kept\n'''  # c"
        assert strip_comments(src, ".py") == "x = '''\n# kept\n'''  "


# ── #16: a trailing backslash never escapes the next line's first character ──
class TestTrailingBackslash:
    def test_python_triple_string_line_continuation(self):
        src = 'x = """abc' + BS + '\n"""  # c1\ny = 1  # c2\nz = 2  # c3'
        assert strip_comments(src, ".py") == 'x = """abc' + BS + '\n"""  \ny = 1  \nz = 2  '

    def test_js_unclosed_regex_reset_clears_escape(self):
        src = "x = /abc" + BS + "\ns = ''; // c2\ny = 1; // c3"
        assert strip_comments(src, ".js") == "x = /abc" + BS + "\ns = ''; \ny = 1; "

    def test_c_string_continued_onto_next_line(self):
        # "abc\<newline>def // x" is one string literal (C translation phase 2).
        src = 's = "abc' + BS + '\ndef // x"; // c1\nint y; // c2'
        assert strip_comments(src, ".c") == 's = "abc' + BS + '\ndef // x"; \nint y; '

    def test_js_template_trailing_backslash(self):
        src = "t = `a" + BS + "\n`; // c1\ny; // c2"
        assert strip_comments(src, ".js") == "t = `a" + BS + "\n`; \ny; "


# ── #17: #if 0 only for C/C++/C#, and never inside comments ──
class TestIfZeroLexicalScope:
    def test_if_zero_inside_block_comment_is_not_a_directive(self):
        src = "/* example:\n#if 0\n*/\nint live(void);\n#endif"
        out = strip_comments(src, ".c")
        assert "int live(void);" in out
        assert out.count("\n") == src.count("\n")

    def test_include_guard_header_keeps_public_api(self):
        src = (
            "#ifndef H\n#define H\n/* Usage: wrap with\n#if 0\n ...\n*/\n"
            "int api_a(void);\nint api_b(void);\n#endif\n"
        )
        out = strip_comments(src, ".h")
        assert "int api_a(void);" in out and "int api_b(void);" in out

    def test_real_if_zero_still_removed_in_c_family(self):
        for ext in (".c", ".cpp", ".cs"):
            out = strip_comments("a();\n#if 0\ndead();\n#endif\nb();", ext)
            assert "dead" not in out and "a();" in out and "b();" in out

    @pytest.mark.parametrize(
        "ext", [".java", ".kt", ".scala", ".js", ".ts", ".tsx", ".go", ".rs", ".swift"]
    )
    def test_no_preprocessor_languages(self, ext):
        assert get_spec(ext).has_ifdef_zero is False
        out = strip_comments('s = "x";\n#if 0\nlive();\n#endif', ext)
        assert "live();" in out


# ── #18: nested block comments ──
class TestNestedBlockComments:
    @pytest.mark.parametrize("ext", [".rs", ".swift", ".kt", ".scala"])
    def test_nested_comment_fully_stripped(self, ext):
        src = "/* outer /* inner */ still comment */\nfn main() {}"
        assert strip_comments(src, ext) == "\nfn main() {}"

    @pytest.mark.parametrize("ext", [".rs", ".kt"])
    def test_nested_across_lines(self, ext):
        src = "/* a\n/* b */\nstill */ x"
        assert strip_comments(src, ext) == "\n\n x"

    @pytest.mark.parametrize("ext", [".c", ".java", ".cs", ".js"])
    def test_non_nesting_languages_unchanged(self, ext):
        assert strip_comments("/* outer /* inner */ x; */", ext) == " x; */"


# ── #19: per-language string rules ──
class TestLanguageStringRules:
    def test_go_raw_string_ending_in_backslash(self):
        src = "p := `C:" + BS + "`\nx := 1 // c1\ny := 2 // c2\nq := `z`\nw := 3 // c4"
        assert strip_comments(src, ".go") == (
            "p := `C:" + BS + "`\nx := 1 \ny := 2 \nq := `z`\nw := 3 "
        )

    def test_go_interpreted_string_still_escapes(self):
        assert strip_comments('s := "a\\" // x" // c', ".go") == 's := "a\\" // x" '

    def test_rust_lifetimes_are_code(self):
        src = "fn f<'a>(x: &'a T) -> &'a T { // c1\n    x /* c2 */\n}"
        assert strip_comments(src, ".rs") == "fn f<'a>(x: &'a T) -> &'a T { \n    x \n}"

    def test_rust_multiline_block_after_lifetime(self):
        src = "fn g<'a>(s: &'a str) -> &'a str { /* a\nb */ s }"
        assert strip_comments(src, ".rs") == "fn g<'a>(s: &'a str) -> &'a str { \n s }"

    def test_rust_char_literals_protect_markers(self):
        src = "let c = '/'; // c\nlet q = '" + BS + "''; // d\nlet s = '\"'; // e"
        assert strip_comments(src, ".rs") == (
            "let c = '/'; \nlet q = '" + BS + "''; \nlet s = '\"'; "
        )


# ── #38: comment mode label discloses files that kept their comments ──
class TestCommentModeDisclosure:
    def test_has_comment_rules(self):
        assert has_comment_rules(".py") and has_comment_rules(".c")
        for ext in (".gradle", ".vue", ".cfg", ".mk", ".txt", ""):
            assert not has_comment_rules(ext)
            assert strip_comments("x = 1  # c\n", ext) == "x = 1  # c\n"

    def test_extensions_without_comment_rules(self):
        assert extensions_without_comment_rules([".py", ".vue", ".gradle", ".vue", ".c"]) == [
            ".gradle",
            ".vue",
        ]

    def test_label_plain_when_all_files_had_rules(self):
        assert stripped_comment_mode() == "stripped"
        assert deep_compare_comment_mode(True, _deep_meta()) == "stripped"
        assert deep_compare_comment_mode(True, _deep_meta(), []) == "stripped"

    def test_label_names_fallback_extensions(self):
        label = deep_compare_comment_mode(True, _deep_meta(), [".vue", ".gradle", ""])
        assert label != "stripped"
        assert label.startswith("stripped (except")
        assert label.endswith("(no extension), .gradle, .vue)")  # sorted, deterministic
        assert stripped_comment_mode([".vue"]) == (
            "stripped (except files with no registered comment syntax, which keep "
            "comments: .vue)"
        )

    def test_label_unaffected_when_not_stripping(self):
        assert deep_compare_comment_mode(False, _deep_meta(), [".vue"]) == "included"
        assert deep_compare_comment_mode(True, None, [".vue"]) == "not-applicable"


# ── #45 (parser half): one rule picks the comment syntax for a pair ──
class TestPairCommentExtension:
    def test_unregistered_side_borrows_partner(self):
        assert comment_extensions_for_pair(".cxx", ".cpp") == (".cpp", ".cpp")
        assert comment_extensions_for_pair(".cpp", ".orig") == (".cpp", ".cpp")

    def test_each_registered_side_keeps_its_own(self):
        assert comment_extensions_for_pair(".py", ".js") == (".py", ".js")

    def test_both_unregistered_unchanged(self):
        assert comment_extensions_for_pair(".vue", ".gradle") == (".vue", ".gradle")

    def test_borrowed_rule_strips_the_unregistered_side(self):
        ext_a, _ = comment_extensions_for_pair(".cxx", ".cpp")
        assert strip_comments("// c\nint f();", ext_a) == "\nint f();"


# ── Round-2 follow-ups (fix-parser.md review: #16, #17, #19 partial cases) ──
CR = "\r"


class TestCrlfBackslashContinuation:
    """#16: in a CRLF file a backslash before the CR still continues the string."""

    def test_c_string_continued_across_crlf_then_comment_stripped(self):
        src = 'x = "abc' + BS + CR + '\ndef"; // x' + CR + "\ny();" + CR + "\n"
        out = strip_comments(src, ".c")
        assert "// x" not in out
        assert out.split("\n")[1].startswith('def"; ')
        assert out.count("\n") == src.count("\n")

    def test_python_string_continued_across_crlf_keeps_hash(self):
        src = "a = 'abc" + BS + CR + "\n# not comment'" + CR + "\n"
        assert strip_comments(src, ".py") == src

    def test_lf_and_crlf_give_same_code(self):
        lf = 'x = "abc' + BS + '\ndef"; // x\ny();'
        crlf = lf.replace("\n", CR + "\n")
        assert strip_comments(crlf, ".c").replace(CR, "") == strip_comments(lf, ".c")

    def test_js_template_backslash_crlf(self):
        src = "s = `a" + BS + CR + "\n// in template`; // c"
        out = strip_comments(src, ".js")
        assert "// in template" in out
        assert "// c" not in out


class TestIfZeroInsideStrings:
    """#17: a '#if 0' line that starts inside a string is string content."""

    def test_csharp_verbatim_string_hides_if0(self):
        src = 'var s = @"\n#if 0\n";\nlive();\n#endif\n'
        assert strip_comments(src, ".cs") == src

    def test_csharp_interpolated_verbatim_string_hides_if0(self):
        for prefix in ('$@"', '@$"'):
            src = "var s = " + prefix + "\n#if 0\n" + '";\nlive();\n#endif\n'
            assert strip_comments(src, ".cs") == src, prefix

    def test_csharp_raw_string_hides_if0(self):
        src = 'var s = """\n#if 0\n""";\nlive();\n#endif\n'
        assert strip_comments(src, ".cs") == src

    def test_csharp_verbatim_doubled_quote_and_no_escape(self):
        # "" is a literal quote and \ is not an escape: the string ends at the
        # final quote, so the following comment and real #if 0 block are removed.
        lit = '@"C:' + BS + "dir" + BS + '""x // in"'
        src = "var p = " + lit + ";// c\n#if 0\ndead();\n#endif\nlive();"
        out = strip_comments(src, ".cs")
        assert out == "var p = " + lit + ";\n\n\n\nlive();"

    def test_c_backslash_continued_string_hides_if0(self):
        src = 'char *s = "a' + BS + "\n#if 0\n" + '";\nlive();\n#endif\n'
        assert strip_comments(src, ".c") == src

    def test_real_if0_block_still_removed(self):
        src = 'var s = @"x";\n#if 0\ndead();\n#endif\nlive();'
        assert strip_comments(src, ".cs") == 'var s = @"x";\n\n\n\nlive();'


class TestGoRawStringNoInterpolation:
    """#19: Go raw strings have no ${...} interpolation."""

    def test_dollar_brace_is_text_in_go_raw_string(self):
        assert strip_comments("x := `${ // a }` + y // c", ".go") == "x := `${ // a }` + y "

    def test_multiline_go_raw_string_with_dollar_brace(self):
        src = "x := `${\n// a\n}` // c\nz()"
        assert strip_comments(src, ".go") == "x := `${\n// a\n}` \nz()"

    def test_js_template_interpolation_unchanged(self):
        assert strip_comments("x = `${ a /* b */ }` // c", ".js") == "x = `${ a  }` "


class TestCppRawStrings:
    """C++11 raw string literals R"d(...)d" are string content, not code (C++ only)."""

    def test_if0_inside_raw_string_is_not_a_directive(self):
        src = 'auto s = R"(\n#if 0\n)";\nlive();\n#endif\n'
        assert strip_comments(src, ".cpp") == src

    def test_line_comment_marker_inside_delimited_raw_string(self):
        src = 'auto s = R"x(// not a comment)x"; int a; // c\n'
        assert strip_comments(src, ".cpp") == 'auto s = R"x(// not a comment)x"; int a; \n'

    def test_multiline_raw_string_with_block_end_inside(self):
        src = 'auto s = R"--(\n/* a */ b */ )" c\n)--"; /* gone */ x();\n// tail'
        out = strip_comments(src, ".cpp")
        assert out == 'auto s = R"--(\n/* a */ b */ )" c\n)--";  x();\n'
        assert out.count("\n") == src.count("\n")

    @pytest.mark.parametrize("prefix", ["u8R", "uR", "UR", "LR"])
    def test_encoding_prefixes(self, prefix):
        src = f'auto s = {prefix}"(a /* b )"; c(); // d'
        assert strip_comments(src, ".cc") == f'auto s = {prefix}"(a /* b )"; c(); '

    def test_identifier_ending_in_r_is_not_a_prefix(self):
        # FOOR is an identifier (e.g. a macro); the following "..." is an ordinary string.
        src = 'FOOR"(x" // c'
        assert strip_comments(src, ".cpp") == 'FOOR"(x" '

    def test_c_file_has_no_raw_strings(self):
        # In C, R is an identifier and "(" an ordinary string; the // after it is a comment.
        src = 'R"(" // c\nint x; /* d */\n'
        assert strip_comments(src, ".c") == 'R"(" \nint x; \n'
        assert strip_comments('auto s = R"(\n#if 0\n)";\nlive();\n#endif\n', ".c") != (
            'auto s = R"(\n#if 0\n)";\nlive();\n#endif\n'
        )
