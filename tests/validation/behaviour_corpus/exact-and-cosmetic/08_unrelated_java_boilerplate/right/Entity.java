package org.freightco.logistics.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

public class Shipment {

    private String trackingNumber;
    private String origin;
    private String destination;
    private BigDecimal weightKg;
    private Instant dispatchedAt;
    private int parcels;

    public Shipment() {
    }

    public Shipment(String trackingNumber, String origin, String destination, BigDecimal weightKg) {
        this.trackingNumber = trackingNumber;
        this.origin = origin;
        this.destination = destination;
        this.weightKg = weightKg;
        this.parcels = 1;
    }

    public String getTrackingNumber() {
        return trackingNumber;
    }

    public void setTrackingNumber(String trackingNumber) {
        this.trackingNumber = trackingNumber;
    }

    public String getOrigin() {
        return origin;
    }

    public void setOrigin(String origin) {
        this.origin = origin;
    }

    public String getDestination() {
        return destination;
    }

    public void setDestination(String destination) {
        this.destination = destination;
    }

    public BigDecimal getWeightKg() {
        return weightKg;
    }

    public void setWeightKg(BigDecimal weightKg) {
        this.weightKg = weightKg;
    }

    public Instant getDispatchedAt() {
        return dispatchedAt;
    }

    public void setDispatchedAt(Instant dispatchedAt) {
        this.dispatchedAt = dispatchedAt;
    }

    public int getParcels() {
        return parcels;
    }

    public void setParcels(int parcels) {
        this.parcels = parcels;
    }

    public boolean isInternational() {
        return origin != null && destination != null
                && !origin.substring(0, 2).equals(destination.substring(0, 2));
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (o == null || getClass() != o.getClass()) {
            return false;
        }
        Shipment that = (Shipment) o;
        return Objects.equals(trackingNumber, that.trackingNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(trackingNumber);
    }

    @Override
    public String toString() {
        return "Shipment{" + trackingNumber + " " + origin + "->" + destination + ", " + weightKg + "kg}";
    }
}
