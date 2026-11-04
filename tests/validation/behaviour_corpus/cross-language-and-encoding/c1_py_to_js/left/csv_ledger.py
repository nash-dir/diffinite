"""Parse ledger CSV exports and reconcile balances per account."""

from decimal import Decimal, InvalidOperation


class LedgerError(Exception):
    pass


def split_csv_line(line, delimiter=","):
    fields = []
    current = []
    in_quotes = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    current.append('"')
                    i += 1
                else:
                    in_quotes = False
            else:
                current.append(ch)
        elif ch == '"':
            in_quotes = True
        elif ch == delimiter:
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    if in_quotes:
        raise LedgerError("unterminated quoted field")
    fields.append("".join(current))
    return fields


def parse_amount(text):
    cleaned = text.replace(",", "").strip()
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise LedgerError("bad amount: %r" % text)
    return -value if negative else value


def load_entries(lines):
    header = None
    entries = []
    for lineno, raw in enumerate(lines, start=1):
        raw = raw.rstrip("\r\n")
        if not raw or raw.startswith("#"):
            continue
        fields = split_csv_line(raw)
        if header is None:
            header = [f.strip().lower() for f in fields]
            continue
        if len(fields) != len(header):
            raise LedgerError("line %d: expected %d fields" % (lineno, len(header)))
        row = dict(zip(header, fields))
        row["amount"] = parse_amount(row["amount"])
        entries.append(row)
    return entries


def reconcile(entries, opening):
    balances = dict(opening)
    flagged = []
    for e in entries:
        acct = e["account"]
        balances[acct] = balances.get(acct, Decimal("0")) + e["amount"]
        if balances[acct] < 0:
            flagged.append((acct, e.get("date"), balances[acct]))
    return balances, flagged
