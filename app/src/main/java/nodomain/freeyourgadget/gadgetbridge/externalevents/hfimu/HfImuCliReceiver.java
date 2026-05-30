/*  Copyright (C) 2026 Glasser Draco

    This file is part of Gadgetbridge.

    Gadgetbridge is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version. */
package nodomain.freeyourgadget.gadgetbridge.externalevents.hfimu;

import android.bluetooth.BluetoothAdapter;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.util.Log;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import nodomain.freeyourgadget.gadgetbridge.GBApplication;
import nodomain.freeyourgadget.gadgetbridge.database.DBHandler;
import nodomain.freeyourgadget.gadgetbridge.database.DBHelper;
import nodomain.freeyourgadget.gadgetbridge.entities.DaoSession;
import nodomain.freeyourgadget.gadgetbridge.entities.Device;
import nodomain.freeyourgadget.gadgetbridge.util.Prefs;

public class HfImuCliReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(final Context context, final Intent intent) {
        if (intent == null) {
            logError(context, "unknown", "", "", "missing_intent");
            return;
        }

        final String action = intent.getAction();
        final String expectedAction = HfImuCliContract.actionForPackage(context.getPackageName());
        final String command = valueOrDefault(intent.getStringExtra(HfImuCliContract.EXTRA_COMMAND), HfImuCliContract.COMMAND_PING);
        final String requestId = valueOrEmpty(intent.getStringExtra(HfImuCliContract.EXTRA_REQUEST_ID));
        final String nonce = valueOrEmpty(intent.getStringExtra(HfImuCliContract.EXTRA_NONCE));

        if (!expectedAction.equals(action)) {
            logError(context, command, requestId, nonce, "unexpected_action");
            return;
        }

