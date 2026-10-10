// This file is part of IBC.
// For conditions of distribution and use, see copyright notice in COPYING.txt

// IBC is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// IBC is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.

// You should have received a copy of the GNU General Public License
// along with IBC.  If not, see <http://www.gnu.org/licenses/>.

package ibcalpha.ibc;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.time.Instant;

/**
 * Appends machine-readable events (one JSON object per line) to the file named
 * by the EventLogFile setting, so that external supervisors (such as the ibc2
 * watchdog) can react to things like "second factor authentication needed" or
 * "stuck on an unrecognised dialog". Does nothing if EventLogFile is not set.
 * Never throws.
 */
class Events {
    private Events() {}

    static final String LOGIN_STARTED = "LOGIN_STARTED";
    static final String TWO_FA_REQUIRED = "TWO_FA_REQUIRED";
    static final String LOGGED_IN = "LOGGED_IN";
    static final String LOGIN_FAILED = "LOGIN_FAILED";
    static final String UNKNOWN_WINDOW = "UNKNOWN_WINDOW";
    static final String RULE_APPLIED = "RULE_APPLIED";
    static final String EXIT = "EXIT";

    static synchronized void emit(String type, String detail) {
        try {
            String path = Settings.settings().getString("EventLogFile", "");
            if (path.isEmpty()) return;
            String line = "{\"time\":\"" + Instant.now() + "\",\"type\":\"" + escape(type)
                    + "\",\"detail\":\"" + escape(detail) + "\"}" + System.lineSeparator();
            Files.write(Paths.get(path), line.getBytes(StandardCharsets.UTF_8),
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException | RuntimeException e) {
            // an event log failure must never disturb the session
        }
    }

    static String escape(String s) {
        if (s == null) return "";
        StringBuilder sb = new StringBuilder(s.length() + 16);
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
            }
        }
        return sb.toString();
    }
}
