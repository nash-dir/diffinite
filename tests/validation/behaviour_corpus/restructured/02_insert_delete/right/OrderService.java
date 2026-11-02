package com.acme.orders;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.Logger;

public class OrderService {

    private static final Logger LOG = Logger.getLogger(OrderService.class.getName());

    private final OrderRepository repository;
    private final TaxTable taxTable;
    private final Map<String, BigDecimal> discountCodes = new HashMap<>();
    private int ordersCreated = 0;

    public OrderService(OrderRepository repository, TaxTable taxTable) {
        this.repository = repository;
        this.taxTable = taxTable;
        LOG.info("OrderService initialised");
    }

    public void registerDiscount(String code, BigDecimal percent) {
        discountCodes.put(code.toUpperCase(), percent);
        LOG.fine("registered discount " + code);
    }

    public Order createOrder(String customerId, List<LineItem> items, String discountCode) {
        if (customerId == null || customerId.isEmpty()) {
            throw new IllegalArgumentException("customer id required");
        }
        if (items == null || items.isEmpty()) {
            throw new IllegalArgumentException("order must contain at least one item");
        }
        LOG.fine("creating order for " + customerId);
        Order order = new Order(repository.nextId(), customerId, LocalDate.now());
        for (LineItem item : items) {
            order.addItem(item);
        }
        BigDecimal subtotal = computeSubtotal(order);
        BigDecimal discount = BigDecimal.ZERO;
        if (discountCode != null) {
            BigDecimal pct = discountCodes.get(discountCode.toUpperCase());
            if (pct != null) {
                discount = subtotal.multiply(pct).divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);
                LOG.fine("applied discount " + discountCode + " = " + discount);
            } else {
                LOG.warning("unknown discount code " + discountCode);
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
        ordersCreated++;
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
        if (order.getStatus() == OrderStatus.CANCELLED) {
            LOG.info("order already cancelled " + orderId);
            return order;
        }
        order.setStatus(OrderStatus.CANCELLED);
        order.setNote(reason);
        order.setCancelledOn(LocalDate.now());
        repository.save(order);
        LOG.info("cancelled order " + orderId + ": " + reason);
        return order;
    }

    public Order markShipped(long orderId, String trackingNumber) {
        Order order = repository.findById(orderId)
                .orElseThrow(() -> new IllegalStateException("no such order " + orderId));
        if (order.getStatus() != OrderStatus.PENDING) {
            throw new IllegalStateException("order not pending: " + orderId);
        }
        if (trackingNumber == null || trackingNumber.trim().isEmpty()) {
            throw new IllegalArgumentException("tracking number required");
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

    public int getOrdersCreated() {
        return ordersCreated;
    }
}