        switch (command) {
            case HfImuCliContract.COMMAND_PING:
                logResult(context, command, requestId, nonce, "ok", "pong", null);
                break;
            case HfImuCliContract.COMMAND_DUMP_STATE:
                dumpState(context, command, requestId, nonce);
                break;
            case HfImuCliContract.COMMAND_KNOWN_DEVICES:
                dumpKnownDevices(context, command, requestId, nonce);
                break;
            case HfImuCliContract.COMMAND_ENABLE_BLUETOOTH:
                enableBluetooth(context, command, requestId, nonce);
                break;
            case HfImuCliContract.COMMAND_SCAN:
            case HfImuCliContract.COMMAND_PAIR:
            case HfImuCliContract.COMMAND_CONNECT:
            case HfImuCliContract.COMMAND_PORT_PROBE:
            case HfImuCliContract.COMMAND_IMU_CAPTURE:
            case HfImuCliContract.COMMAND_FIND_BAND:
            case HfImuCliContract.COMMAND_GAMESIR_PROBE:
            case HfImuCliContract.COMMAND_SPORT_XMS_PROBE:
                startCliService(context, command, requestId, nonce, intent);
                break;
            case HfImuCliContract.COMMAND_ENABLE_DEBUG:
                enableDebugCommands(context, command, requestId, nonce);
                break;
            case HfImuCliContract.COMMAND_START_SERVICE:
                startCliService(context, command, requestId, nonce, intent);
                break;
            default:
                logError(context, command, requestId, nonce, "unknown_command");
                break;
        }
    }

    private void startCliService(final Context context, final String command, final String requestId, final String nonce,
                                 final Intent sourceIntent) {
        final Intent serviceIntent = new Intent(context, HfImuCliService.class);
        serviceIntent.putExtra(HfImuCliContract.EXTRA_COMMAND, command);
        serviceIntent.putExtra(HfImuCliContract.EXTRA_REQUEST_ID, requestId);
        serviceIntent.putExtra(HfImuCliContract.EXTRA_NONCE, nonce);
        if (sourceIntent != null) {
            serviceIntent.putExtra(HfImuCliContract.EXTRA_SECONDS, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_SECONDS));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_NAME, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_NAME));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_ADDRESS, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_ADDRESS));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_RESET_BOND, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_RESET_BOND));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_CONNECT_TIMEOUT_SECONDS, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_CONNECT_TIMEOUT_SECONDS));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_PORTS, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_PORTS));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_HEX, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_HEX));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_PORT_CONNECT_TIMEOUT_MS, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_PORT_CONNECT_TIMEOUT_MS));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_PORT_READ_MS, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_PORT_READ_MS));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_DISCONNECT_FIRST, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_DISCONNECT_FIRST));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_PORT, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_PORT));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_CAPTURE_MS, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_CAPTURE_MS));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_MAX_PACKETS, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_MAX_PACKETS));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_FIND_DURATION_MS, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_FIND_DURATION_MS));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_GAMESIR_HANDSHAKE, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_GAMESIR_HANDSHAKE));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_GAMESIR_BOND, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_GAMESIR_BOND));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_GAMESIR_HISTORICAL_010103, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_GAMESIR_HISTORICAL_010103));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_XMS_START, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_XMS_START));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_XMS_SPORT_TYPE, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_XMS_SPORT_TYPE));
            serviceIntent.putExtra(HfImuCliContract.EXTRA_XMS_DID, sourceIntent.getStringExtra(HfImuCliContract.EXTRA_XMS_DID));
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent);
            } else {
                context.startService(serviceIntent);
            }
            logResult(context, command, requestId, nonce, "ok", "service_start_requested", null);
        } catch (final IllegalStateException e) {
            logResult(context, command, requestId, nonce, "error", "service_start_failed", e.getClass().getSimpleName());
        }
    }

    private void dumpState(final Context context, final String command, final String requestId, final String nonce) {
        boolean debugAllowed = false;
        try {
            final Prefs prefs = GBApplication.getPrefs();
            debugAllowed = prefs.getBoolean("intent_api_allow_debug_commands", false);
        } catch (final Exception e) {
            logResult(context, command, requestId, nonce, "error", "prefs_unavailable", e.getClass().getSimpleName());
            return;
        }

        final Map<String, String> fields = baseFields(context, command, requestId, nonce, "ok");
        fields.put("message", "state");
        fields.put("debug_allowed", Boolean.toString(debugAllowed));
        fields.put("headless", "true");
        Log.i(HfImuCliContract.LOG_TAG_STATE, HfImuCliResultFormatter.format(fields));
    }

    private void enableBluetooth(final Context context, final String command, final String requestId, final String nonce) {
        final BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        if (adapter == null) {
            logResult(context, command, requestId, nonce, "error", "bluetooth_adapter_missing", null);
            return;
        }
        final boolean alreadyEnabled = adapter.isEnabled();
        final boolean requested = alreadyEnabled || adapter.enable();
        final Map<String, String> fields = baseFields(context, command, requestId, nonce, requested ? "ok" : "error");
        fields.put("message", requested ? "bluetooth_enable_requested" : "bluetooth_enable_failed");
        fields.put("already_enabled", Boolean.toString(alreadyEnabled));
        fields.put("enabled_now", Boolean.toString(adapter.isEnabled()));
        Log.i(requested ? HfImuCliContract.LOG_TAG_STATE : HfImuCliContract.LOG_TAG_ERROR, HfImuCliResultFormatter.format(fields));
    }

    private void dumpKnownDevices(final Context context, final String command, final String requestId, final String nonce) {
        final Map<String, String> fields = baseFields(context, command, requestId, nonce, "ok");
        fields.put("message", "known_devices");
        try (DBHandler db = GBApplication.acquireDB()) {
            final DaoSession daoSession = db.getDaoSession();
            final List<Device> devices = DBHelper.getActiveDevices(daoSession);
            fields.put("device_count", Integer.toString(devices.size()));
            for (int i = 0; i < devices.size(); i++) {
                final Device device = devices.get(i);
                final String prefix = "device_" + i + "_";
                final String identifier = valueOrEmpty(device.getIdentifier());
                fields.put(prefix + "address", identifier);
                fields.put(prefix + "name", valueOrEmpty(device.getName()));
                fields.put(prefix + "manufacturer", valueOrEmpty(device.getManufacturer()));
                fields.put(prefix + "type_name", valueOrEmpty(device.getTypeName()));
                fields.put(prefix + "model", valueOrEmpty(device.getModel()));
                fields.put(prefix + "credential_present", Boolean.toString(hasDeviceCredential(identifier)));
            }
            Log.i(HfImuCliContract.LOG_TAG_STATE, HfImuCliResultFormatter.format(fields));
        } catch (final Exception e) {
            logResult(context, command, requestId, nonce, "error", "known_devices_failed", e.getClass().getSimpleName());
        }
    }

    private boolean hasDeviceCredential(final String identifier) {
        if (identifier == null || identifier.length() == 0) {
            return false;
        }
        try {
            final SharedPreferences sharedPrefs = GBApplication.getDeviceSpecificSharedPrefs(identifier);
            return sharedPrefs.contains("authkey");
        } catch (final Exception e) {
            return false;
        }
    }

    private void enableDebugCommands(final Context context, final String command, final String requestId, final String nonce) {
        try {
            GBApplication.getPrefs().getPreferences().edit()
                    .putBoolean("intent_api_allow_debug_commands", true)
                    .apply();
            logResult(context, command, requestId, nonce, "ok", "debug_commands_enabled", null);
        } catch (final Exception e) {
            logResult(context, command, requestId, nonce, "error", "debug_enable_failed", e.getClass().getSimpleName());
        }
    }

    private void logError(final Context context, final String command, final String requestId, final String nonce, final String message) {
        logResult(context, command, requestId, nonce, "error", message, null);
    }

    private void logResult(final Context context, final String command, final String requestId, final String nonce,
                           final String status, final String message, final String errorClass) {
        final Map<String, String> fields = baseFields(context, command, requestId, nonce, status);
        fields.put("message", valueOrEmpty(message));
        if (errorClass != null) {
            fields.put("error_class", errorClass);
        }
        final String tag = "error".equals(status) ? HfImuCliContract.LOG_TAG_ERROR : HfImuCliContract.LOG_TAG_RESULT;
        Log.i(tag, HfImuCliResultFormatter.format(fields));
    }

    private Map<String, String> baseFields(final Context context, final String command, final String requestId,
                                           final String nonce, final String status) {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("status", status);
        fields.put("component", "receiver");
        fields.put("command", valueOrEmpty(command));
        fields.put("request_id", valueOrEmpty(requestId));
        fields.put("nonce", valueOrEmpty(nonce));
        fields.put("package", context == null ? "" : context.getPackageName());
        return fields;
    }

    private static String valueOrDefault(final String value, final String fallback) {
        return value == null || value.length() == 0 ? fallback : value;
    }

    private static String valueOrEmpty(final String value) {
        return value == null ? "" : value;
    }
}
