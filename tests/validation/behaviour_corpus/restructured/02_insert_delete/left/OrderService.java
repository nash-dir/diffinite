package com.acme.orders;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class OrderService {

    private final OrderRepository repository;
    private final TaxTable taxTable;
    private final Map<String, BigDecimal> discountCodes = new HashMap<>();

    public OrderService(OrderRepository repository, TaxTable taxTable) {
        this.repository = repository;
        this.taxTable = taxTable;
    }

    public void registerDiscount(String code, BigDecimal percent) {
        if (percent.compareTo(BigDecimal.ZERO) <= 0 || percent.compareTo(new BigDecimal("90")) > 0) {
            throw new IllegalArgumentException("discount out of range: " + percent);
        }
        discountCodes.put(code.toUpperCase(), percent);
    }

    public Order createOrder(String customerId, List<LineItem> items, String discountCode) {
        if (customerId == null || customerId.isEmpty()) {
            throw new IllegalArgumentException("customer id required");
        }
        if (items == null || items.isEmpty()) {
            throw new IllegalArgumentException("order must contain at least one item");
        }
        Order order = new Order(repository.nextId(), customerId, LocalDate.now());
        for (LineItem item : items) {
            if (item.getQuantity() <= 0) {
                throw new IllegalArgumentException("bad quantity for " + item.getSku());
            }
            order.addItem(item);
        }
        BigDecimal subtotal = computeSubtotal(order);
        BigDecimal discount = BigDecimal.ZERO;
        if (discountCode != null) {
            BigDecimal pct = discountCodes.get(discountCode.toUpperCase());
            if (pct != null) {
                discount = subtotal.multiply(pct).divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);
            }
        }
        BigDecimal taxable = subtotal.subtract(discount);
        BigDecimal tax = taxTable.rateFor(order.getRegion()).multiply(taxable).setScale(2, RoundingMode.HALF_UP);
        order.setSubtotal(subtotal);
        order.setDiscount(discount);
        order.setTax(tax);
        order.setTotal(taxable.add(tax));
        order.setStatus(OrderStatus.PENDING);
        repository.save(order);
        return order;
    }

    BigDecimal computeSubtotal(Order order) {
        BigDecimal sum = BigDecimal.ZERO;
        for (LineItem item : order.getItems()) {
            BigDecimal line = item.getUnitPrice().multiply(BigDecimal.valueOf(item.getQuantity()));
            sum = sum.add(line);
        }
        return sum.setScale(2, RoundingMode.HALF_UP);
    }

    public Order cancelOrder(long orderId, String reason) {
        Order order = repository.findById(orderId)
                .orElseThrow(() -> new IllegalStateException("no such order " + orderId));
        if (order.getStatus() == OrderStatus.SHIPPED) {
            throw new IllegalStateException("cannot cancel shipped order " + orderId);
        }
        order.setStatus(OrderStatus.CANCELLED);
        order.setNote(reason);
        repository.save(order);
        return order;
    }

    public Order markShipped(long orderId, String trackingNumber) {
        Order order = repository.findById(orderId)
                .orElseThrow(() -> new IllegalStateException("no such order " + orderId));
        if (order.getStatus() != OrderStatus.PENDING) {
            throw new IllegalStateException("order not pending: " + orderId);
        }
        order.setTrackingNumber(trackingNumber);
        order.setStatus(OrderStatus.SHIPPED);
        repository.save(order);
        return order;
    }

    public List<Order> openOrdersFor(String customerId) {
        List<Order> result = new ArrayList<>();
        for (Order o : repository.findByCustomer(customerId)) {
            if (o.getStatus() == OrderStatus.PENDING) {
                result.add(o);
            }
        }
        return result;
    }

    public Optional<Order> largestOrder(String customerId) {
        Order best = null;
        for (Order o : repository.findByCustomer(customerId)) {
            if (best == null || o.getTotal().compareTo(best.getTotal()) > 0) {
                best = o;
            }
        }
        return Optional.ofNullable(best);
    }

    public BigDecimal revenueBetween(LocalDate from, LocalDate to) {
        BigDecimal total = BigDecimal.ZERO;
        for (Order o : repository.findAll()) {
            if (o.getStatus() == OrderStatus.CANCELLED) {
                continue;
            }
            LocalDate d = o.getCreatedOn();
            if (!d.isBefore(from) && !d.isAfter(to)) {
                total = total.add(o.getTotal());
            }
        }
        return total;
    }
}
