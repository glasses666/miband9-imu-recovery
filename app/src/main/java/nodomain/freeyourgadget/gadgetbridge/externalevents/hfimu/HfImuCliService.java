/*  Copyright (C) 2026 Glasser Draco

    This file is part of Gadgetbridge.

    Gadgetbridge is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version. */
package nodomain.freeyourgadget.gadgetbridge.externalevents.hfimu;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.BluetoothSocket;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanRecord;
import android.bluetooth.le.ScanResult;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.ServiceConnection;
import android.os.Binder;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.Parcel;
import android.os.RemoteException;
import android.util.Log;

import androidx.localbroadcastmanager.content.LocalBroadcastManager;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TimeZone;
import java.util.UUID;

import nodomain.freeyourgadget.gadgetbridge.GBApplication;
import nodomain.freeyourgadget.gadgetbridge.R;
import nodomain.freeyourgadget.gadgetbridge.impl.GBDevice;
import nodomain.freeyourgadget.gadgetbridge.util.DeviceHelper;

public class HfImuCliService extends Service {
    private static final String CHANNEL_ID = "hfimucli";
    private static final int NOTIFICATION_ID = 42;
    private static final int MAX_SCAN_SECONDS = 30;
    private static final int PAIR_TIMEOUT_MS = 45000;
    private static final int CONNECT_TIMEOUT_MS = 90000;
    private static final String MI_BAND9_IMU_INIT_HEX = "A5A5020016001D4D0101030001000002020000FC03020020000402001027";
    private static final UUID GAMESIR_SERVICE = UUID.fromString("00008650-0000-1000-8000-00805f9b34fb");
    private static final UUID GAMESIR_HEARTBEAT_CHAR = UUID.fromString("0000865f-0000-1000-8000-00805f9b34fb");
    private static final UUID GAMESIR_UNLOCK_SERVICE = UUID.fromString("0000ff10-0000-1000-8000-00805f9b34fb");
    private static final UUID GAMESIR_UNLOCK_CHAR = UUID.fromString("0000ff12-0000-1000-8000-00805f9b34fb");
    private static final UUID GAMESIR_NOTIFY_CHAR = UUID.fromString("0000ff11-0000-1000-8000-00805f9b34fb");
    private static final UUID HID_SERVICE = UUID.fromString("00001812-0000-1000-8000-00805f9b34fb");
    private static final UUID HID_REPORT_CHAR = UUID.fromString("00002a4d-0000-1000-8000-00805f9b34fb");
    private static final UUID CCC_DESCRIPTOR = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    private static final byte[] GAMESIR_PRIME = new byte[]{0x07};
    private static final byte[] GAMESIR_UNLOCK_PAYLOAD = new byte[]{0x01, 0x15, 0x01, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x18};
    private static final byte[] GAMESIR_HISTORICAL_010103 = new byte[]{0x01, 0x01, 0x03};
    private static final String SPORT_XMS_ACTION = "com.xiaomi.fitness.SPORT_XMS_SERVICE";
    private static final String SPORT_XMS_PACKAGE = "com.mi.health";
    private static final String SPORT_XMS_INTERFACE = "com.xiaomi.fitness.sport_xms.launch.ISportXmsApi";
    private static final String SPORT_XMS_SENSOR_LISTENER = "com.xiaomi.fitness.sport_xms.listener.IRemoteSportXmsSensorDataChangedListener";
    private static final String SPORT_XMS_STATE_LISTENER = "com.xiaomi.fitness.sport_xms.listener.IRemoteSportXmsStateChangedListener";
    private static final int XMS_TRANSACTION_START_SPORT = 1;
    private static final int XMS_TRANSACTION_FINISH_SPORT_BY_TYPE = 24;
    private static final int XMS_TRANSACTION_SET_STATE_LISTENER = 7;
    private static final int XMS_TRANSACTION_SET_SENSOR_LISTENER = 9;
    private static final int XMS_TRANSACTION_IS_DEVICE_CONNECTED = 11;
    private static final int XMS_TRANSACTION_GET_DEVICE_BATTERY = 14;
    private static final int XMS_TRANSACTION_IS_SUPPORT_SOMATOSENSORY = 15;
    private static final int XMS_TRANSACTION_GET_DEVICE_INFO = 23;
    private static final int XMS_DEFAULT_SPORT_TYPE = 812;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Map<String, BluetoothDevice> scanDevices = new LinkedHashMap<>();

    private BroadcastReceiver scanReceiver;
    private String scanRequestId;
    private String scanNonce;
    private String scanTargetName;

    private BroadcastReceiver pairReceiver;
    private BluetoothDevice pairDevice;
    private String pairRequestId;
    private String pairNonce;
    private boolean pairResetRequested;
    private boolean pairCreateBondStarted;

    private BroadcastReceiver connectReceiver;
    private GBDevice connectDevice;
    private String connectRequestId;
    private String connectNonce;
    private String connectAddress;

    private BluetoothLeScanner gamesirScanner;
    private ScanCallback gamesirScanCallback;
    private BluetoothGatt gamesirGatt;
    private long gamesirStartedMs;
    private String gamesirRequestId;
    private String gamesirNonce;
    private String gamesirTargetName;
    private String gamesirTargetAddress;
    private boolean gamesirHandshake;
    private boolean gamesirBond;
    private boolean gamesirHistorical010103;
    private int gamesirCandidateCount;
    private int gamesirServiceCount;
    private int gamesirWriteCount;
    private int gamesirNotificationCount;

    private ServiceConnection sportXmsConnection;
    private IBinder sportXmsBinder;
    private String sportXmsRequestId;
    private String sportXmsNonce;
    private String sportXmsDid;
    private String sportXmsDidOverride;
    private long sportXmsStartedMs;
    private int sportXmsCaptureMs;
    private int sportXmsSportType;
    private boolean sportXmsShouldStart;
    private boolean sportXmsStarted;
    private int sportXmsSensorPackets;
    private int sportXmsAccelSamples;
    private int sportXmsGyroSamples;

    @Override
    public void onCreate() {
        super.onCreate();
        ensureNotificationChannel();
        logState("created", null, null);
    }

