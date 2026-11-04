/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
package com.acme.queue;

import java.time.Duration;
import java.util.EnumMap;
import java.util.Map;

/**
 * Retry policy configuration for the message consumer.
 */
public class Config {

    public enum Priority { LOW, NORMAL, HIGH }

    private final Map<Priority, Integer> maxAttempts = new EnumMap<>(Priority.class);
    private Duration baseDelay = Duration.ofMillis(200);
    private double multiplier = 2.0;
    private Duration maxDelay = Duration.ofSeconds(30);

    public Config() {
        maxAttempts.put(Priority.LOW, 3);
        maxAttempts.put(Priority.NORMAL, 5);
        maxAttempts.put(Priority.HIGH, 10);
    }

    public Config withBaseDelay(Duration d) {
        if (d.isNegative() || d.isZero()) {
            throw new IllegalArgumentException("base delay must be positive");
        }
        this.baseDelay = d;
        return this;
    }

    public Config withMultiplier(double m) {
        if (m < 1.0) {
            throw new IllegalArgumentException("multiplier must be >= 1");
        }
        this.multiplier = m;
        return this;
    }

    public Config withMaxDelay(Duration d) {
        this.maxDelay = d;
        return this;
    }

    public Config attempts(Priority p, int n) {
        maxAttempts.put(p, n);
        return this;
    }

    public boolean shouldRetry(Priority p, int attempt) {
        return attempt < maxAttempts.getOrDefault(p, 1);
    }

    public Duration delayFor(int attempt) {
        double millis = baseDelay.toMillis() * Math.pow(multiplier, Math.max(0, attempt - 1));
        long capped = (long) Math.min(millis, (double) maxDelay.toMillis());
        return Duration.ofMillis(capped);
    }

    public static void main(String[] args) {
        Config c = new Config().withMultiplier(1.5).attempts(Priority.LOW, 2);
        for (int i = 1; i <= 6; i++) {
            System.out.printf("attempt %d -> retry=%s delay=%s%n",
                    i, c.shouldRetry(Priority.NORMAL, i), c.delayFor(i));
        }
    }
}
