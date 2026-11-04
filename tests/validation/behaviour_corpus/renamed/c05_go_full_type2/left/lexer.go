package calc

import (
	"fmt"
	"strconv"
	"unicode"
)

type TokenKind int

const (
	TokNumber TokenKind = iota
	TokIdent
	TokPlus
	TokMinus
	TokStar
	TokSlash
	TokLParen
	TokRParen
	TokEOF
)

type Token struct {
	Kind  TokenKind
	Text  string
	Value float64
	Pos   int
}

type Lexer struct {
	input []rune
	pos   int
}

func NewLexer(src string) *Lexer {
	return &Lexer{input: []rune(src), pos: 0}
}

func (l *Lexer) peek() rune {
	if l.pos >= len(l.input) {
		return 0
	}
	return l.input[l.pos]
}

func (l *Lexer) skipSpace() {
	for l.pos < len(l.input) && unicode.IsSpace(l.input[l.pos]) {
		l.pos++
	}
}

func (l *Lexer) Next() (Token, error) {
	l.skipSpace()
	start := l.pos
	ch := l.peek()
	switch {
	case ch == 0:
		return Token{Kind: TokEOF, Pos: start}, nil
	case unicode.IsDigit(ch) || ch == '.':
		return l.number(start)
	case unicode.IsLetter(ch) || ch == '_':
		for l.pos < len(l.input) && (unicode.IsLetter(l.input[l.pos]) || unicode.IsDigit(l.input[l.pos]) || l.input[l.pos] == '_') {
			l.pos++
		}
		return Token{Kind: TokIdent, Text: string(l.input[start:l.pos]), Pos: start}, nil
	}
	l.pos++
	switch ch {
	case '+':
		return Token{Kind: TokPlus, Text: "+", Pos: start}, nil
	case '-':
		return Token{Kind: TokMinus, Text: "-", Pos: start}, nil
	case '*':
		return Token{Kind: TokStar, Text: "*", Pos: start}, nil
	case '/':
		return Token{Kind: TokSlash, Text: "/", Pos: start}, nil
	case '(':
		return Token{Kind: TokLParen, Text: "(", Pos: start}, nil
	case ')':
		return Token{Kind: TokRParen, Text: ")", Pos: start}, nil
	}
	return Token{}, fmt.Errorf("unexpected character %q at %d", ch, start)
}

func (l *Lexer) number(start int) (Token, error) {
	seenDot := false
	for l.pos < len(l.input) {
		c := l.input[l.pos]
		if c == '.' {
			if seenDot {
				break
			}
			seenDot = true
		} else if !unicode.IsDigit(c) {
			break
		}
		l.pos++
	}
	text := string(l.input[start:l.pos])
	v, err := strconv.ParseFloat(text, 64)
	if err != nil {
		return Token{}, fmt.Errorf("bad number %q at %d: %w", text, start, err)
	}
	return Token{Kind: TokNumber, Text: text, Value: v, Pos: start}, nil
}

func Tokenize(src string) ([]Token, error) {
	lx := NewLexer(src)
	var out []Token
	for {
		tok, err := lx.Next()
		if err != nil {
			return nil, err
		}
		out = append(out, tok)
		if tok.Kind == TokEOF {
			return out, nil
		}
	}
}