    @Override
    public int onStartCommand(final Intent intent, final int flags, final int startId) {
        final String requestId = intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_REQUEST_ID);
        final String nonce = intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_NONCE);
        final String command = intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_COMMAND);
        startForeground(NOTIFICATION_ID, buildNotification());
        logState("started", requestId, nonce);
        if (HfImuCliContract.COMMAND_SCAN.equals(command)) {
            startScan(intent, requestId, nonce);
        } else if (HfImuCliContract.COMMAND_PAIR.equals(command)) {
            startPair(intent, requestId, nonce);
        } else if (HfImuCliContract.COMMAND_CONNECT.equals(command)) {
            startConnect(intent, requestId, nonce);
        } else if (HfImuCliContract.COMMAND_PORT_PROBE.equals(command)) {
            startPortProbe(intent, requestId, nonce);
        } else if (HfImuCliContract.COMMAND_IMU_CAPTURE.equals(command)) {
            startImuCapture(intent, requestId, nonce);
        } else if (HfImuCliContract.COMMAND_GAMESIR_PROBE.equals(command)) {
            startGamesirProbe(intent, requestId, nonce);
        } else if (HfImuCliContract.COMMAND_SPORT_XMS_PROBE.equals(command)) {
            startSportXmsProbe(intent, requestId, nonce);
        }
        return START_STICKY;
    }

    @Override
    public IBinder onBind(final Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        cleanupScanReceiver();
        cleanupPairReceiver();
        cleanupConnectReceiver();
        cleanupGamesirProbe();
        cleanupSportXmsProbe(false);
        super.onDestroy();
    }

    private Notification buildNotification() {
        final Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return builder
                .setSmallIcon(R.drawable.ic_device_miband6)
                .setContentTitle("Gadgetbridge HF IMU CLI")
                .setContentText("Headless IMU control service is running")
                .setOngoing(true)
                .build();
    }

    private void ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        final NotificationManager notificationManager = getSystemService(NotificationManager.class);
        if (notificationManager == null) {
            return;
        }
        final NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "HF IMU CLI",
                NotificationManager.IMPORTANCE_LOW
        );
        notificationManager.createNotificationChannel(channel);
    }

    private void startScan(final Intent intent, final String requestId, final String nonce) {
        cleanupScanReceiver();
        final BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        if (adapter == null) {
            logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_SCAN, "error", "scan_failed", requestId, nonce,
                    singleField("reason", "bluetooth_adapter_missing"));
            return;
        }
        if (!adapter.isEnabled()) {
            logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_SCAN, "error", "scan_failed", requestId, nonce,
                    singleField("reason", "bluetooth_disabled"));
            return;
        }

        scanRequestId = requestId;
        scanNonce = nonce;
        scanTargetName = valueOrEmpty(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_NAME));
        scanDevices.clear();
        final int seconds = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_SECONDS), 10), 1, MAX_SCAN_SECONDS);

        scanReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(final Context context, final Intent foundIntent) {
                final String action = foundIntent == null ? null : foundIntent.getAction();
                if (BluetoothDevice.ACTION_FOUND.equals(action)) {
                    final BluetoothDevice device = foundIntent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
                    rememberScannedDevice(device);
                } else if (BluetoothAdapter.ACTION_DISCOVERY_FINISHED.equals(action)) {
                    finishScan(adapter, "scan_complete");
                }
            }
        };
        final IntentFilter filter = new IntentFilter();
        filter.addAction(BluetoothDevice.ACTION_FOUND);
        filter.addAction(BluetoothAdapter.ACTION_DISCOVERY_FINISHED);
        registerReceiver(scanReceiver, filter);

        if (adapter.isDiscovering()) {
            adapter.cancelDiscovery();
        }
        final boolean started = adapter.startDiscovery();
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("seconds", Integer.toString(seconds));
        fields.put("name", scanTargetName);
        fields.put("start_discovery", Boolean.toString(started));
        logCommand(started ? HfImuCliContract.LOG_TAG_STATE : HfImuCliContract.LOG_TAG_ERROR,
                HfImuCliContract.COMMAND_SCAN,
                started ? "ok" : "error",
                started ? "scan_started" : "scan_failed",
                requestId,
                nonce,
                fields);
        if (!started) {
            cleanupScanReceiver();
            return;
        }
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                finishScan(adapter, "scan_complete");
            }
        }, seconds * 1000L);
    }

    private void rememberScannedDevice(final BluetoothDevice device) {
        if (device == null || device.getAddress() == null) {
            return;
        }
        final String name = valueOrEmpty(device.getName());
        if (scanTargetName.length() > 0 && !name.toLowerCase().contains(scanTargetName.toLowerCase())) {
            return;
        }
        scanDevices.put(device.getAddress(), device);
    }

    private void finishScan(final BluetoothAdapter adapter, final String message) {
        if (scanReceiver == null) {
            return;
        }
        if (adapter != null && adapter.isDiscovering()) {
            adapter.cancelDiscovery();
        }
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("message", message);
        fields.put("target_name", valueOrEmpty(scanTargetName));
        fields.put("device_count", Integer.toString(scanDevices.size()));
        int index = 0;
        for (BluetoothDevice device : scanDevices.values()) {
            final String prefix = "device_" + index + "_";
            fields.put(prefix + "address", valueOrEmpty(device.getAddress()));
            fields.put(prefix + "name", valueOrEmpty(device.getName()));
            fields.put(prefix + "bond_state", bondStateName(device.getBondState()));
            index++;
        }
        cleanupScanReceiver();
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_SCAN, "ok", message, scanRequestId, scanNonce, fields);
    }

    private void cleanupScanReceiver() {
        if (scanReceiver == null) {
            return;
        }
        try {
            unregisterReceiver(scanReceiver);
        } catch (final IllegalArgumentException ignored) {
            // Receiver was already gone.
        }
        scanReceiver = null;
    }

    private void startPair(final Intent intent, final String requestId, final String nonce) {
        cleanupPairReceiver();
        final BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        final String address = valueOrEmpty(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_ADDRESS)).toUpperCase();
        pairResetRequested = parseBoolean(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_RESET_BOND));
        pairCreateBondStarted = false;
        pairRequestId = requestId;
        pairNonce = nonce;

        if (adapter == null) {
            logPairFinal("error", "pair_failed", address, "", "UNKNOWN", "bluetooth_adapter_missing");
            return;
        }
        if (!adapter.isEnabled()) {
            logPairFinal("error", "pair_failed", address, "", "UNKNOWN", "bluetooth_disabled");
            return;
        }
        if (!BluetoothAdapter.checkBluetoothAddress(address)) {
            logPairFinal("error", "pair_failed", address, "", "UNKNOWN", "invalid_address");
            return;
        }
        if (adapter.isDiscovering()) {
            adapter.cancelDiscovery();
        }

        pairDevice = adapter.getRemoteDevice(address);
        pairReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(final Context context, final Intent pairIntent) {
                final String action = pairIntent == null ? null : pairIntent.getAction();
                final BluetoothDevice device = pairIntent == null ? null : pairIntent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
                if (!sameDevice(device, pairDevice)) {
                    return;
                }
                if (BluetoothDevice.ACTION_PAIRING_REQUEST.equals(action)) {
                    logPairEvent("ok", "pairing_request", null);
                    attemptPairingConfirmation(device);
                    return;
                }
                if (BluetoothDevice.ACTION_BOND_STATE_CHANGED.equals(action)) {
                    final int state = pairIntent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, -1);
                    if (state == BluetoothDevice.BOND_BONDED) {
                        logPairFinal("ok", "pair_complete", device.getAddress(), valueOrEmpty(device.getName()), bondStateName(state), null);
                    } else if (state == BluetoothDevice.BOND_NONE) {
                        if (pairResetRequested && !pairCreateBondStarted) {
                            beginCreateBond();
                        } else if (pairCreateBondStarted) {
                            logPairFinal("error", "pair_failed", device.getAddress(), valueOrEmpty(device.getName()), bondStateName(state), "bond_none_after_create_bond");
                        }
                    }
                }
            }
        };
        final IntentFilter filter = new IntentFilter();
        filter.addAction(BluetoothDevice.ACTION_BOND_STATE_CHANGED);
        filter.addAction(BluetoothDevice.ACTION_PAIRING_REQUEST);
        registerReceiver(pairReceiver, filter);

        final int currentState = pairDevice.getBondState();
        logPairEvent("ok", "pair_started", singleField("initial_bond_state", bondStateName(currentState)));
        if (pairResetRequested && currentState == BluetoothDevice.BOND_BONDED) {
            final boolean removeRequested = invokeBooleanMethod(pairDevice, "removeBond");
            final Map<String, String> fields = singleField("remove_bond_requested", Boolean.toString(removeRequested));
            fields.put("initial_bond_state", bondStateName(currentState));
            logPairEvent(removeRequested ? "ok" : "error", removeRequested ? "remove_bond_requested" : "pair_failed", fields);
            if (!removeRequested) {
                logPairFinal("error", "pair_failed", pairDevice.getAddress(), valueOrEmpty(pairDevice.getName()), bondStateName(currentState), "remove_bond_failed");
                return;
            }
        } else if (currentState == BluetoothDevice.BOND_BONDED) {
            logPairFinal("ok", "pair_complete", pairDevice.getAddress(), valueOrEmpty(pairDevice.getName()), bondStateName(currentState), null);
        } else {
            beginCreateBond();
        }

        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (pairReceiver == null || pairDevice == null) {
                    return;
                }
                final int state = pairDevice.getBondState();
                final String message = state == BluetoothDevice.BOND_BONDING ? "needs_band_confirm" : "pair_timeout";
                logPairFinal("error", message, pairDevice.getAddress(), valueOrEmpty(pairDevice.getName()), bondStateName(state), message);
            }
        }, PAIR_TIMEOUT_MS);
    }

    private void beginCreateBond() {
        if (pairDevice == null) {
            logPairFinal("error", "pair_failed", "", "", "UNKNOWN", "missing_pair_device");
            return;
        }
        pairCreateBondStarted = true;
        final boolean createRequested = pairDevice.createBond();
        final Map<String, String> fields = singleField("create_bond_requested", Boolean.toString(createRequested));
        fields.put("bond_state", bondStateName(pairDevice.getBondState()));
        logPairEvent(createRequested ? "ok" : "error", createRequested ? "create_bond_requested" : "pair_failed", fields);
        if (!createRequested && pairDevice.getBondState() != BluetoothDevice.BOND_BONDING) {
            logPairFinal("error", "pair_failed", pairDevice.getAddress(), valueOrEmpty(pairDevice.getName()), bondStateName(pairDevice.getBondState()), "create_bond_failed");
        }
    }

    private void attemptPairingConfirmation(final BluetoothDevice device) {
        try {
            final Method method = device.getClass().getMethod("setPairingConfirmation", boolean.class);
            method.invoke(device, true);
            logPairEvent("ok", "pairing_confirmation_attempted", null);
        } catch (final Exception e) {
            final Map<String, String> fields = singleField("error_class", e.getClass().getSimpleName());
            logPairEvent("error", "pairing_confirmation_failed", fields);
        }
    }

    private void logPairEvent(final String status, final String message, final Map<String, String> extraFields) {
        final Map<String, String> fields = extraFields == null ? new LinkedHashMap<String, String>() : new LinkedHashMap<>(extraFields);
        if (pairDevice != null) {
            fields.put("address", valueOrEmpty(pairDevice.getAddress()));
            fields.put("name", valueOrEmpty(pairDevice.getName()));
            fields.put("bond_state", bondStateName(pairDevice.getBondState()));
        }
        fields.put("reset_requested", Boolean.toString(pairResetRequested));
        logCommand("error".equals(status) ? HfImuCliContract.LOG_TAG_ERROR : HfImuCliContract.LOG_TAG_STATE,
                HfImuCliContract.COMMAND_PAIR, status, message, pairRequestId, pairNonce, fields);
    }

    private void logPairFinal(final String status, final String message, final String address, final String name,
                              final String bondState, final String reason) {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("address", valueOrEmpty(address));
        fields.put("name", valueOrEmpty(name));
        fields.put("bond_state", valueOrEmpty(bondState));
        fields.put("reset_requested", Boolean.toString(pairResetRequested));
        if (reason != null) {
            fields.put("reason", reason);
        }
        cleanupPairReceiver();
        logCommand("error".equals(status) ? HfImuCliContract.LOG_TAG_ERROR : HfImuCliContract.LOG_TAG_STATE,
                HfImuCliContract.COMMAND_PAIR, status, message, pairRequestId, pairNonce, fields);
    }

    private void cleanupPairReceiver() {
        if (pairReceiver == null) {
            return;
        }
        try {
            unregisterReceiver(pairReceiver);
        } catch (final IllegalArgumentException ignored) {
            // Receiver was already gone.
        }
        pairReceiver = null;
    }

    private void startConnect(final Intent intent, final String requestId, final String nonce) {
        cleanupConnectReceiver();
        connectRequestId = requestId;
        connectNonce = nonce;
        connectAddress = valueOrEmpty(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_ADDRESS)).toUpperCase();

        if (!BluetoothAdapter.checkBluetoothAddress(connectAddress)) {
            logConnectFinal("error", "connect_failed", null, "invalid_address");
            return;
        }

        connectDevice = GBApplication.app().getDeviceManager().getDeviceByAddress(connectAddress);
        if (connectDevice == null) {
            connectDevice = DeviceHelper.getInstance().findAvailableDevice(connectAddress, this);
        }
        if (connectDevice == null) {
            logConnectFinal("error", "connect_failed", null, "known_device_missing");
            return;
        }

        connectReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(final Context context, final Intent stateIntent) {
                if (stateIntent == null || !GBDevice.ACTION_DEVICE_CHANGED.equals(stateIntent.getAction())) {
                    return;
                }
                final GBDevice changedDevice = stateIntent.getParcelableExtra(GBDevice.EXTRA_DEVICE);
                if (changedDevice == null || !sameAddress(changedDevice.getAddress(), connectAddress)) {
                    return;
                }
                connectDevice = changedDevice;
                logConnectEvent("ok", "device_state", changedDevice, null);
                if (changedDevice.isInitialized()) {
                    logConnectFinal("ok", "initialized", changedDevice, null);
                }
            }
        };
        final IntentFilter filter = new IntentFilter(GBDevice.ACTION_DEVICE_CHANGED);
        LocalBroadcastManager.getInstance(this).registerReceiver(connectReceiver, filter);

        logConnectEvent("ok", "connect_started", connectDevice, null);
        if (connectDevice.isInitialized()) {
            logConnectFinal("ok", "initialized", connectDevice, null);
            return;
        }

        try {
            GBApplication.deviceService(connectDevice).connect();
            logConnectEvent("ok", "connect_requested", connectDevice, null);
        } catch (final Exception e) {
            logConnectFinal("error", "connect_failed", connectDevice, e.getClass().getSimpleName());
            return;
        }

        final int timeoutMs = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_CONNECT_TIMEOUT_SECONDS), CONNECT_TIMEOUT_MS / 1000), 10, 180) * 1000;
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (connectReceiver == null) {
                    return;
                }
                logConnectFinal("error", "connect_timeout", connectDevice, "timeout");
            }
        }, timeoutMs);
    }

    private void logConnectEvent(final String status, final String message, final GBDevice device, final String reason) {
        final Map<String, String> fields = connectFields(device);
        if (reason != null) {
            fields.put("reason", reason);
        }
        logCommand("error".equals(status) ? HfImuCliContract.LOG_TAG_ERROR : HfImuCliContract.LOG_TAG_STATE,
                HfImuCliContract.COMMAND_CONNECT, status, message, connectRequestId, connectNonce, fields);
    }

    private void logConnectFinal(final String status, final String message, final GBDevice device, final String reason) {
        final Map<String, String> fields = connectFields(device);
        if (reason != null) {
            fields.put("reason", reason);
        }
        cleanupConnectReceiver();
        logCommand("error".equals(status) ? HfImuCliContract.LOG_TAG_ERROR : HfImuCliContract.LOG_TAG_STATE,
                HfImuCliContract.COMMAND_CONNECT, status, message, connectRequestId, connectNonce, fields);
    }

    private Map<String, String> connectFields(final GBDevice device) {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("address", valueOrEmpty(connectAddress));
        if (device != null) {
            fields.put("name", valueOrEmpty(device.getName()));
            fields.put("device_state", device.getState().name());
            fields.put("state_ordinal", Integer.toString(device.getStateOrdinal()));
            fields.put("initialized", Boolean.toString(device.isInitialized()));
        } else {
            fields.put("name", "");
            fields.put("device_state", "UNKNOWN");
            fields.put("state_ordinal", "-1");
            fields.put("initialized", "false");
        }
        return fields;
    }

    private void cleanupConnectReceiver() {
        if (connectReceiver == null) {
            return;
        }
        try {
            LocalBroadcastManager.getInstance(this).unregisterReceiver(connectReceiver);
        } catch (final IllegalArgumentException ignored) {
            // Receiver was already gone.
        }
        connectReceiver = null;
    }

    private void startPortProbe(final Intent intent, final String requestId, final String nonce) {
        final String address = valueOrEmpty(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_ADDRESS)).toUpperCase();
        final String portsSpec = valueOrDefault(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_PORTS), "1-30");
        final String hex = valueOrEmpty(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_HEX));
        final int connectTimeoutMs = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_PORT_CONNECT_TIMEOUT_MS), 3000), 500, 15000);
        final int readMs = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_PORT_READ_MS), 750), 0, 10000);
        final boolean disconnectFirst = parseBoolean(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_DISCONNECT_FIRST));

        if (!BluetoothAdapter.checkBluetoothAddress(address)) {
            logPortProbeFinal("error", "probe_failed", requestId, nonce, address, "invalid_address", new ArrayList<String>(), 0);
            return;
        }

        final BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        if (adapter == null) {
            logPortProbeFinal("error", "probe_failed", requestId, nonce, address, "bluetooth_adapter_missing", new ArrayList<String>(), 0);
            return;
        }
        if (!adapter.isEnabled()) {
            logPortProbeFinal("error", "probe_failed", requestId, nonce, address, "bluetooth_disabled", new ArrayList<String>(), 0);
            return;
        }

        final List<Integer> ports = parsePortSpec(portsSpec);
        if (ports.isEmpty()) {
            logPortProbeFinal("error", "probe_failed", requestId, nonce, address, "no_valid_ports", new ArrayList<String>(), 0);
            return;
        }

        final byte[] payload = parseHexBytes(hex);
        if (hex.length() > 0 && payload == null) {
            logPortProbeFinal("error", "probe_failed", requestId, nonce, address, "invalid_hex", new ArrayList<String>(), 0);
            return;
        }

        final Map<String, String> startFields = new LinkedHashMap<>();
        startFields.put("address", address);
        startFields.put("ports", portsSpec);
        startFields.put("port_count", Integer.toString(ports.size()));
        startFields.put("payload_bytes", Integer.toString(payload == null ? 0 : payload.length));
        startFields.put("connect_timeout_ms", Integer.toString(connectTimeoutMs));
        startFields.put("read_ms", Integer.toString(readMs));
        startFields.put("disconnect_first", Boolean.toString(disconnectFirst));
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_PORT_PROBE, "ok", "probe_started", requestId, nonce, startFields);

        new Thread(new Runnable() {
            @Override
            public void run() {
                if (disconnectFirst) {
                    requestProbeDisconnect(address, requestId, nonce, HfImuCliContract.COMMAND_PORT_PROBE);
                }
                adapter.cancelDiscovery();
                final BluetoothDevice device = adapter.getRemoteDevice(address);
                final List<String> openPorts = new ArrayList<>();
                int tested = 0;
                for (final int port : ports) {
                    tested++;
                    final PortProbeResult result = probeRfcommPort(device, port, payload, connectTimeoutMs, readMs);
                    if (result.connected) {
                        openPorts.add(Integer.toString(port));
                    }
                    final Map<String, String> fields = new LinkedHashMap<>();
                    fields.put("address", address);
                    fields.put("port", Integer.toString(port));
                    fields.put("connected", Boolean.toString(result.connected));
                    fields.put("reason", valueOrEmpty(result.reason));
                    fields.put("connect_ms", Long.toString(result.connectMs));
                    fields.put("bytes_written", Integer.toString(result.bytesWritten));
                    fields.put("bytes_read", Integer.toString(result.bytesRead));
                    fields.put("response_hex", valueOrEmpty(result.responseHex));
                    logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_PORT_PROBE, "ok", "port_result", requestId, nonce, fields);
                }
                logPortProbeFinal("ok", "probe_complete", requestId, nonce, address, "", openPorts, tested);
            }
        }, "HF IMU RFCOMM port probe").start();
    }

    private void startImuCapture(final Intent intent, final String requestId, final String nonce) {
        final String address = valueOrEmpty(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_ADDRESS)).toUpperCase();
        final int port = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_PORT), 5), 1, 30);
        final String hex = valueOrDefault(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_HEX), MI_BAND9_IMU_INIT_HEX);
        final byte[] payload = parseHexBytes(hex);
        final int connectTimeoutMs = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_PORT_CONNECT_TIMEOUT_MS), 3000), 500, 15000);
        final int captureMs = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_CAPTURE_MS), 5000), 0, 60000);
        final int maxPackets = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_MAX_PACKETS), 50), 0, 500);
        final boolean disconnectFirst = parseBoolean(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_DISCONNECT_FIRST));

        if (!BluetoothAdapter.checkBluetoothAddress(address)) {
            logImuCaptureFinal("error", "capture_failed", requestId, nonce, address, port, "invalid_address", new ImuCaptureResult());
            return;
        }
        final BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        if (adapter == null || !adapter.isEnabled()) {
            logImuCaptureFinal("error", "capture_failed", requestId, nonce, address, port, "bluetooth_unavailable", new ImuCaptureResult());
            return;
        }
        if (payload == null || payload.length == 0) {
            logImuCaptureFinal("error", "capture_failed", requestId, nonce, address, port, "invalid_hex", new ImuCaptureResult());
            return;
        }

        final Map<String, String> startFields = new LinkedHashMap<>();
        startFields.put("address", address);
        startFields.put("port", Integer.toString(port));
        startFields.put("payload_bytes", Integer.toString(payload.length));
        startFields.put("connect_timeout_ms", Integer.toString(connectTimeoutMs));
        startFields.put("capture_ms", Integer.toString(captureMs));
        startFields.put("max_packets", Integer.toString(maxPackets));
        startFields.put("disconnect_first", Boolean.toString(disconnectFirst));
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_IMU_CAPTURE, "ok", "capture_started", requestId, nonce, startFields);

        new Thread(new Runnable() {
            @Override
            public void run() {
                if (disconnectFirst) {
                    requestProbeDisconnect(address, requestId, nonce, HfImuCliContract.COMMAND_IMU_CAPTURE);
                }
                adapter.cancelDiscovery();
                final BluetoothDevice device = adapter.getRemoteDevice(address);
                final ImuCaptureResult result = captureRfcomm(device, port, payload, connectTimeoutMs, captureMs, maxPackets, requestId, nonce, address);
                logImuCaptureFinal(result.connected ? "ok" : "error", result.connected ? "capture_complete" : "capture_failed", requestId, nonce, address, port, result.reason, result);
            }
        }, "HF IMU RFCOMM capture").start();
    }

    private ImuCaptureResult captureRfcomm(final BluetoothDevice device, final int port, final byte[] payload,
                                           final int connectTimeoutMs, final int captureMs, final int maxPackets,
                                           final String requestId, final String nonce, final String address) {
        final ImuCaptureResult result = new ImuCaptureResult();
        final BluetoothSocket[] socketRef = new BluetoothSocket[1];
        final Thread worker = new Thread(new Runnable() {
            @Override
            public void run() {
                BluetoothSocket socket = null;
                try {
                    final long started = System.currentTimeMillis();
                    final Method method = device.getClass().getMethod("createRfcommSocket", Integer.TYPE);
                    socket = (BluetoothSocket) method.invoke(device, port);
                    socketRef[0] = socket;
                    socket.connect();
                    result.connectMs = System.currentTimeMillis() - started;
                    result.connected = true;
                    result.reason = "connected";

                    final Map<String, String> connectedFields = new LinkedHashMap<>();
                    connectedFields.put("address", address);
                    connectedFields.put("port", Integer.toString(port));
                    connectedFields.put("connect_ms", Long.toString(result.connectMs));
                    logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_IMU_CAPTURE, "ok", "capture_connected", requestId, nonce, connectedFields);

                    final OutputStream outputStream = socket.getOutputStream();
                    outputStream.write(payload);
                    outputStream.flush();
                    result.bytesWritten = payload.length;
                    final Map<String, String> writeFields = new LinkedHashMap<>();
                    writeFields.put("address", address);
                    writeFields.put("port", Integer.toString(port));
                    writeFields.put("bytes_written", Integer.toString(result.bytesWritten));
                    logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_IMU_CAPTURE, "ok", "payload_written", requestId, nonce, writeFields);

                    final InputStream inputStream = socket.getInputStream();
                    final byte[] buffer = new byte[512];
                    final long captureStarted = System.currentTimeMillis();
                    final long deadline = captureStarted + captureMs;
                    while (System.currentTimeMillis() < deadline && (maxPackets <= 0 || result.packets < maxPackets)) {
                        final int available = inputStream.available();
                        if (available > 0) {
                            final int nRead = inputStream.read(buffer, 0, Math.min(buffer.length, available));
                            if (nRead > 0) {
                                result.packets++;
                                result.bytesRead += nRead;
                                final byte[] packet = new byte[nRead];
                                System.arraycopy(buffer, 0, packet, 0, nRead);
                                final String hex = bytesToHex(packet, 256);
                                if (result.firstHex.length() == 0) {
                                    result.firstHex = hex;
                                }
                                result.lastHex = hex;
                                final Map<String, String> packetFields = new LinkedHashMap<>();
                                packetFields.put("address", address);
                                packetFields.put("port", Integer.toString(port));
                                packetFields.put("packet_index", Integer.toString(result.packets));
                                packetFields.put("elapsed_ms", Long.toString(System.currentTimeMillis() - captureStarted));
                                packetFields.put("bytes_read", Integer.toString(nRead));
                                packetFields.put("hex", hex);
                                logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_IMU_CAPTURE, "ok", "capture_packet", requestId, nonce, packetFields);
                            }
                        } else {
                            try {
                                Thread.sleep(20L);
                            } catch (final InterruptedException e) {
                                Thread.currentThread().interrupt();
                                result.reason = "interrupted";
                                break;
                            }
                        }
                    }
                    result.durationMs = System.currentTimeMillis() - captureStarted;
                } catch (final Throwable t) {
                    result.connected = false;
                    result.reason = t.getClass().getSimpleName();
                } finally {
                    if (socket != null) {
                        try {
                            socket.close();
                        } catch (final Exception ignored) {
                        }
                    }
                }
            }
        }, "RFCOMM port " + port + " capture");
        worker.start();
        try {
            worker.join(connectTimeoutMs + captureMs + 1000L);
        } catch (final InterruptedException e) {
            Thread.currentThread().interrupt();
            result.reason = "interrupted";
        }
        if (worker.isAlive()) {
            result.connected = false;
            result.reason = "timeout";
            if (socketRef[0] != null) {
                try {
                    socketRef[0].close();
                } catch (final Exception ignored) {
                }
            }
        }
        return result;
    }

    private void logImuCaptureFinal(final String status, final String message, final String requestId, final String nonce,
                                    final String address, final int port, final String reason, final ImuCaptureResult result) {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("address", valueOrEmpty(address));
        fields.put("port", Integer.toString(port));
        fields.put("connected", Boolean.toString(result != null && result.connected));
        fields.put("connect_ms", Long.toString(result == null ? -1 : result.connectMs));
        fields.put("bytes_written", Integer.toString(result == null ? 0 : result.bytesWritten));
        fields.put("bytes_read", Integer.toString(result == null ? 0 : result.bytesRead));
        fields.put("packets", Integer.toString(result == null ? 0 : result.packets));
        fields.put("duration_ms", Long.toString(result == null ? 0 : result.durationMs));
        fields.put("first_hex", result == null ? "" : valueOrEmpty(result.firstHex));
        fields.put("last_hex", result == null ? "" : valueOrEmpty(result.lastHex));
        if (reason != null && reason.length() > 0) {
            fields.put("reason", reason);
        }
        logCommand("error".equals(status) ? HfImuCliContract.LOG_TAG_ERROR : HfImuCliContract.LOG_TAG_STATE,
                HfImuCliContract.COMMAND_IMU_CAPTURE, status, message, requestId, nonce, fields);
    }

    private void startGamesirProbe(final Intent intent, final String requestId, final String nonce) {
        cleanupGamesirProbe();
        final BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        if (adapter == null) {
            logGamesirFinal("error", "probe_failed", requestId, nonce, "bluetooth_adapter_missing");
            return;
        }
        if (!adapter.isEnabled()) {
            logGamesirFinal("error", "probe_failed", requestId, nonce, "bluetooth_disabled");
            return;
        }
        gamesirScanner = adapter.getBluetoothLeScanner();
        if (gamesirScanner == null) {
            logGamesirFinal("error", "probe_failed", requestId, nonce, "ble_scanner_missing");
            return;
        }

        gamesirRequestId = requestId;
        gamesirNonce = nonce;
        gamesirStartedMs = System.currentTimeMillis();
        gamesirTargetName = valueOrDefault(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_NAME), "GameSir,Nova,Wireless");
        gamesirTargetAddress = valueOrEmpty(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_ADDRESS)).toUpperCase();
        gamesirHandshake = parseBoolean(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_GAMESIR_HANDSHAKE));
        gamesirBond = parseBoolean(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_GAMESIR_BOND));
        gamesirHistorical010103 = parseBoolean(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_GAMESIR_HISTORICAL_010103));
        gamesirCandidateCount = 0;
        gamesirServiceCount = 0;
        gamesirWriteCount = 0;
        gamesirNotificationCount = 0;
        final int seconds = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_SECONDS), 15), 1, MAX_SCAN_SECONDS);
        final int captureMs = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_CAPTURE_MS), 5000), 500, 30000);

        gamesirScanCallback = new ScanCallback() {
            @Override
            public void onScanResult(final int callbackType, final ScanResult result) {
                handleGamesirScanResult(result);
            }

            @Override
            public void onScanFailed(final int errorCode) {
                final Map<String, String> fields = singleField("reason", "scan_failed_" + errorCode);
                logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_GAMESIR_PROBE, "error", "scan_failed", gamesirRequestId, gamesirNonce, fields);
                logGamesirFinal("error", "probe_failed", gamesirRequestId, gamesirNonce, "scan_failed_" + errorCode);
            }
        };

        final Map<String, String> fields = gamesirBaseFields();
        fields.put("seconds", Integer.toString(seconds));
        fields.put("capture_ms", Integer.toString(captureMs));
        fields.put("handshake", Boolean.toString(gamesirHandshake));
        fields.put("bond", Boolean.toString(gamesirBond));
        fields.put("historical_010103", Boolean.toString(gamesirHistorical010103));
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_GAMESIR_PROBE, "ok", "scan_started", requestId, nonce, fields);
        if (gamesirTargetAddress.length() > 0 && BluetoothAdapter.checkBluetoothAddress(gamesirTargetAddress)) {
            final BluetoothDevice directDevice = adapter.getRemoteDevice(gamesirTargetAddress);
            gamesirCandidateCount++;
            final Map<String, String> directFields = gamesirBaseFields();
            directFields.put("address", valueOrEmpty(directDevice.getAddress()));
            directFields.put("name", valueOrEmpty(directDevice.getName()));
            directFields.put("rssi", "0");
            directFields.put("bond_state", bondStateName(directDevice.getBondState()));
            directFields.put("service_uuids", "");
            directFields.put("source", "direct_address");
            logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_GAMESIR_PROBE, "ok", "scan_candidate", requestId, nonce, directFields);
            connectGamesirGatt(directDevice, directDevice.getName());
        } else {
            gamesirScanner.startScan(gamesirScanCallback);
        }

        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                stopGamesirScanOnly();
                if (gamesirGatt == null) {
                    logGamesirFinal("ok", "probe_complete", gamesirRequestId, gamesirNonce,
                            gamesirCandidateCount == 0 ? "no_candidate" : "no_gatt_connection");
                }
            }
        }, seconds * 1000L);
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                logGamesirFinal("ok", "probe_complete", gamesirRequestId, gamesirNonce, "capture_window_elapsed");
            }
        }, seconds * 1000L + captureMs + 3000L);
    }

    private void handleGamesirScanResult(final ScanResult result) {
        if (result == null || gamesirRequestId == null) {
            return;
        }
        final BluetoothDevice device = result.getDevice();
        if (device == null || device.getAddress() == null) {
            return;
        }
        final ScanRecord record = result.getScanRecord();
        final String recordName = record == null ? "" : valueOrEmpty(record.getDeviceName());
        final String name = recordName.length() > 0 ? recordName : valueOrEmpty(device.getName());
        if (!matchesGamesirTarget(device.getAddress(), name)) {
            return;
        }
        gamesirCandidateCount++;
        final Map<String, String> fields = gamesirBaseFields();
        fields.put("address", valueOrEmpty(device.getAddress()));
        fields.put("name", name);
        fields.put("rssi", Integer.toString(result.getRssi()));
        fields.put("bond_state", bondStateName(device.getBondState()));
        fields.put("service_uuids", record == null ? "" : serviceUuidListToString(record.getServiceUuids()));
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_GAMESIR_PROBE, "ok", "scan_candidate", gamesirRequestId, gamesirNonce, fields);
        if (gamesirGatt == null) {
            connectGamesirGatt(device, name);
        }
    }

    private boolean matchesGamesirTarget(final String address, final String name) {
        if (gamesirTargetAddress != null && gamesirTargetAddress.length() > 0) {
            return sameAddress(gamesirTargetAddress, address);
        }
        final String lowerName = valueOrEmpty(name).toLowerCase();
        for (final String token : valueOrEmpty(gamesirTargetName).split(",")) {
            final String needle = token.trim().toLowerCase();
            if (needle.length() > 0 && lowerName.contains(needle)) {
                return true;
            }
        }
        return false;
    }

    private void connectGamesirGatt(final BluetoothDevice device, final String name) {
        stopGamesirScanOnly();
        final Map<String, String> fields = gamesirBaseFields();
        fields.put("address", valueOrEmpty(device.getAddress()));
        fields.put("name", valueOrEmpty(name));
        fields.put("bond_state", bondStateName(device.getBondState()));
        if (gamesirBond && device.getBondState() != BluetoothDevice.BOND_BONDED) {
            fields.put("create_bond_requested", Boolean.toString(device.createBond()));
        }
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_GAMESIR_PROBE, "ok", "gatt_connect_requested", gamesirRequestId, gamesirNonce, fields);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            gamesirGatt = device.connectGatt(this, false, gamesirGattCallback, BluetoothDevice.TRANSPORT_LE);
        } else {
            gamesirGatt = device.connectGatt(this, false, gamesirGattCallback);
        }
    }

    private final BluetoothGattCallback gamesirGattCallback = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(final BluetoothGatt gatt, final int status, final int newState) {
            final Map<String, String> fields = gamesirBaseFields();
            fields.put("gatt_status", Integer.toString(status));
            fields.put("new_state", bluetoothProfileStateName(newState));
            logCommand(status == BluetoothGatt.GATT_SUCCESS ? HfImuCliContract.LOG_TAG_STATE : HfImuCliContract.LOG_TAG_ERROR,
                    HfImuCliContract.COMMAND_GAMESIR_PROBE,
                    status == BluetoothGatt.GATT_SUCCESS ? "ok" : "error",
                    "gatt_state",
                    gamesirRequestId,
                    gamesirNonce,
                    fields);
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                gatt.discoverServices();
            }
        }

        @Override
        public void onServicesDiscovered(final BluetoothGatt gatt, final int status) {
            final List<BluetoothGattService> services = gatt.getServices();
            gamesirServiceCount = services == null ? 0 : services.size();
            if (services != null) {
                for (final BluetoothGattService service : services) {
                    final Map<String, String> fields = gamesirBaseFields();
                    fields.put("service_uuid", service.getUuid().toString());
                    fields.put("char_uuids", characteristicUuidListToString(service.getCharacteristics()));
                    logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_GAMESIR_PROBE, "ok", "gatt_service", gamesirRequestId, gamesirNonce, fields);
                }
            }
            enableGamesirNotifications(gatt);
            if (gamesirHandshake) {
                handler.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        writeGamesirCharacteristic(gatt, GAMESIR_SERVICE, GAMESIR_HEARTBEAT_CHAR, GAMESIR_PRIME, "865F_PRIME");
                    }
                }, 300L);
                handler.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        writeGamesirCharacteristic(gatt, GAMESIR_UNLOCK_SERVICE, GAMESIR_UNLOCK_CHAR, GAMESIR_UNLOCK_PAYLOAD, "FF12_UNLOCK");
                    }
                }, 700L);
                if (gamesirHistorical010103) {
                    handler.postDelayed(new Runnable() {
                        @Override
                        public void run() {
                            writeGamesirCharacteristic(gatt, GAMESIR_UNLOCK_SERVICE, GAMESIR_UNLOCK_CHAR, GAMESIR_HISTORICAL_010103, "FF12_010103");
                        }
                    }, 1200L);
                }
            }
        }

        @Override
        public void onCharacteristicWrite(final BluetoothGatt gatt, final BluetoothGattCharacteristic characteristic, final int status) {
            final Map<String, String> fields = gamesirBaseFields();
            fields.put("char_uuid", characteristic == null ? "" : characteristic.getUuid().toString());
            fields.put("gatt_status", Integer.toString(status));
            logCommand(status == BluetoothGatt.GATT_SUCCESS ? HfImuCliContract.LOG_TAG_STATE : HfImuCliContract.LOG_TAG_ERROR,
                    HfImuCliContract.COMMAND_GAMESIR_PROBE,
                    status == BluetoothGatt.GATT_SUCCESS ? "ok" : "error",
                    "write_callback",
                    gamesirRequestId,
                    gamesirNonce,
                    fields);
        }

        @Override
        public void onCharacteristicChanged(final BluetoothGatt gatt, final BluetoothGattCharacteristic characteristic) {
            final byte[] value = characteristic == null ? null : characteristic.getValue();
            logGamesirNotification(characteristic == null ? "" : characteristic.getUuid().toString(), value);
        }

        @Override
        public void onDescriptorWrite(final BluetoothGatt gatt, final BluetoothGattDescriptor descriptor, final int status) {
            final Map<String, String> fields = gamesirBaseFields();
            fields.put("descriptor_uuid", descriptor == null ? "" : descriptor.getUuid().toString());
            fields.put("char_uuid", descriptor == null || descriptor.getCharacteristic() == null ? "" : descriptor.getCharacteristic().getUuid().toString());
            fields.put("gatt_status", Integer.toString(status));
            logCommand(status == BluetoothGatt.GATT_SUCCESS ? HfImuCliContract.LOG_TAG_STATE : HfImuCliContract.LOG_TAG_ERROR,
                    HfImuCliContract.COMMAND_GAMESIR_PROBE,
                    status == BluetoothGatt.GATT_SUCCESS ? "ok" : "error",
                    "descriptor_write",
                    gamesirRequestId,
                    gamesirNonce,
                    fields);
        }
    };

    private void enableGamesirNotifications(final BluetoothGatt gatt) {
        requestNotification(gatt, GAMESIR_SERVICE, GAMESIR_HEARTBEAT_CHAR, "865F");
        requestNotification(gatt, GAMESIR_UNLOCK_SERVICE, GAMESIR_NOTIFY_CHAR, "FF11");
        requestNotification(gatt, HID_SERVICE, HID_REPORT_CHAR, "2A4D");
    }

    private void requestNotification(final BluetoothGatt gatt, final UUID serviceUuid, final UUID charUuid, final String label) {
        final BluetoothGattCharacteristic characteristic = findCharacteristic(gatt, serviceUuid, charUuid);
        final Map<String, String> fields = gamesirBaseFields();
        fields.put("label", label);
        fields.put("service_uuid", serviceUuid.toString());
        fields.put("char_uuid", charUuid.toString());
        if (characteristic == null) {
            fields.put("reason", "missing_char");
            logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_GAMESIR_PROBE, "ok", "notification_skipped", gamesirRequestId, gamesirNonce, fields);
            return;
        }
        final boolean enabled = gatt.setCharacteristicNotification(characteristic, true);
        fields.put("set_characteristic_notification", Boolean.toString(enabled));
        final BluetoothGattDescriptor descriptor = characteristic.getDescriptor(CCC_DESCRIPTOR);
        if (descriptor != null) {
            descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
            fields.put("descriptor_write_requested", Boolean.toString(gatt.writeDescriptor(descriptor)));
        } else {
            fields.put("descriptor_write_requested", "false");
            fields.put("reason", "missing_ccc_descriptor");
        }
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_GAMESIR_PROBE, "ok", "notification_requested", gamesirRequestId, gamesirNonce, fields);
    }

    private void writeGamesirCharacteristic(final BluetoothGatt gatt, final UUID serviceUuid, final UUID charUuid,
                                            final byte[] payload, final String label) {
        final BluetoothGattCharacteristic characteristic = findCharacteristic(gatt, serviceUuid, charUuid);
        final Map<String, String> fields = gamesirBaseFields();
        fields.put("label", label);
        fields.put("service_uuid", serviceUuid.toString());
        fields.put("char_uuid", charUuid.toString());
        fields.put("hex", bytesToHex(payload, 64));
        if (characteristic == null) {
            fields.put("gatt_status", "-1");
            fields.put("reason", "missing_char");
            logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_GAMESIR_PROBE, "error", "write_result", gamesirRequestId, gamesirNonce, fields);
            return;
        }
        characteristic.setValue(payload);
        final boolean requested = gatt.writeCharacteristic(characteristic);
        gamesirWriteCount++;
        fields.put("gatt_status", requested ? "0" : "-1");
        fields.put("write_requested", Boolean.toString(requested));
        logCommand(requested ? HfImuCliContract.LOG_TAG_STATE : HfImuCliContract.LOG_TAG_ERROR,
                HfImuCliContract.COMMAND_GAMESIR_PROBE,
                requested ? "ok" : "error",
                "write_result",
                gamesirRequestId,
                gamesirNonce,
                fields);
    }

    private BluetoothGattCharacteristic findCharacteristic(final BluetoothGatt gatt, final UUID serviceUuid, final UUID charUuid) {
        if (gatt == null) {
            return null;
        }
        final BluetoothGattService service = gatt.getService(serviceUuid);
        return service == null ? null : service.getCharacteristic(charUuid);
    }

    private void logGamesirNotification(final String charUuid, final byte[] value) {
        gamesirNotificationCount++;
        final Map<String, String> fields = gamesirBaseFields();
        fields.put("char_uuid", valueOrEmpty(charUuid));
        fields.put("elapsed_ms", Long.toString(System.currentTimeMillis() - gamesirStartedMs));
        fields.put("bytes_read", Integer.toString(value == null ? 0 : value.length));
        fields.put("hex", bytesToHex(value, 256));
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_GAMESIR_PROBE, "ok", "notification", gamesirRequestId, gamesirNonce, fields);
    }

    private void logGamesirFinal(final String status, final String message, final String requestId, final String nonce, final String reason) {
        if (requestId == null && gamesirRequestId == null) {
            return;
        }
        final Map<String, String> fields = gamesirBaseFields();
        fields.put("candidate_count", Integer.toString(gamesirCandidateCount));
        fields.put("service_count", Integer.toString(gamesirServiceCount));
        fields.put("write_count", Integer.toString(gamesirWriteCount));
        fields.put("notification_count", Integer.toString(gamesirNotificationCount));
        fields.put("duration_ms", Long.toString(gamesirStartedMs == 0 ? 0 : System.currentTimeMillis() - gamesirStartedMs));
        if (reason != null && reason.length() > 0) {
            fields.put("reason", reason);
        }
        cleanupGamesirProbe();
        logCommand("error".equals(status) ? HfImuCliContract.LOG_TAG_ERROR : HfImuCliContract.LOG_TAG_STATE,
                HfImuCliContract.COMMAND_GAMESIR_PROBE, status, message, requestId, nonce, fields);
    }

    private Map<String, String> gamesirBaseFields() {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("target_name", valueOrEmpty(gamesirTargetName));
        fields.put("target_address", valueOrEmpty(gamesirTargetAddress));
        return fields;
    }

    private void stopGamesirScanOnly() {
        if (gamesirScanner != null && gamesirScanCallback != null) {
            try {
                gamesirScanner.stopScan(gamesirScanCallback);
            } catch (final Exception ignored) {
            }
        }
        gamesirScanCallback = null;
    }

    private void cleanupGamesirProbe() {
        stopGamesirScanOnly();
        if (gamesirGatt != null) {
            try {
                gamesirGatt.disconnect();
            } catch (final Exception ignored) {
            }
            try {
                gamesirGatt.close();
            } catch (final Exception ignored) {
            }
        }
        gamesirGatt = null;
        gamesirScanner = null;
        gamesirRequestId = null;
        gamesirNonce = null;
    }

    private static String serviceUuidListToString(final List<android.os.ParcelUuid> uuids) {
        if (uuids == null || uuids.isEmpty()) {
            return "";
        }
        final StringBuilder builder = new StringBuilder();
        for (int i = 0; i < uuids.size(); i++) {
            if (i > 0) {
                builder.append(',');
            }
            builder.append(uuids.get(i).getUuid().toString());
        }
        return builder.toString();
    }

    private static String characteristicUuidListToString(final List<BluetoothGattCharacteristic> characteristics) {
        if (characteristics == null || characteristics.isEmpty()) {
            return "";
        }
        final StringBuilder builder = new StringBuilder();
        for (int i = 0; i < characteristics.size(); i++) {
            if (i > 0) {
                builder.append(',');
            }
            builder.append(characteristics.get(i).getUuid().toString());
        }
        return builder.toString();
    }

    private static String bluetoothProfileStateName(final int state) {
        switch (state) {
            case BluetoothProfile.STATE_CONNECTED:
                return "CONNECTED";
            case BluetoothProfile.STATE_CONNECTING:
                return "CONNECTING";
            case BluetoothProfile.STATE_DISCONNECTED:
                return "DISCONNECTED";
            case BluetoothProfile.STATE_DISCONNECTING:
                return "DISCONNECTING";
            default:
                return "UNKNOWN";
        }
    }

    private void requestProbeDisconnect(final String address, final String requestId, final String nonce, final String commandName) {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("address", valueOrEmpty(address));
        GBDevice device = GBApplication.app().getDeviceManager().getDeviceByAddress(address);
        if (device == null) {
            device = DeviceHelper.getInstance().findAvailableDevice(address, this);
        }
        if (device == null) {
            fields.put("reason", "known_device_missing");
            logCommand(HfImuCliContract.LOG_TAG_STATE, valueOrDefault(commandName, HfImuCliContract.COMMAND_PORT_PROBE), "ok", "disconnect_skipped", requestId, nonce, fields);
            return;
        }
        fields.put("device_state", device.getState().name());
        fields.put("initialized", Boolean.toString(device.isInitialized()));
        try {
            GBApplication.deviceService(device).disconnect();
            logCommand(HfImuCliContract.LOG_TAG_STATE, valueOrDefault(commandName, HfImuCliContract.COMMAND_PORT_PROBE), "ok", "disconnect_requested", requestId, nonce, fields);
            try {
                Thread.sleep(1500L);
            } catch (final InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        } catch (final Exception e) {
            fields.put("reason", e.getClass().getSimpleName());
            logCommand(HfImuCliContract.LOG_TAG_STATE, valueOrDefault(commandName, HfImuCliContract.COMMAND_PORT_PROBE), "ok", "disconnect_failed", requestId, nonce, fields);
        }
    }

    private PortProbeResult probeRfcommPort(final BluetoothDevice device, final int port, final byte[] payload,
                                            final int connectTimeoutMs, final int readMs) {
        final PortProbeResult result = new PortProbeResult();
        final BluetoothSocket[] socketRef = new BluetoothSocket[1];
        final Thread worker = new Thread(new Runnable() {
            @Override
            public void run() {
                BluetoothSocket socket = null;
                try {
                    final long started = System.currentTimeMillis();
                    final Method method = device.getClass().getMethod("createRfcommSocket", Integer.TYPE);
                    socket = (BluetoothSocket) method.invoke(device, port);
                    socketRef[0] = socket;
                    socket.connect();
                    result.connectMs = System.currentTimeMillis() - started;
                    result.connected = true;
                    result.reason = "connected";
                    if (payload != null && payload.length > 0) {
                        final OutputStream outputStream = socket.getOutputStream();
                        outputStream.write(payload);
                        outputStream.flush();
                        result.bytesWritten = payload.length;
                    }
                    if (readMs > 0) {
                        final InputStream inputStream = socket.getInputStream();
                        final ByteArrayOutputStream rx = new ByteArrayOutputStream();
                        final byte[] buffer = new byte[512];
                        final long deadline = System.currentTimeMillis() + readMs;
                        while (System.currentTimeMillis() < deadline) {
                            final int available = inputStream.available();
                            if (available > 0) {
                                final int nRead = inputStream.read(buffer, 0, Math.min(buffer.length, available));
                                if (nRead > 0) {
                                    rx.write(buffer, 0, nRead);
                                }
                            } else {
                                try {
                                    Thread.sleep(50L);
                                } catch (final InterruptedException e) {
                                    Thread.currentThread().interrupt();
                                    break;
                                }
                            }
                        }
                        final byte[] response = rx.toByteArray();
                        result.bytesRead = response.length;
                        result.responseHex = bytesToHex(response, 96);
                    }
                } catch (final Throwable t) {
                    result.connected = false;
                    result.reason = t.getClass().getSimpleName();
                } finally {
                    if (socket != null) {
                        try {
                            socket.close();
                        } catch (final Exception ignored) {
                        }
                    }
                }
            }
        }, "RFCOMM port " + port + " probe");
        worker.start();
        try {
            worker.join(connectTimeoutMs + readMs + 750L);
        } catch (final InterruptedException e) {
            Thread.currentThread().interrupt();
            result.reason = "interrupted";
        }
        if (worker.isAlive()) {
            result.connected = false;
            result.reason = "timeout";
            if (socketRef[0] != null) {
                try {
                    socketRef[0].close();
                } catch (final Exception ignored) {
                }
            }
        }
        return result;
    }

    private void logPortProbeFinal(final String status, final String message, final String requestId, final String nonce,
                                   final String address, final String reason, final List<String> openPorts, final int tested) {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("address", valueOrEmpty(address));
        fields.put("tested_ports", Integer.toString(tested));
        fields.put("open_ports", joinStrings(openPorts));
        fields.put("open_port_count", Integer.toString(openPorts == null ? 0 : openPorts.size()));
        if (reason != null && reason.length() > 0) {
            fields.put("reason", reason);
        }
        logCommand("error".equals(status) ? HfImuCliContract.LOG_TAG_ERROR : HfImuCliContract.LOG_TAG_STATE,
                HfImuCliContract.COMMAND_PORT_PROBE, status, message, requestId, nonce, fields);
    }

    private static List<Integer> parsePortSpec(final String spec) {
        final List<Integer> ports = new ArrayList<>();
        final String text = valueOrEmpty(spec).replace(" ", "");
        if (text.length() == 0) {
            return ports;
        }
        final String[] parts = text.split(",");
        for (final String part : parts) {
            if (part.length() == 0) {
                continue;
            }
            final int dash = part.indexOf('-');
            if (dash > 0) {
                final int start = parseInt(part.substring(0, dash), -1);
                final int end = parseInt(part.substring(dash + 1), -1);
                if (start > 0 && end > 0) {
                    final int step = start <= end ? 1 : -1;
                    for (int port = start; port != end + step; port += step) {
                        addRfcommPort(ports, port);
                    }
                }
            } else {
                addRfcommPort(ports, parseInt(part, -1));
            }
        }
        return ports;
    }

    private static void addRfcommPort(final List<Integer> ports, final int port) {
        if (port < 1 || port > 30 || ports.contains(port)) {
            return;
        }
        ports.add(port);
    }

    private static byte[] parseHexBytes(final String hex) {
        final String cleanHex = valueOrEmpty(hex).replaceAll("\\s+", "");
        if (cleanHex.length() == 0) {
            return null;
        }
        if (cleanHex.length() % 2 != 0 || !cleanHex.matches("[0-9a-fA-F]+")) {
            return null;
        }
        final byte[] bytes = new byte[cleanHex.length() / 2];
        for (int i = 0; i < bytes.length; i++) {
            bytes[i] = (byte) Integer.parseInt(cleanHex.substring(i * 2, i * 2 + 2), 16);
        }
        return bytes;
    }

    private static String bytesToHex(final byte[] bytes, final int maxBytes) {
        if (bytes == null || bytes.length == 0) {
            return "";
        }
        final int count = Math.min(bytes.length, Math.max(0, maxBytes));
        final StringBuilder builder = new StringBuilder(count * 2);
        for (int i = 0; i < count; i++) {
            builder.append(String.format("%02X", bytes[i] & 0xff));
        }
        if (bytes.length > count) {
            builder.append("...");
        }
        return builder.toString();
    }

    private static String joinStrings(final List<String> values) {
        if (values == null || values.isEmpty()) {
            return "";
        }
        final StringBuilder builder = new StringBuilder();
        for (int i = 0; i < values.size(); i++) {
            if (i > 0) {
                builder.append(',');
            }
            builder.append(values.get(i));
        }
        return builder.toString();
    }

    private void startSportXmsProbe(final Intent intent, final String requestId, final String nonce) {
        cleanupSportXmsProbe(false);
        sportXmsRequestId = requestId;
        sportXmsNonce = nonce;
        sportXmsStartedMs = System.currentTimeMillis();
        sportXmsCaptureMs = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_CAPTURE_MS), 5000), 500, 600000);
        sportXmsSportType = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_XMS_SPORT_TYPE), XMS_DEFAULT_SPORT_TYPE), 1, 9999);
        sportXmsDidOverride = valueOrEmpty(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_XMS_DID));
        sportXmsShouldStart = parseBoolean(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_XMS_START));
        sportXmsStarted = false;
        sportXmsSensorPackets = 0;
        sportXmsAccelSamples = 0;
        sportXmsGyroSamples = 0;
        sportXmsDid = "";

        final Intent bindIntent = new Intent(SPORT_XMS_ACTION);
        bindIntent.setPackage(SPORT_XMS_PACKAGE);
        sportXmsConnection = new ServiceConnection() {
            @Override
            public void onServiceConnected(final ComponentName name, final IBinder service) {
                sportXmsBinder = service;
                final Map<String, String> fields = new LinkedHashMap<>();
                fields.put("service_package", SPORT_XMS_PACKAGE);
                fields.put("service_component", name == null ? "" : name.flattenToShortString());
                fields.put("interface", SPORT_XMS_INTERFACE);
                logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_SPORT_XMS_PROBE,
                        "ok", "binder_connected", sportXmsRequestId, sportXmsNonce, fields);
                performSportXmsProbe();
            }

            @Override
            public void onServiceDisconnected(final ComponentName name) {
                final Map<String, String> fields = new LinkedHashMap<>();
                fields.put("service_component", name == null ? "" : name.flattenToShortString());
                logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_SPORT_XMS_PROBE,
                        "ok", "binder_disconnected", sportXmsRequestId, sportXmsNonce, fields);
                sportXmsBinder = null;
            }
        };

        final boolean bindRequested;
        try {
            bindRequested = bindService(bindIntent, sportXmsConnection, Context.BIND_AUTO_CREATE);
        } catch (final Exception e) {
            finishSportXmsProbe("error", "probe_failed", "bind_exception_" + e.getClass().getSimpleName());
            return;
        }
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_SPORT_XMS_PROBE,
                bindRequested ? "ok" : "error", bindRequested ? "bind_requested" : "probe_failed",
                requestId, nonce, singleField("service_package", SPORT_XMS_PACKAGE));
        if (!bindRequested) {
            finishSportXmsProbe("error", "probe_failed", "bind_returned_false");
            return;
        }
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (sportXmsBinder == null && valueOrEmpty(sportXmsNonce).equals(valueOrEmpty(nonce))) {
                    finishSportXmsProbe("error", "probe_failed", "bind_timeout");
                }
            }
        }, 8000);
    }

    private void performSportXmsProbe() {
        if (sportXmsBinder == null) {
            finishSportXmsProbe("error", "probe_failed", "binder_missing");
            return;
        }
        try {
            final boolean deviceConnected = transactSportXmsBoolean(XMS_TRANSACTION_IS_DEVICE_CONNECTED);
            final boolean supportSomatosensory = transactSportXmsBoolean(XMS_TRANSACTION_IS_SUPPORT_SOMATOSENSORY);
            final String battery = transactSportXmsString(XMS_TRANSACTION_GET_DEVICE_BATTERY);
            final SportXmsDeviceInfo deviceInfo = transactSportXmsDeviceInfo();
            sportXmsDid = valueOrEmpty(sportXmsDidOverride).length() > 0 ? valueOrEmpty(sportXmsDidOverride) : valueOrEmpty(deviceInfo.did);

            final Map<String, String> fields = new LinkedHashMap<>();
            fields.put("service_package", SPORT_XMS_PACKAGE);
            fields.put("interface", SPORT_XMS_INTERFACE);
            fields.put("device_connected", Boolean.toString(deviceConnected));
            fields.put("support_somatosensory", Boolean.toString(supportSomatosensory));
            fields.put("device_name", valueOrEmpty(deviceInfo.name));
            fields.put("device_model", valueOrEmpty(deviceInfo.model));
            fields.put("did_present", Boolean.toString(valueOrEmpty(deviceInfo.did).length() > 0));
            fields.put("did_override_present", Boolean.toString(valueOrEmpty(sportXmsDidOverride).length() > 0));
            fields.put("battery", valueOrEmpty(battery));
            logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_SPORT_XMS_PROBE,
                    "ok", "device_info", sportXmsRequestId, sportXmsNonce, fields);

            transactSportXmsCallback(XMS_TRANSACTION_SET_SENSOR_LISTENER, new SportXmsSensorCallback());
            transactSportXmsCallback(XMS_TRANSACTION_SET_STATE_LISTENER, new SportXmsStateCallback());
            if (sportXmsShouldStart) {
                transactSportXmsStartSport(sportXmsDid, sportXmsSportType, 1);
                sportXmsStarted = true;
                final Map<String, String> startFields = new LinkedHashMap<>();
                startFields.put("sport_type", Integer.toString(sportXmsSportType));
                startFields.put("sport_state", "1");
                startFields.put("did_present", Boolean.toString(valueOrEmpty(sportXmsDid).length() > 0));
                startFields.put("did_override_present", Boolean.toString(valueOrEmpty(sportXmsDidOverride).length() > 0));
                logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_SPORT_XMS_PROBE,
                        "ok", "sport_started", sportXmsRequestId, sportXmsNonce, startFields);
                handler.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        finishSportXmsProbe("ok", "probe_complete", "");
                    }
                }, sportXmsCaptureMs);
            } else {
                finishSportXmsProbe("ok", "probe_complete", "");
            }
        } catch (final Exception e) {
            finishSportXmsProbe("error", "probe_failed", e.getClass().getSimpleName());
        }
    }

    private boolean transactSportXmsBoolean(final int code) throws RemoteException {
        final Parcel data = Parcel.obtain();
        final Parcel reply = Parcel.obtain();
        try {
            data.writeInterfaceToken(SPORT_XMS_INTERFACE);
            sportXmsBinder.transact(code, data, reply, 0);
            reply.readException();
            return reply.readInt() != 0;
        } finally {
            reply.recycle();
            data.recycle();
        }
    }

    private String transactSportXmsString(final int code) throws RemoteException {
        final Parcel data = Parcel.obtain();
        final Parcel reply = Parcel.obtain();
        try {
            data.writeInterfaceToken(SPORT_XMS_INTERFACE);
            sportXmsBinder.transact(code, data, reply, 0);
            reply.readException();
            return valueOrEmpty(reply.readString());
        } finally {
            reply.recycle();
            data.recycle();
        }
    }

    private SportXmsDeviceInfo transactSportXmsDeviceInfo() throws RemoteException {
        final Parcel data = Parcel.obtain();
        final Parcel reply = Parcel.obtain();
        try {
            data.writeInterfaceToken(SPORT_XMS_INTERFACE);
            sportXmsBinder.transact(XMS_TRANSACTION_GET_DEVICE_INFO, data, reply, 0);
            reply.readException();
            if (reply.readInt() == 0) {
                return new SportXmsDeviceInfo("", "", "");
            }
            return new SportXmsDeviceInfo(reply.readString(), reply.readString(), reply.readString());
        } finally {
            reply.recycle();
            data.recycle();
        }
    }

    private void transactSportXmsCallback(final int code, final IBinder callback) throws RemoteException {
        final Parcel data = Parcel.obtain();
        final Parcel reply = Parcel.obtain();
        try {
            data.writeInterfaceToken(SPORT_XMS_INTERFACE);
            data.writeStrongBinder(callback);
            sportXmsBinder.transact(code, data, reply, 0);
            reply.readException();
        } finally {
            reply.recycle();
            data.recycle();
        }
    }

    private void transactSportXmsStartSport(final String did, final int sportType, final int sportState) throws RemoteException {
        final Parcel data = Parcel.obtain();
        final Parcel reply = Parcel.obtain();
        final long now = System.currentTimeMillis();
        try {
            data.writeInterfaceToken(SPORT_XMS_INTERFACE);
            data.writeString(valueOrEmpty(did));
            data.writeInt(1);
            data.writeInt((int) (now / 1000L));
            data.writeInt(TimeZone.getDefault().getOffset(now) / 60000 / 15);
            data.writeInt(sportType);
            data.writeInt(sportState);
            data.writeInt(0);
            sportXmsBinder.transact(XMS_TRANSACTION_START_SPORT, data, reply, 0);
            reply.readException();
        } finally {
            reply.recycle();
            data.recycle();
        }
    }

    private void transactSportXmsFinishSportByType(final String did, final int sportType) throws RemoteException {
        final Parcel data = Parcel.obtain();
        final Parcel reply = Parcel.obtain();
        try {
            data.writeInterfaceToken(SPORT_XMS_INTERFACE);
            data.writeString(valueOrEmpty(did));
            data.writeInt(sportType);
            sportXmsBinder.transact(XMS_TRANSACTION_FINISH_SPORT_BY_TYPE, data, reply, 0);
            reply.readException();
        } finally {
            reply.recycle();
            data.recycle();
        }
    }

    private void finishSportXmsProbe(final String status, final String message, final String reason) {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("service_package", SPORT_XMS_PACKAGE);
        fields.put("interface", SPORT_XMS_INTERFACE);
        fields.put("started", Boolean.toString(sportXmsStarted));
        fields.put("capture_ms", Integer.toString(sportXmsCaptureMs));
        fields.put("sport_type", Integer.toString(sportXmsSportType));
        fields.put("sensor_packets", Integer.toString(sportXmsSensorPackets));
        fields.put("accel_samples", Integer.toString(sportXmsAccelSamples));
        fields.put("gyro_samples", Integer.toString(sportXmsGyroSamples));
        fields.put("reason", valueOrEmpty(reason));
        logCommand("error".equals(status) ? HfImuCliContract.LOG_TAG_ERROR : HfImuCliContract.LOG_TAG_STATE,
                HfImuCliContract.COMMAND_SPORT_XMS_PROBE, status, message, sportXmsRequestId, sportXmsNonce, fields);
        cleanupSportXmsProbe(true);
    }

    private void cleanupSportXmsProbe(final boolean finishSport) {
        if (sportXmsBinder != null) {
            try {
                transactSportXmsCallback(XMS_TRANSACTION_SET_SENSOR_LISTENER, null);
            } catch (final Exception ignored) {
            }
            try {
                transactSportXmsCallback(XMS_TRANSACTION_SET_STATE_LISTENER, null);
            } catch (final Exception ignored) {
            }
            if (finishSport && sportXmsStarted) {
                try {
                    transactSportXmsFinishSportByType(sportXmsDid, sportXmsSportType);
                } catch (final Exception ignored) {
                }
            }
        }
        if (sportXmsConnection != null) {
            try {
                unbindService(sportXmsConnection);
            } catch (final Exception ignored) {
            }
        }
        sportXmsConnection = null;
        sportXmsBinder = null;
        sportXmsRequestId = null;
        sportXmsNonce = null;
        sportXmsDid = "";
        sportXmsDidOverride = "";
        sportXmsStarted = false;
    }

    private static class SportXmsDeviceInfo {
        final String name;
        final String model;
        final String did;

        SportXmsDeviceInfo(final String name, final String model, final String did) {
            this.name = valueOrEmpty(name);
            this.model = valueOrEmpty(model);
            this.did = valueOrEmpty(did);
        }
    }

    private static class SensorListSummary {
        int count = 0;
        long firstTimestamp = 0;
        long lastTimestamp = 0;
        float minX = Float.POSITIVE_INFINITY;
        float maxX = Float.NEGATIVE_INFINITY;
        float minY = Float.POSITIVE_INFINITY;
        float maxY = Float.NEGATIVE_INFINITY;
        float minZ = Float.POSITIVE_INFINITY;
        float maxZ = Float.NEGATIVE_INFINITY;
        StringBuilder tValues = new StringBuilder();
        StringBuilder xValues = new StringBuilder();
        StringBuilder yValues = new StringBuilder();
        StringBuilder zValues = new StringBuilder();

        void observe(final long timestamp, final float x, final float y, final float z) {
            if (count == 0) {
                firstTimestamp = timestamp;
            }
            lastTimestamp = timestamp;
            minX = Math.min(minX, x);
            maxX = Math.max(maxX, x);
            minY = Math.min(minY, y);
            maxY = Math.max(maxY, y);
            minZ = Math.min(minZ, z);
            maxZ = Math.max(maxZ, z);
            appendCsv(tValues, Long.toString(timestamp));
            appendCsv(xValues, Float.toString(x));
            appendCsv(yValues, Float.toString(y));
            appendCsv(zValues, Float.toString(z));
            count++;
        }
    }

    private static void appendCsv(final StringBuilder builder, final String value) {
        if (builder.length() > 0) {
            builder.append(',');
        }
        builder.append(value);
    }

    private SensorListSummary readSensorListSummary(final Parcel parcel) {
        final SensorListSummary summary = new SensorListSummary();
        final int size = parcel.readInt();
        if (size <= 0 || size > 512) {
            return summary;
        }
        for (int i = 0; i < size; i++) {
            final int present = parcel.readInt();
            if (present == 0) {
                continue;
            }
            final long timestamp = parcel.readLong();
            final float x = parcel.readFloat();
            final float y = parcel.readFloat();
            final float z = parcel.readFloat();
            summary.observe(timestamp, x, y, z);
        }
        return summary;
    }

    private void appendSensorRangeFields(final Map<String, String> fields, final String prefix, final SensorListSummary summary) {
        if (summary == null || summary.count <= 0) {
            return;
        }
        fields.put(prefix + "_x_min", Float.toString(summary.minX));
        fields.put(prefix + "_x_max", Float.toString(summary.maxX));
        fields.put(prefix + "_y_min", Float.toString(summary.minY));
        fields.put(prefix + "_y_max", Float.toString(summary.maxY));
        fields.put(prefix + "_z_min", Float.toString(summary.minZ));
        fields.put(prefix + "_z_max", Float.toString(summary.maxZ));
        fields.put(prefix + "_t_values", summary.tValues.toString());
        fields.put(prefix + "_x_values", summary.xValues.toString());
        fields.put(prefix + "_y_values", summary.yValues.toString());
        fields.put(prefix + "_z_values", summary.zValues.toString());
    }

    private class SportXmsSensorCallback extends Binder {
        @Override
        protected boolean onTransact(final int code, final Parcel data, final Parcel reply, final int flags) throws RemoteException {
            if (code == INTERFACE_TRANSACTION) {
                if (reply != null) {
                    reply.writeString(SPORT_XMS_SENSOR_LISTENER);
                }
                return true;
            }
            if (code != 1) {
                return super.onTransact(code, data, reply, flags);
            }
            data.enforceInterface(SPORT_XMS_SENSOR_LISTENER);
            SensorListSummary accel = new SensorListSummary();
            SensorListSummary gyro = new SensorListSummary();
            try {
                if (data.readInt() != 0) {
                    accel = readSensorListSummary(data);
                    gyro = readSensorListSummary(data);
                }
                sportXmsSensorPackets++;
                sportXmsAccelSamples += accel.count;
                sportXmsGyroSamples += gyro.count;
                final Map<String, String> fields = new LinkedHashMap<>();
                fields.put("packet_index", Integer.toString(sportXmsSensorPackets));
                fields.put("elapsed_ms", Long.toString(System.currentTimeMillis() - sportXmsStartedMs));
                fields.put("accel_samples", Integer.toString(accel.count));
                fields.put("gyro_samples", Integer.toString(gyro.count));
                fields.put("first_accel_timestamp", Long.toString(accel.firstTimestamp));
                fields.put("last_accel_timestamp", Long.toString(accel.lastTimestamp));
                appendSensorRangeFields(fields, "accel", accel);
                appendSensorRangeFields(fields, "gyro", gyro);
                logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_SPORT_XMS_PROBE,
                        "ok", "sensor_packet", sportXmsRequestId, sportXmsNonce, fields);
                if (reply != null) {
                    reply.writeNoException();
                }
                return true;
            } catch (final Exception e) {
                if (reply != null) {
                    reply.writeException(new RemoteException(e.getClass().getSimpleName()));
                }
                return true;
            }
        }
    }

    private class SportXmsStateCallback extends Binder {
        @Override
        protected boolean onTransact(final int code, final Parcel data, final Parcel reply, final int flags) throws RemoteException {
            if (code == INTERFACE_TRANSACTION) {
                if (reply != null) {
                    reply.writeString(SPORT_XMS_STATE_LISTENER);
                }
                return true;
            }
            data.enforceInterface(SPORT_XMS_STATE_LISTENER);
            final Map<String, String> fields = new LinkedHashMap<>();
            fields.put("state_code", Integer.toString(code));
            if (code == 1) {
                fields.put("event", "started");
                fields.put("code", Integer.toString(data.readInt()));
                fields.put("start_time", Integer.toString(data.readInt()));
                fields.put("time_zone", Integer.toString(data.readInt()));
                fields.put("launch_type", Integer.toString(data.readInt()));
            } else if (code == 2) {
                fields.put("event", "restarted");
                fields.put("code", Integer.toString(data.readInt()));
            } else if (code == 3) {
                fields.put("event", "paused");
                fields.put("code", Integer.toString(data.readInt()));
            } else if (code == 4) {
                fields.put("event", "finished");
                fields.put("code", Integer.toString(data.readInt()));
                fields.put("valid", Boolean.toString(data.readInt() != 0));
            } else {
                return super.onTransact(code, data, reply, flags);
            }
            logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_SPORT_XMS_PROBE,
                    "ok", "sport_state", sportXmsRequestId, sportXmsNonce, fields);
            return true;
        }
    }

    private static class PortProbeResult {
        boolean connected = false;
        String reason = "";
        long connectMs = -1;
        int bytesWritten = 0;
        int bytesRead = 0;
        String responseHex = "";
    }

    private static class ImuCaptureResult {
        boolean connected = false;
        String reason = "";
        long connectMs = -1;
        int bytesWritten = 0;
        int bytesRead = 0;
        int packets = 0;
        long durationMs = 0;
        String firstHex = "";
        String lastHex = "";
    }

    private static boolean sameDevice(final BluetoothDevice left, final BluetoothDevice right) {
        return left != null && right != null && valueOrEmpty(left.getAddress()).equalsIgnoreCase(valueOrEmpty(right.getAddress()));
    }

    private static boolean sameAddress(final String left, final String right) {
        return valueOrEmpty(left).equalsIgnoreCase(valueOrEmpty(right));
    }

    private static boolean invokeBooleanMethod(final BluetoothDevice device, final String methodName) {
        try {
            final Method method = device.getClass().getMethod(methodName);
            final Object value = method.invoke(device);
            return value instanceof Boolean && (Boolean) value;
        } catch (final Exception e) {
            return false;
        }
    }

    private void logState(final String state, final String requestId, final String nonce) {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("state", state);
        logCommand(HfImuCliContract.LOG_TAG_STATE, "service", "ok", "service_" + state, requestId, nonce, fields);
    }

    private void logCommand(final String tag, final String command, final String status, final String message,
                            final String requestId, final String nonce, final Map<String, String> extraFields) {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("status", valueOrEmpty(status));
        fields.put("component", "service");
        fields.put("command", valueOrEmpty(command));
        fields.put("message", valueOrEmpty(message));
        fields.put("request_id", valueOrEmpty(requestId));
        fields.put("nonce", valueOrEmpty(nonce));
        fields.put("package", getPackageName());
        if (extraFields != null) {
            fields.putAll(extraFields);
        }
        Log.i(tag, HfImuCliResultFormatter.format(fields));
    }

    private static Map<String, String> singleField(final String key, final String value) {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put(key, valueOrEmpty(value));
        return fields;
    }

    private static String bondStateName(final int state) {
        switch (state) {
            case BluetoothDevice.BOND_NONE:
                return "NONE";
            case BluetoothDevice.BOND_BONDING:
                return "BONDING";
            case BluetoothDevice.BOND_BONDED:
                return "BONDED";
            default:
                return "UNKNOWN";
        }
    }

    private static int parseInt(final String value, final int fallback) {
        try {
            return Integer.parseInt(valueOrEmpty(value));
        } catch (final NumberFormatException e) {
            return fallback;
        }
    }

    private static boolean parseBoolean(final String value) {
        return "1".equals(value) || "true".equalsIgnoreCase(value) || "yes".equalsIgnoreCase(value);
    }

    private static int clamp(final int value, final int min, final int max) {
        return Math.max(min, Math.min(max, value));
    }

    private static String valueOrDefault(final String value, final String fallback) {
        return value == null || value.length() == 0 ? fallback : value;
    }

    private static String valueOrEmpty(final String value) {
        return value == null ? "" : value;
    }
}
