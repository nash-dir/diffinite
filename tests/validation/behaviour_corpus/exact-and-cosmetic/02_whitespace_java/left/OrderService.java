package com.example.shop.orders;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class OrderService {

    private final Map<String, Order> orders = new HashMap<>();
    private final InventoryClient inventory;
    private final PaymentGateway payments;
    private long sequence = 1000L;

    public OrderService(InventoryClient inventory, PaymentGateway payments) {
        this.inventory = inventory;
        this.payments = payments;
    }

    public Order createOrder(String customerId, List<OrderLine> lines) {
        if (customerId == null || customerId.isEmpty()) {
            throw new IllegalArgumentException("customerId required");
        }
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("order must contain at least one line");
        }
        for (OrderLine line : lines) {
            if (!inventory.isAvailable(line.getSku(), line.getQuantity())) {
                throw new IllegalStateException("insufficient stock for " + line.getSku());
            }
        }
        String id = "ORD-" + (sequence++);
        Order order = new Order(id, customerId, new ArrayList<>(lines), Instant.now());
        orders.put(id, order);
        return order;
    }

    public BigDecimal computeTotal(Order order) {
        BigDecimal total = BigDecimal.ZERO;
        for (OrderLine line : order.getLines()) {
            BigDecimal lineTotal = line.getUnitPrice().multiply(BigDecimal.valueOf(line.getQuantity()));
            if (line.getDiscountPercent() > 0) {
                BigDecimal discount = lineTotal.multiply(BigDecimal.valueOf(line.getDiscountPercent()))
                        .divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);
                lineTotal = lineTotal.subtract(discount);
            }
            total = total.add(lineTotal);
        }
        return total.setScale(2, RoundingMode.HALF_UP);
    }

    public PaymentResult checkout(String orderId, String cardToken) {
        Order order = find(orderId).orElseThrow(() -> new IllegalArgumentException("no such order " + orderId));
        if (order.getStatus() != OrderStatus.NEW) {
            throw new IllegalStateException("order already processed: " + order.getStatus());
        }
        BigDecimal amount = computeTotal(order);
        PaymentResult result = payments.charge(cardToken, amount, order.getId());
        if (result.isSuccess()) {
            for (OrderLine line : order.getLines()) {
                inventory.reserve(line.getSku(), line.getQuantity());
            }
            order.setStatus(OrderStatus.PAID);
        } else {
            order.setStatus(OrderStatus.PAYMENT_FAILED);
        }
        return result;
    }

    public void cancel(String orderId) {
        Order order = find(orderId).orElseThrow(() -> new IllegalArgumentException("no such order " + orderId));
        switch (order.getStatus()) {
            case NEW:
            case PAYMENT_FAILED:
                order.setStatus(OrderStatus.CANCELLED);
                break;
            case PAID:
                payments.refund(order.getId());
                for (OrderLine line : order.getLines()) {
                    inventory.release(line.getSku(), line.getQuantity());
                }
                order.setStatus(OrderStatus.REFUNDED);
                break;
            default:
                throw new IllegalStateException("cannot cancel order in state " + order.getStatus());
        }
    }

    public Optional<Order> find(String orderId) {
        return Optional.ofNullable(orders.get(orderId));
    }

    public List<Order> ordersFor(String customerId) {
        List<Order> result = new ArrayList<>();
        for (Order o : orders.values()) {
            if (o.getCustomerId().equals(customerId)) {
                result.add(o);
            }
        }
        result.sort((a, b) -> a.getCreatedAt().compareTo(b.getCreatedAt()));
        return Collections.unmodifiableList(result);
    }
}
