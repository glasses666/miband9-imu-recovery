/*  Copyright (C) 2026 Glasser Draco

    This file is part of Gadgetbridge.

    Gadgetbridge is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version. */
package nodomain.freeyourgadget.gadgetbridge.externalevents.hfimu;

public final class HfImuCliContract {
    public static final String ACTION_SUFFIX = ".CLI";
    public static final String EXTRA_COMMAND = "command";
    public static final String EXTRA_REQUEST_ID = "request_id";
    public static final String EXTRA_NONCE = "nonce";
    public static final String EXTRA_SECONDS = "seconds";
    public static final String EXTRA_NAME = "name";
    public static final String EXTRA_ADDRESS = "address";
    public static final String EXTRA_RESET_BOND = "reset_bond";
    public static final String EXTRA_CONNECT_TIMEOUT_SECONDS = "connect_timeout_seconds";
    public static final String EXTRA_FORCE_CONNECTION_TYPE = "force_connection_type";
    public static final String EXTRA_PORTS = "ports";
    public static final String EXTRA_HEX = "hex";
    public static final String EXTRA_PORT_CONNECT_TIMEOUT_MS = "port_connect_timeout_ms";
    public static final String EXTRA_PORT_READ_MS = "port_read_ms";
    public static final String EXTRA_DISCONNECT_FIRST = "disconnect_first";
    public static final String EXTRA_PORT = "port";
    public static final String EXTRA_CAPTURE_MS = "capture_ms";
    public static final String EXTRA_MAX_PACKETS = "max_packets";
    public static final String EXTRA_FIND_DURATION_MS = "find_duration_ms";
    public static final String EXTRA_GAMESIR_HANDSHAKE = "gamesir_handshake";
    public static final String EXTRA_GAMESIR_BOND = "gamesir_bond";
    public static final String EXTRA_GAMESIR_HISTORICAL_010103 = "gamesir_historical_010103";
    public static final String EXTRA_XMS_START = "xms_start";
    public static final String EXTRA_XMS_SPORT_TYPE = "xms_sport_type";
    public static final String EXTRA_XMS_DID = "xms_did";
    public static final String EXTRA_XMS_TIMEZONE = "xms_timezone";
    public static final String EXTRA_XMS_SPORT_STATE = "xms_sport_state";

    public static final String COMMAND_PING = "ping";
    public static final String COMMAND_START_SERVICE = "start-service";
    public static final String COMMAND_ENABLE_DEBUG = "enable-debug";
    public static final String COMMAND_DUMP_STATE = "dump-state";
    public static final String COMMAND_KNOWN_DEVICES = "known-devices";
    public static final String COMMAND_ENABLE_BLUETOOTH = "enable-bluetooth";
    public static final String COMMAND_SCAN = "scan";
    public static final String COMMAND_PAIR = "pair";
    public static final String COMMAND_CONNECT = "connect";
    public static final String COMMAND_PORT_PROBE = "port-probe";
    public static final String COMMAND_IMU_CAPTURE = "imu-capture";
    public static final String COMMAND_FIND_BAND = "find-band";
    public static final String COMMAND_MI_FIND_BAND = "mi-find-band";
    public static final String COMMAND_GAMESIR_PROBE = "gamesir-probe";
    public static final String COMMAND_DFU_STATUS_PROBE = "dfu-status-probe";
    public static final String COMMAND_SPORT_XMS_PROBE = "sport-xms-probe";
    public static final String COMMAND_GB_SPORT_XMS_OPEN = "gb-sport-xms-open";
    public static final String COMMAND_GB_SPORT_XMS_STOP = "gb-sport-xms-stop";

    public static final String LOG_TAG_RESULT = "MI_HFIMU_RESULT";
    public static final String LOG_TAG_STATE = "MI_HFIMU_STATE";
    public static final String LOG_TAG_ERROR = "MI_HFIMU_ERROR";

    private HfImuCliContract() {
    }

    public static String actionForPackage(final String packageName) {
        return packageName + ACTION_SUFFIX;
    }
}
