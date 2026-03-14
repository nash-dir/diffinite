"""Default AST node type sets shared across all languages.

When a ``LangSpec`` leaves its node-type fields as ``None``, the
corresponding default set from this module is used as the fallback.
"""

# Node types that are identifiers (normalised to "ID")
DEFAULT_IDENTIFIER_TYPES = frozenset({
    "identifier", "type_identifier", "field_identifier",
    "property_identifier", "shorthand_property_identifier",
    "shorthand_property_identifier_pattern",
    "variable_name", "name", "attribute",
})

# Node types for numeric literals (→ "LIT")
DEFAULT_LITERAL_TYPES = frozenset({
    "integer", "integer_literal", "decimal_integer_literal",
    "hex_integer_literal", "octal_integer_literal",
    "binary_integer_literal", "float_literal",
    "decimal_floating_point_literal", "number",
})

# Node types for string literals (→ "STR")
DEFAULT_STRING_TYPES = frozenset({
    "string", "string_literal", "string_fragment",
    "template_string", "raw_string_literal",
    "character_literal", "char_literal",
    "interpreted_string_literal", "rune_literal",
})

# Internal node types that contribute meaningful structure
DEFAULT_STRUCTURE_NODE_TYPES = frozenset({
    # Statements
    "if_statement", "else_clause", "elif_clause",
    "for_statement", "for_in_statement", "enhanced_for_statement",
    "while_statement", "do_statement",
    "switch_statement", "switch_expression",
    "case_clause", "switch_case", "default_case",
    "try_statement", "catch_clause", "finally_clause",
    "return_statement", "throw_statement",
    "break_statement", "continue_statement",
    # Declarations
    "function_definition", "function_declaration",
    "method_declaration", "method_definition",
    "class_declaration", "class_definition",
    "constructor_declaration",
    "variable_declaration", "local_variable_declaration",
    # Expressions
    "call_expression", "method_invocation",
    "binary_expression", "unary_expression",
    "assignment_expression", "conditional_expression",
    "lambda_expression",
    # Blocks
    "block", "statement_block", "compound_statement",
    # Parameters
    "formal_parameters", "parameter_list", "parameters",
    "argument_list", "arguments",
})

# Statement-level node types considered for PDG analysis
DEFAULT_STATEMENT_TYPES = frozenset({
    "expression_statement", "return_statement",
    "if_statement", "for_statement", "while_statement",
    "for_in_statement", "enhanced_for_statement",
    "do_statement", "switch_statement",
    "try_statement", "throw_statement",
    "variable_declaration", "local_variable_declaration",
    "assignment_expression",
    # Python
    "assignment", "augmented_assignment",
    "print_statement",
})
