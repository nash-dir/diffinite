package com.example.bank;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class AccountService {

    private final Map<String, Account> accounts = new HashMap<>();
    private final List<Transaction> ledger = new ArrayList<>();
    private int nextTransactionId = 1;
    private double overdraftLimit;

    public AccountService(double overdraftLimit) {
        this.overdraftLimit = overdraftLimit;
    }

    public Account openAccount(String owner, double initialDeposit) {
        if (initialDeposit < 0) {
            throw new IllegalArgumentException("Initial deposit must be non-negative");
        }
        String number = generateAccountNumber(owner);
        Account account = new Account(number, owner, initialDeposit);
        accounts.put(number, account);
        recordTransaction(number, "OPEN", initialDeposit);
        return account;
    }

    public double deposit(String number, double amount) {
        Account account = findAccount(number);
        if (amount <= 0) {
            throw new IllegalArgumentException("Deposit must be positive");
        }
        account.balance += amount;
        recordTransaction(number, "DEPOSIT", amount);
        return account.balance;
    }

    public double withdraw(String number, double amount) {
        Account account = findAccount(number);
        if (amount <= 0) {
            throw new IllegalArgumentException("Withdrawal must be positive");
        }
        if (account.balance - amount < -overdraftLimit) {
            throw new IllegalStateException("Overdraft limit exceeded");
        }
        account.balance -= amount;
        recordTransaction(number, "WITHDRAW", amount);
        return account.balance;
    }

    public void transfer(String from, String to, double amount) {
        withdraw(from, amount);
        deposit(to, amount);
        recordTransaction(from + "->" + to, "TRANSFER", amount);
    }

    public List<Transaction> history(String number) {
        List<Transaction> result = new ArrayList<>();
        for (Transaction tx : ledger) {
            if (tx.accountNumber.startsWith(number)) {
                result.add(tx);
            }
        }
        return result;
    }

    public double totalDeposits() {
        double sum = 0;
        for (Account account : accounts.values()) {
            if (account.balance > 0) {
                sum += account.balance;
            }
        }
        return sum;
    }

    public int countOverdrawn() {
        int count = 0;
        for (Account account : accounts.values()) {
            if (account.balance < 0) {
                count++;
            }
        }
        return count;
    }

    private Account findAccount(String number) {
        Account account = accounts.get(number);
        if (account == null) {
            throw new IllegalArgumentException("No such account: " + number);
        }
        return account;
    }

    private String generateAccountNumber(String owner) {
        int hash = Math.abs(owner.hashCode()) % 10000;
        return String.format("%04d-%06d", hash, accounts.size() + 1);
    }

    private void recordTransaction(String number, String type, double amount) {
        ledger.add(new Transaction(nextTransactionId++, number, type, amount));
    }

    public static class Account {
        final String number;
        final String owner;
        double balance;

        Account(String number, String owner, double balance) {
            this.number = number;
            this.owner = owner;
            this.balance = balance;
        }
    }

    public static class Transaction {
        final int id;
        final String accountNumber;
        final String type;
        final double amount;

        Transaction(int id, String accountNumber, String type, double amount) {
            this.id = id;
            this.accountNumber = accountNumber;
            this.type = type;
            this.amount = amount;
        }
    }
}
