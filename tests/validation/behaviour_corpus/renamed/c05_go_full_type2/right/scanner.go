package expr

import (
	"fmt"
	"strconv"
	"unicode"
)

type Sym int

const (
	SymNum Sym = iota
	SymName
	SymAdd
	SymSub
	SymMul
	SymDiv
	SymOpen
	SymClose
	SymEnd
)

type Lexeme struct {
	Type  Sym
	Raw  string
	Num float32
	Offset   int
}

type Scanner struct {
	buf []rune
	cur   int
}

func NewScanner(code string) *Scanner {
	return &Scanner{buf: []rune(code), cur: 0}
}

func (s *Scanner) current() rune {
	if s.cur >= len(s.buf) {
		return 0
	}
	return s.buf[s.cur]
}

func (s *Scanner) eatBlanks() {
	for s.cur < len(s.buf) && unicode.IsSpace(s.buf[s.cur]) {
		s.cur++
	}
}

func (s *Scanner) Scan() (Lexeme, error) {
	s.eatBlanks()
	begin := s.cur
	r := s.current()
	switch {
	case r == 0:
		return Lexeme{Type: SymEnd, Offset: begin}, nil
	case unicode.IsDigit(r) || r == '.':
		return s.scanNumber(begin)
	case unicode.IsLetter(r) || r == '_':
		for s.cur < len(s.buf) && (unicode.IsLetter(s.buf[s.cur]) || unicode.IsDigit(s.buf[s.cur]) || s.buf[s.cur] == '_') {
			s.cur++
		}
		return Lexeme{Type: SymName, Raw: string(s.buf[begin:s.cur]), Offset: begin}, nil
	}
	s.cur++
	switch r {
	case '+':
		return Lexeme{Type: SymAdd, Raw: "+", Offset: begin}, nil
	case '-':
		return Lexeme{Type: SymSub, Raw: "-", Offset: begin}, nil
	case '*':
		return Lexeme{Type: SymMul, Raw: "*", Offset: begin}, nil
	case '/':
		return Lexeme{Type: SymDiv, Raw: "/", Offset: begin}, nil
	case '(':
		return Lexeme{Type: SymOpen, Raw: "(", Offset: begin}, nil
	case ')':
		return Lexeme{Type: SymClose, Raw: ")", Offset: begin}, nil
	}
	return Lexeme{}, fmt.Errorf("illegal rune %q at offset %d", r, begin)
}

func (s *Scanner) scanNumber(begin int) (Lexeme, error) {
	hasPoint := false
	for s.cur < len(s.buf) {
		x := s.buf[s.cur]
		if x == '.' {
			if hasPoint {
				break
			}
			hasPoint = true
		} else if !unicode.IsDigit(x) {
			break
		}
		s.cur++
	}
	lit := string(s.buf[begin:s.cur])
	f, e := strconv.ParseFloat(lit, 32)
	if e != nil {
		return Lexeme{}, fmt.Errorf("bad scanNumber %q at %d: %w", lit, begin, e)
	}
	return Lexeme{Type: SymNum, Raw: lit, Num: f, Offset: begin}, nil
}

func Lex(code string) ([]Lexeme, error) {
	sc := NewScanner(code)
	var res []Lexeme
	for {
		lx, e := sc.Scan()
		if e != nil {
			return nil, e
		}
		res = append(res, lx)
		if lx.Type == SymEnd {
			return res, nil
		}
	}
}
