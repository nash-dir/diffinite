"""Tests for the 2-Pass comment parser."""

import pytest

from diffinite.parser import strip_comments


class TestPythonComments:
    """Python (#) comment stripping."""

    def test_simple_line_comment(self):
        src = "x = 1  # this is a comment\ny = 2\n"
        result = strip_comments(src, ".py")
        assert "# this is a comment" not in result
        assert "x = 1" in result
        assert "y = 2" in result

    def test_string_with_hash_preserved(self):
        """Hash inside a string literal must NOT be stripped."""
        src = 'url = "http://example.com/#fragment"\n'
        result = strip_comments(src, ".py")
        assert "#fragment" in result

    def test_single_quoted_hash_preserved(self):
        src = "path = '/usr/bin/#test'\n"
        result = strip_comments(src, ".py")
        assert "#test" in result

    def test_triple_quoted_string(self):
        src = '"""\nThis # is not a comment\n"""\nx = 1  # real comment\n'
        result = strip_comments(src, ".py")
        assert "This # is not a comment" in result
        assert "# real comment" not in result

    def test_escape_in_string(self):
        src = r's = "escaped \" still string # not comment"' + "\n"
        result = strip_comments(src, ".py")
        assert "# not comment" in result

    def test_empty_input(self):
        assert strip_comments("", ".py") == ""


class TestCFamilyComments:
    """C-family (// and /* */) comment stripping."""

    def test_line_comment(self):
        src = "int x = 1; // my var\n"
        result = strip_comments(src, ".js")
        assert "// my var" not in result
        assert "int x = 1;" in result

    def test_block_comment(self):
        src = "a = 1; /* block\ncomment */ b = 2;\n"
        result = strip_comments(src, ".c")
        assert "block" not in result
        assert "a = 1;" in result
        assert "b = 2;" in result

    def test_url_in_string_preserved(self):
        """// inside a string must not be treated as a comment."""
        src = 'var url = "https://example.com/path";\n'
        result = strip_comments(src, ".js")
        assert "https://example.com/path" in result

    def test_slash_star_in_string(self):
        src = 'char *s = "/* not a comment */";\n'
        result = strip_comments(src, ".c")
        assert "/* not a comment */" in result

    def test_template_literal_backtick(self):
        """JS template literal with // inside should be preserved."""
        src = "let x = `https://example.com`;\n"
        result = strip_comments(src, ".js")
        assert "https://example.com" in result

    def test_nested_string_in_block_comment(self):
        """Block comment ending doesn't get confused by string inside comment."""
        src = 'int a; /* "hello" */ int b;\n'
        result = strip_comments(src, ".java")
        assert '"hello"' not in result  # inside the comment
        assert "int a;" in result
        assert "int b;" in result

    def test_template_literal_basic(self):
        """JS template literal text should be preserved."""
        src = "let msg = `Hello ${name}, welcome!`;\n"
        result = strip_comments(src, ".js")
        assert "Hello" in result
        assert "welcome" in result

    def test_template_literal_comment_inside_expr(self):
        """Comments inside ${} expressions should be stripped."""
        src = "let x = `value: ${foo(a) // inline comment\n}`;\n"
        result = strip_comments(src, ".js")
        assert "// inline comment" not in result
        assert "foo(a)" in result

    def test_template_literal_nested(self):
        """Nested ${} in template literals should be handled correctly."""
        src = "let x = `outer ${a + `inner ${b}`} end`;\n"
        result = strip_comments(src, ".js")
        assert "outer" in result
        assert "inner" in result
        assert "end" in result


class TestHTMLComments:
    """HTML/XML <!-- --> comment stripping."""

    def test_html_comment(self):
        src = "<div><!-- hidden --><p>visible</p></div>\n"
        result = strip_comments(src, ".html")
        assert "hidden" not in result
        assert "visible" in result


class TestUnknownExtension:
    """Unknown extensions should pass text through unchanged."""

    def test_unknown(self):
        src = "# this stays\n// also stays\n"
        assert strip_comments(src, ".xyz") == src


