/*  Copyright (C) 2026 Glasser Draco

    This file is part of Gadgetbridge.

    Gadgetbridge is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version. */
package nodomain.freeyourgadget.gadgetbridge.externalevents.hfimu;

import java.util.Locale;
import java.util.Map;

public final class HfImuCliResultFormatter {
    private HfImuCliResultFormatter() {
    }

    public static String format(final Map<String, String> fields) {
        final StringBuilder builder = new StringBuilder();
        builder.append('{');
        boolean first = true;
        for (final Map.Entry<String, String> entry : fields.entrySet()) {
            if (!first) {
                builder.append(',');
            }
            first = false;
            builder.append('"').append(escape(entry.getKey())).append('"').append(':');
            builder.append('"').append(escape(redact(entry.getKey(), entry.getValue()))).append('"');
        }
        builder.append('}');
        return builder.toString();
    }

    private static String redact(final String key, final String value) {
        if (value == null) {
            return "";
        }
        final String normalized = key == null ? "" : key.toLowerCase(Locale.ROOT);
        if (normalized.contains("auth") || normalized.contains("token") || normalized.contains("password") || normalized.contains("secret")) {
            return "[REDACTED]";
        }
        return value;
    }

    private static String escape(final String value) {
        if (value == null) {
            return "";
        }
        final StringBuilder escaped = new StringBuilder(value.length());
        for (int i = 0; i < value.length(); i++) {
            final char c = value.charAt(i);
            switch (c) {
                case '\\':
                    escaped.append("\\\\");
                    break;
                case '"':
                    escaped.append("\\\"");
                    break;
                case '\n':
                    escaped.append("\\n");
                    break;
                case '\r':
                    escaped.append("\\r");
                    break;
                case '\t':
                    escaped.append("\\t");
                    break;
                default:
                    if (c < 0x20) {
                        escaped.append(String.format(Locale.ROOT, "\\u%04x", (int) c));
                    } else {
                        escaped.append(c);
                    }
                    break;
            }
        }
        return escaped.toString();
    }
}
