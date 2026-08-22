/*  Copyright (C) 2026 Glasser Draco

    This file is part of Gadgetbridge.

    Gadgetbridge is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version. */
package nodomain.freeyourgadget.gadgetbridge.externalevents.hfimu;

import org.junit.Test;

import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.Assert.assertEquals;

public class HfImuCliResultFormatterTest {
    @Test
    public void formatsStableJsonWithEscaping() {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("status", "ok");
        fields.put("request_id", "req-1");
        fields.put("message", "hello \"cli\"\\dragon");

        assertEquals(
                "{\"status\":\"ok\",\"request_id\":\"req-1\",\"message\":\"hello \\\"cli\\\"\\\\dragon\"}",
                HfImuCliResultFormatter.format(fields)
        );
    }

    @Test
    public void redactsSensitiveFieldNames() {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("auth_key", "secret-value");
        fields.put("refresh_token", "secret-token");
        fields.put("status", "ok");

        assertEquals(
                "{\"auth_key\":\"[REDACTED]\",\"refresh_token\":\"[REDACTED]\",\"status\":\"ok\"}",
                HfImuCliResultFormatter.format(fields)
        );
    }
}
