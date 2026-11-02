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
package org.example.weather;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

/** Loads station configuration from a properties file on the classpath. */
public final class Config {
    private final String stationId;
    private final double latitude;
    private final double longitude;
    private final int pollSeconds;

    private Config(String stationId, double latitude, double longitude, int pollSeconds) {
        this.stationId = stationId;
        this.latitude = latitude;
        this.longitude = longitude;
        this.pollSeconds = pollSeconds;
    }

    public static Config load(String resource) throws IOException {
        Properties p = new Properties();
        try (InputStream in = Config.class.getResourceAsStream(resource)) {
            if (in == null) {
                throw new IOException("missing resource " + resource);
            }
            p.load(in);
        }
        String id = p.getProperty("station.id", "UNKNOWN");
        double lat = Double.parseDouble(p.getProperty("station.lat", "0"));
        double lon = Double.parseDouble(p.getProperty("station.lon", "0"));
        int poll = Integer.parseInt(p.getProperty("poll.seconds", "60"));
        if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
            throw new IllegalArgumentException("coordinates out of range");
        }
        return new Config(id, lat, lon, Math.max(10, poll));
    }

    public String stationId() { return stationId; }
    public double latitude() { return latitude; }
    public double longitude() { return longitude; }
    public int pollSeconds() { return pollSeconds; }

    public double distanceKmTo(double lat2, double lon2) {
        double r = 6371.0;
        double dLat = Math.toRadians(lat2 - latitude);
        double dLon = Math.toRadians(lon2 - longitude);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(latitude)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return 2 * r * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    @Override
    public String toString() {
        return "Config[" + stationId + " @ " + latitude + "," + longitude + "]";
    }
}