class TestSQLComments:
    """SQL (-- and /* */) comment stripping."""

    def test_line_comment(self):
        src = "SELECT * FROM t; -- get all\n"
        result = strip_comments(src, ".sql")
        assert "-- get all" not in result
        assert "SELECT * FROM t;" in result


class TestJsRegexLiterals:
    """JS/TS regex literals must not be mistaken for comments."""

    def test_regex_slash_star_not_block_comment(self):
        # /foo/ is a regex; the following '/*' must NOT open a block comment
        # that swallows real code on later lines.
        src = "const re = /foo/*bar/;\nconst SECRET = 1;\ndoStuff();\n"
        result = strip_comments(src, ".js")
        assert "SECRET" in result
        assert "doStuff" in result
        assert "const re" in result

    def test_regex_with_double_slash_inside_class(self):
        # A regex char-class containing '/' and '//'-looking content stays code.
        src = "const p = /[a-z/]+\\/\\//;\nKEEP = 2;\n"
        result = strip_comments(src, ".js")
        assert "KEEP" in result

    def test_division_is_not_regex(self):
        # Plain arithmetic with '//' line comment after it still strips.
        src = "let r = total / count; // ratio\nnext();\n"
        result = strip_comments(src, ".js")
        assert "// ratio" not in result
        assert "total / count" in result
        assert "next();" in result

    def test_division_after_object_literal_does_not_hide_real_comment(self):
        src = "const x = {} / 2; // real comment\nconst after = 1;\n"
        result = strip_comments(src, ".js")
        assert "{} / 2" in result
        assert "real comment" not in result
        assert "const after = 1;" in result

    def test_regex_after_statement_block_remains_a_regex_literal(self):
        src = r"if (ready) {} /foo\/\/bar/.test(value); // real comment" + "\n"
        result = strip_comments(src, ".js")
        assert r"/foo\/\/bar/.test(value)" in result
        assert "real comment" not in result

    def test_real_line_comment_after_value_still_stripped(self):
        src = "let x = 5; // keep value\n"
        result = strip_comments(src, ".js")
        assert "// keep value" not in result
        assert "let x = 5;" in result


class TestMarkupQuotesAreData:
    """In HTML/XML/SVG/CSS a quote is data, not a string delimiter."""

    def test_html_apostrophe_does_not_hide_comment(self):
        src = "<p>it's a test <!-- secret comment --> visible</p>\n"
        result = strip_comments(src, ".html")
        assert "secret comment" not in result
        assert "visible" in result
        assert "it's a test" in result

    def test_html_attribute_quotes_preserved(self):
        src = '<a href="x">link</a><!-- c -->\n'
        result = strip_comments(src, ".html")
        assert 'href="x"' in result
        assert "<!-- c -->" not in result and "c -->" not in result

    def test_css_apostrophe_does_not_leak_comment(self):
        src = "p::after { content: 'o'clock'; } /* note */ a{}\n"
        result = strip_comments(src, ".css")
        assert "note" not in result
        assert "content:" in result


class TestRubyBlockAnchored:
    """Ruby =begin/=end are comment markers only at column 0."""

    def test_begin_midline_is_not_block_comment(self):
        src = "result =begin_value\nputs result\n"
        result = strip_comments(src, ".rb")
        assert "puts result" in result
        assert "begin_value" in result

    def test_begin_at_column_zero_strips_block(self):
        src = "x = 1\n=begin\nhidden doc here\n=end\ny = 2\n"
        result = strip_comments(src, ".rb")
        assert "hidden doc here" not in result
        assert "x = 1" in result
        assert "y = 2" in result

    def test_indented_end_does_not_close_early(self):
        src = "=begin\nline one\n  =end still comment\nreal_code = 1\n=end\nafter = 2\n"
        result = strip_comments(src, ".rb")
        assert "line one" not in result
        assert "real_code" not in result  # still inside the block (indented =end ignored)
        assert "after = 2" in result


