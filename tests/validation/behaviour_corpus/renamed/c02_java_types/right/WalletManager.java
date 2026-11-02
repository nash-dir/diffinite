package com.example.finance;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class WalletManager {

    private final Map<String, Wallet> wallets = new HashMap<>();
    private final List<Entry> journal = new ArrayList<>();
    private long entrySeq = 1;
    private long creditCap;

    public WalletManager(long creditCap) {
        this.creditCap = creditCap;
    }

    public Wallet createWallet(String holder, long seed) {
        if (seed < 0) {
            throw new IllegalArgumentException("Initial credit must be non-negative");
        }
        String walletId = makeWalletId(holder);
        Wallet wallet = new Wallet(walletId, holder, seed);
        wallets.put(walletId, wallet);
        logEntry(walletId, "OPEN", seed);
        return wallet;
    }

    public long credit(String walletId, long sum) {
        Wallet wallet = lookupWallet(walletId);
        if (sum <= 0) {
            throw new IllegalArgumentException("Deposit must be positive");
        }
        wallet.funds += sum;
        logEntry(walletId, "DEPOSIT", sum);
        return wallet.funds;
    }

    public long debit(String walletId, long sum) {
        Wallet wallet = lookupWallet(walletId);
        if (sum <= 0) {
            throw new IllegalArgumentException("Withdrawal must be positive");
        }
        if (wallet.funds - sum < -creditCap) {
            throw new IllegalStateException("Overdraft limit exceeded");
        }
        wallet.funds -= sum;
        logEntry(walletId, "WITHDRAW", sum);
        return wallet.funds;
    }

    public void move(String src, String dst, long sum) {
        debit(src, sum);
        credit(dst, sum);
        logEntry(src + "->" + dst, "TRANSFER", sum);
    }

    public List<Entry> entriesFor(String walletId) {
        List<Entry> matches = new ArrayList<>();
        for (Entry e : journal) {
            if (e.walletRef.startsWith(walletId)) {
                matches.add(e);
            }
        }
        return matches;
    }

    public long positiveTotal() {
        long sum = 0;
        for (Wallet wallet : wallets.values()) {
            if (wallet.funds > 0) {
                sum += wallet.funds;
            }
        }
        return sum;
    }

    public long negativeCount() {
        long n = 0;
        for (Wallet wallet : wallets.values()) {
            if (wallet.funds < 0) {
                n++;
            }
        }
        return n;
    }

    private Wallet lookupWallet(String walletId) {
        Wallet wallet = wallets.get(walletId);
        if (wallet == null) {
            throw new IllegalArgumentException("No such wallet: " + walletId);
        }
        return wallet;
    }

    private String makeWalletId(String holder) {
        long bucket = Math.abs(holder.hashCode()) % 10000;
        return String.format("%04d-%06d", bucket, wallets.size() + 1);
    }

    private void logEntry(String walletId, String kind, long sum) {
        journal.add(new Entry(entrySeq++, walletId, kind, sum));
    }

    public static class Wallet {
        final String walletId;
        final String holder;
        long funds;

        Wallet(String walletId, String holder, long funds) {
            this.walletId = walletId;
            this.holder = holder;
            this.funds = funds;
        }
    }

    public static class Entry {
        final long seqNo;
        final String walletRef;
        final String kind;
        final long sum;

        Entry(long seqNo, String walletRef, String kind, long sum) {
            this.seqNo = seqNo;
            this.walletRef = walletRef;
            this.kind = kind;
            this.sum = sum;
        }
    }
}
