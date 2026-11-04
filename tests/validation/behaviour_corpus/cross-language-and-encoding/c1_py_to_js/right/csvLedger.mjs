// Parse ledger CSV exports and reconcile balances per account.

export class LedgerError extends Error {}

export function splitCsvLine(line, delimiter = ',') {
  const fields = [];
  let current = [];
  let inQuotes = false;
  let i = 0;
  while (i < line.length) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (i + 1 < line.length && line[i + 1] === '"') {
          current.push('"');
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        current.push(ch);
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === delimiter) {
      fields.push(current.join(''));
      current = [];
    } else {
      current.push(ch);
    }
    i += 1;
  }
  if (inQuotes) {
    throw new LedgerError('unterminated quoted field');
  }
  fields.push(current.join(''));
  return fields;
}

export function parseAmount(text) {
  let cleaned = text.replaceAll(',', '').trim();
  const negative = cleaned.startsWith('(') && cleaned.endsWith(')');
  if (negative) {
    cleaned = cleaned.slice(1, -1);
  }
  const value = Number(cleaned);
  if (Number.isNaN(value)) {
    throw new LedgerError(`bad amount: ${text}`);
  }
  return negative ? -value : value;
}

export function loadEntries(lines) {
  let header = null;
  const entries = [];
  lines.forEach((rawLine, idx) => {
    const lineno = idx + 1;
    const raw = rawLine.replace(/[\r\n]+$/, '');
    if (!raw || raw.startsWith('#')) {
      return;
    }
    const fields = splitCsvLine(raw);
    if (header === null) {
      header = fields.map((f) => f.trim().toLowerCase());
      return;
    }
    if (fields.length !== header.length) {
      throw new LedgerError(`line ${lineno}: expected ${header.length} fields`);
    }
    const row = Object.fromEntries(header.map((h, j) => [h, fields[j]]));
    row.amount = parseAmount(row.amount);
    entries.push(row);
  });
  return entries;
}

export function reconcile(entries, opening) {
  const balances = { ...opening };
  const flagged = [];
  for (const e of entries) {
    const acct = e.account;
    balances[acct] = (balances[acct] || 0) + e.amount;
    if (balances[acct] < 0) {
      flagged.push([acct, e.date, balances[acct]]);
    }
  }
  return [balances, flagged];
}
