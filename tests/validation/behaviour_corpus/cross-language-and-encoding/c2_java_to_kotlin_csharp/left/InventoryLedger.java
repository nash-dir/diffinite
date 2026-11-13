package com.acme.warehouse;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Tracks stock levels per SKU and emits reorder suggestions.
 */
public class InventoryLedger {

    private final Map<String, Integer> stock = new HashMap<>();
    private final Map<String, Integer> reorderPoint = new HashMap<>();
    private final List<String> auditLog = new ArrayList<>();
    private int movementCount = 0;

    public void registerSku(String sku, int initialQty, int reorderAt) {
        if (sku == null || sku.isEmpty()) {
            throw new IllegalArgumentException("sku must not be empty");
        }
        if (initialQty < 0 || reorderAt < 0) {
            throw new IllegalArgumentException("quantities must be non-negative");
        }
        stock.put(sku, initialQty);
        reorderPoint.put(sku, reorderAt);
        auditLog.add("REGISTER " + sku + " qty=" + initialQty);
    }

    public int receive(String sku, int qty) {
        requireKnown(sku);
        if (qty <= 0) {
            throw new IllegalArgumentException("receive qty must be positive");
        }
        int updated = stock.get(sku) + qty;
        stock.put(sku, updated);
        movementCount++;
        auditLog.add("RECEIVE " + sku + " +" + qty + " -> " + updated);
        return updated;
    }

    public int ship(String sku, int qty) {
        requireKnown(sku);
        int current = stock.get(sku);
        if (qty > current) {
            auditLog.add("SHORT " + sku + " wanted=" + qty + " have=" + current);
            throw new IllegalStateException("insufficient stock for " + sku);
        }
        int updated = current - qty;
        stock.put(sku, updated);
        movementCount++;
        auditLog.add("SHIP " + sku + " -" + qty + " -> " + updated);
        return updated;
    }

    public List<String> reorderSuggestions(int batchSize) {
        List<String> result = new ArrayList<>();
        for (Map.Entry<String, Integer> entry : stock.entrySet()) {
            String sku = entry.getKey();
            int qty = entry.getValue();
            int point = reorderPoint.get(sku);
            if (qty <= point) {
                int deficit = point - qty;
                int batches = deficit / batchSize + 1;
                result.add(sku + ":" + (batches * batchSize));
            }
        }
        result.sort(String::compareTo);
        return result;
    }

    public double turnoverRatio(String sku, int periodShipped) {
        requireKnown(sku);
        int onHand = stock.get(sku);
        if (onHand == 0) {
            return Double.POSITIVE_INFINITY;
        }
        return (double) periodShipped / onHand;
    }

    public int getMovementCount() {
        return movementCount;
    }

    public List<String> getAuditLog() {
        return new ArrayList<>(auditLog);
    }

    private void requireKnown(String sku) {
        if (!stock.containsKey(sku)) {
            throw new IllegalArgumentException("unknown sku: " + sku);
        }
    }

    public static void main(String[] args) {
        InventoryLedger ledger = new InventoryLedger();
        ledger.registerSku("BOLT-M6", 120, 50);
        ledger.registerSku("NUT-M6", 40, 60);
        ledger.receive("BOLT-M6", 30);
        ledger.ship("BOLT-M6", 110);
        ledger.ship("NUT-M6", 5);
        System.out.println(ledger.reorderSuggestions(25));
        System.out.println(ledger.turnoverRatio("BOLT-M6", 110));
    }
}