class TestJavaScriptTemplateInterpolationDepth:
    """Template text and interpolation code must return to the right state."""

    @pytest.mark.parametrize(
        "template",
        [
            "`plain template`",
            "`value=${name}`",
            "`value=${foo({a: 1})}`",
            "`nested=${`inner=${value}`}`",
            r"`escaped \` backtick`",
            "`multi\nline ${value}\ntext`",
            "`text // not comment /* also text */`",
            '`value=${"// string" + item}`',
        ],
    )
    def test_template_variants_preserved_and_real_comment_removed(self, template):
        source = f"const message = {template}; // actual comment\nconst after = 1; /* remove */\n"
        output = strip_comments(source, ".js")
        assert template in output
        assert "actual comment" not in output
        assert "remove" not in output
        assert "const after = 1;" in output

    def test_nested_object_braces_do_not_end_interpolation_early(self):
        source = (
            "const message = `value=${foo({a: 1, nested: {b: 2}}) "
            "+ extra /* interpolation comment */}`;\n"
            "const after = compute(); // real comment\n"
            "return after;\n"
        )
        output = strip_comments(source, ".js")
        assert "nested: {b: 2}" in output
        assert "interpolation comment" not in output
        assert "real comment" not in output
        assert "return after;" in output

    def test_object_literal_division_inside_interpolation_strips_comment(self):
        source = "const value = `${{} / 2 /* remove */}`; // outer comment\n"
        output = strip_comments(source, ".js")
        assert "${{} / 2 }" in output
        assert "remove" not in output
        assert "outer comment" not in output

    def test_fingerprint_is_deterministic_after_template_interpolation(self):
        from diffinite.fingerprint import extract_fingerprints

        source = (
            "const message = `value=${foo({a: 1})}`;\n"
            "function after(value) { return value + 1; } // real comment\n"
        )
        cleaned = strip_comments(source, ".js")
        first = extract_fingerprints(cleaned, k=3, w=2)
        second = extract_fingerprints(cleaned, k=3, w=2)
        assert first == second
        assert "function after" in cleaned
        assert "real comment" not in cleaned


class TestIfZeroBlocks:
    """``#if 0`` removal must drop only the dead branch and keep line count."""

    def test_simple_block_removed(self):
        src = "a();\n#if 0\ndead();\n#endif\nb();"
        out = strip_comments(src, ".c")
        assert "dead" not in out
        assert "a();" in out and "b();" in out
        assert out.count("\n") == src.count("\n")

    def test_else_branch_is_live_code(self):
        src = "#if 0\nold();\n#else\nlive_code();\n#endif\n"
        out = strip_comments(src, ".c")
        assert "old" not in out
        assert "live_code();" in out
        assert out.count("\n") == src.count("\n")

    def test_elif_branch_is_live_code(self):
        src = "#if 0\nold();\n#elif defined(X)\nlive();\n#endif\n"
        out = strip_comments(src, ".c")
        assert "old" not in out
        assert "live();" in out

    def test_nested_ifdef_does_not_close_outer_block(self):
        src = "#if 0\n#ifdef FOO\nx();\n#endif\ndead2();\n#endif\nafter();"
        out = strip_comments(src, ".c")
        assert "dead2" not in out
        assert "x();" not in out
        assert "after();" in out
        assert "#endif" not in out

    def test_nested_else_inside_dead_block_stays_dead(self):
        src = "#if 0\n#ifndef FOO\na();\n#else\nb();\n#endif\n#endif\nc();"
        out = strip_comments(src, ".c")
        assert "a();" not in out and "b();" not in out
        assert "c();" in out

    def test_trailing_comment_on_if_zero(self):
        src = "#if 0 // disabled\ndead();\n#endif\nok();"
        out = strip_comments(src, ".c")
        assert "dead" not in out
        assert "ok();" in out

    def test_unterminated_if_zero_keeps_original_text(self):
        # '#if 0' quoted inside a block comment never closes; it must not erase
        # the live code that follows it.
        src = "/* example:\n#if 0\n*/\nreal();\nmore();\n"
        out = strip_comments(src, ".c")
        assert "real();" in out and "more();" in out
