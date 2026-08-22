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
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSppSupport;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSupport;
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
    private static final UUID DFU_V5_SERVICE = UUID.fromString("00000000-1530-3512-2118-0009af100700");
    private static final UUID DFU_V5_CPT_CHAR = UUID.fromString("00000000-1531-3512-2118-0009af100700");
    private static final UUID DFU_V5_PKT_CHAR = UUID.fromString("00000000-1532-3512-2118-0009af100700");
    private static final byte[] DFU_V5_QUERY_STATUS = new byte[]{(byte) 0xD1};
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
    private static final String DEVICE_SETTINGS_XMS_ACTION = "com.xiaomi.fitness.DEVICE_SETTINGS_XMS_SERVICE";
    private static final String DEVICE_SETTINGS_XMS_INTERFACE = "com.xiaomi.fitness.devicesettings.xms.IDeviceSettingsApi";
    private static final int DEVICE_SETTINGS_TRANSACTION_START_FIND_DEVICE = 1;
    private static final int DEVICE_SETTINGS_TRANSACTION_STOP_FIND_DEVICE = 2;
    private static final int DEVICE_SETTINGS_TRANSACTION_CHECK_DEVICE_CONNECT_STATUS = 7;

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

    private BluetoothLeScanner dfuScanner;
    private ScanCallback dfuScanCallback;
    private BluetoothGatt dfuGatt;
    private long dfuStartedMs;
    private String dfuRequestId;
    private String dfuNonce;
    private String dfuTargetName;
    private String dfuTargetAddress;
    private int dfuCandidateCount;
    private int dfuServiceCount;
    private int dfuWriteCount;
    private int dfuNotificationCount;
    private boolean dfuStatusParsed;

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

    private BroadcastReceiver gbSportXmsSppReceiver;
    private String gbSportXmsRequestId;
    private String gbSportXmsNonce;
    private int gbSportXmsSppPackets;
    private int gbSportXmsProtobufPackets;
    private int gbSportXmsActivityPackets;
    private int gbSportXmsOtherPackets;
    private int gbSportXmsType8Subtype26Packets;
    private int gbSportXmsType8Subtype50Packets;
    private int gbSportXmsType8Subtype53Packets;
    private String gbSportXmsFirstChannel;
    private String gbSportXmsFirstHex;
    private String gbSportXmsLastChannel;
    private String gbSportXmsLastHex;

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
        } else if (HfImuCliContract.COMMAND_FIND_BAND.equals(command)) {
            startFindBand(intent, requestId, nonce);
        } else if (HfImuCliContract.COMMAND_MI_FIND_BAND.equals(command)) {
            startMiFindBand(intent, requestId, nonce);
        } else if (HfImuCliContract.COMMAND_GAMESIR_PROBE.equals(command)) {
            startGamesirProbe(intent, requestId, nonce);
        } else if (HfImuCliContract.COMMAND_DFU_STATUS_PROBE.equals(command)) {
            startDfuStatusProbe(intent, requestId, nonce);
        } else if (HfImuCliContract.COMMAND_SPORT_XMS_PROBE.equals(command)) {
            startSportXmsProbe(intent, requestId, nonce);
        } else if (HfImuCliContract.COMMAND_GB_SPORT_XMS_OPEN.equals(command)) {
            startGadgetbridgeSportXmsOpen(intent, requestId, nonce);
        } else if (HfImuCliContract.COMMAND_GB_SPORT_XMS_STOP.equals(command)) {
            startGadgetbridgeSportXmsStop(intent, requestId, nonce);
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
        cleanupDfuStatusProbe();
        cleanupSportXmsProbe(false);
        cleanupGadgetbridgeSportXmsOpenReceiver();
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
        final String forceConnectionType = normalizeForceConnectionType(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_FORCE_CONNECTION_TYPE));

        if (!BluetoothAdapter.checkBluetoothAddress(connectAddress)) {
            logConnectFinal("error", "connect_failed", null, "invalid_address");
            return;
        }

        XiaomiSupport.setDebugForcedConnectionType(forceConnectionType);

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
                logConnectEvent("ok", "device_state", changedDevice, null, forceConnectionType);
                if (changedDevice.isInitialized()) {
                    logConnectFinal("ok", "initialized", changedDevice, null, forceConnectionType);
                }
            }
        };
        final IntentFilter filter = new IntentFilter(GBDevice.ACTION_DEVICE_CHANGED);
        LocalBroadcastManager.getInstance(this).registerReceiver(connectReceiver, filter);

        logConnectEvent("ok", "connect_started", connectDevice, null, forceConnectionType);
        if (connectDevice.isInitialized()) {
            logConnectFinal("ok", "initialized", connectDevice, null, forceConnectionType);
            return;
        }

        try {
            GBApplication.deviceService(connectDevice).connect();
            logConnectEvent("ok", "connect_requested", connectDevice, null, forceConnectionType);
        } catch (final Exception e) {
            logConnectFinal("error", "connect_failed", connectDevice, e.getClass().getSimpleName(), forceConnectionType);
            return;
        }

        final int timeoutMs = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_CONNECT_TIMEOUT_SECONDS), CONNECT_TIMEOUT_MS / 1000), 10, 180) * 1000;
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (connectReceiver == null) {
                    return;
                }
                logConnectFinal("error", "connect_timeout", connectDevice, "timeout", forceConnectionType);
            }
        }, timeoutMs);
    }

    private String normalizeForceConnectionType(final String raw) {
        final String value = valueOrEmpty(raw).trim().toUpperCase().replace('-', '_');
        if ("BLE".equals(value) || "BT_CLASSIC".equals(value) || "BOTH".equals(value)) {
            return value;
        }
        return "";
    }

    private void logConnectEvent(final String status, final String message, final GBDevice device, final String reason) {
        logConnectEvent(status, message, device, reason, "");
    }

    private void logConnectEvent(final String status, final String message, final GBDevice device, final String reason,
                                 final String forceConnectionType) {
        final Map<String, String> fields = connectFields(device);
        if (reason != null) {
            fields.put("reason", reason);
        }
        if (forceConnectionType.length() > 0) {
            fields.put("force_connection_type", forceConnectionType);
        }
        logCommand("error".equals(status) ? HfImuCliContract.LOG_TAG_ERROR : HfImuCliContract.LOG_TAG_STATE,
                HfImuCliContract.COMMAND_CONNECT, status, message, connectRequestId, connectNonce, fields);
    }

    private void logConnectFinal(final String status, final String message, final GBDevice device, final String reason) {
        logConnectFinal(status, message, device, reason, "");
    }

    private void logConnectFinal(final String status, final String message, final GBDevice device, final String reason,
                                 final String forceConnectionType) {
        final Map<String, String> fields = connectFields(device);
        if (reason != null) {
            fields.put("reason", reason);
        }
        if (forceConnectionType.length() > 0) {
            fields.put("force_connection_type", forceConnectionType);
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

    private void startMiFindBand(final Intent intent, final String requestId, final String nonce) {
        final String did = valueOrEmpty(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_XMS_DID));
        final int durationMs = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_FIND_DURATION_MS), 3000), 250, 10000);
        if (did.length() > 0) {
            startMiFindBandWithDid(did, durationMs, requestId, nonce, "cli");
            return;
        }
        resolveMiHealthDidThenFind(durationMs, requestId, nonce);
    }

    private void resolveMiHealthDidThenFind(final int durationMs, final String requestId, final String nonce) {
        final Map<String, String> baseFields = new LinkedHashMap<>();
        baseFields.put("service_package", SPORT_XMS_PACKAGE);
        baseFields.put("service_action", SPORT_XMS_ACTION);
        baseFields.put("interface", SPORT_XMS_INTERFACE);
        baseFields.put("duration_ms", Integer.toString(durationMs));
        baseFields.put("did_present", "false");
        final Intent bindIntent = new Intent(SPORT_XMS_ACTION);
        bindIntent.setPackage(SPORT_XMS_PACKAGE);
        final ServiceConnection[] holder = new ServiceConnection[1];
        holder[0] = new ServiceConnection() {
            @Override
            public void onServiceConnected(final ComponentName name, final IBinder service) {
                final Map<String, String> fields = new LinkedHashMap<>(baseFields);
                fields.put("service_component", name == null ? "" : name.flattenToShortString());
                logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_MI_FIND_BAND,
                        "ok", "did_binder_connected", requestId, nonce, fields);
                try {
                    final SportXmsDeviceInfo deviceInfo = transactSportXmsDeviceInfo(service);
                    final String resolvedDid = valueOrEmpty(deviceInfo.did);
                    final Map<String, String> resolvedFields = new LinkedHashMap<>(baseFields);
                    resolvedFields.put("resolved_did_present", Boolean.toString(resolvedDid.length() > 0));
                    resolvedFields.put("device_name", valueOrEmpty(deviceInfo.name));
                    resolvedFields.put("device_model", valueOrEmpty(deviceInfo.model));
                    if (resolvedDid.length() == 0) {
                        resolvedFields.put("reason", "did_missing");
                        logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_MI_FIND_BAND,
                                "error", "find_failed", requestId, nonce, resolvedFields);
                        return;
                    }
                    logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_MI_FIND_BAND,
                            "ok", "did_resolved", requestId, nonce, resolvedFields);
                    startMiFindBandWithDid(resolvedDid, durationMs, requestId, nonce, "sport_xms_device_info");
                } catch (final Exception e) {
                    fields.put("reason", "did_resolve_" + e.getClass().getSimpleName());
                    logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_MI_FIND_BAND,
                            "error", "find_failed", requestId, nonce, fields);
                } finally {
                    safeUnbindService(holder[0]);
                }
            }

            @Override
            public void onServiceDisconnected(final ComponentName name) {
                final Map<String, String> fields = new LinkedHashMap<>(baseFields);
                fields.put("service_component", name == null ? "" : name.flattenToShortString());
                logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_MI_FIND_BAND,
                        "ok", "did_binder_disconnected", requestId, nonce, fields);
            }
        };
        final boolean bindRequested;
        try {
            bindRequested = bindService(bindIntent, holder[0], Context.BIND_AUTO_CREATE);
        } catch (final Exception e) {
            baseFields.put("reason", "did_bind_exception_" + e.getClass().getSimpleName());
            logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_MI_FIND_BAND,
                    "error", "find_failed", requestId, nonce, baseFields);
            return;
        }
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_MI_FIND_BAND,
                bindRequested ? "ok" : "error", bindRequested ? "did_bind_requested" : "find_failed",
                requestId, nonce, baseFields);
        if (!bindRequested) {
            baseFields.put("reason", "did_bind_returned_false");
            logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_MI_FIND_BAND,
                    "error", "find_failed", requestId, nonce, baseFields);
        }
    }

    private void startMiFindBandWithDid(final String did, final int durationMs, final String requestId,
                                        final String nonce, final String didSource) {
        final Map<String, String> baseFields = new LinkedHashMap<>();
        baseFields.put("service_package", SPORT_XMS_PACKAGE);
        baseFields.put("service_action", DEVICE_SETTINGS_XMS_ACTION);
        baseFields.put("interface", DEVICE_SETTINGS_XMS_INTERFACE);
        baseFields.put("duration_ms", Integer.toString(durationMs));
        baseFields.put("did_present", Boolean.toString(valueOrEmpty(did).length() > 0));
        baseFields.put("did_source", valueOrEmpty(didSource));
        if (valueOrEmpty(did).length() == 0) {
            baseFields.put("reason", "did_missing");
            logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_MI_FIND_BAND,
                    "error", "find_failed", requestId, nonce, baseFields);
            return;
        }

        final Intent bindIntent = new Intent(DEVICE_SETTINGS_XMS_ACTION);
        bindIntent.setPackage(SPORT_XMS_PACKAGE);
        final ServiceConnection[] holder = new ServiceConnection[1];
        holder[0] = new ServiceConnection() {
            @Override
            public void onServiceConnected(final ComponentName name, final IBinder service) {
                final Map<String, String> connectedFields = new LinkedHashMap<>(baseFields);
                connectedFields.put("service_component", name == null ? "" : name.flattenToShortString());
                logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_MI_FIND_BAND,
                        "ok", "binder_connected", requestId, nonce, connectedFields);
                try {
                    final int deviceConnected = transactDeviceSettingsCheck(service, did);
                    final Map<String, String> startFields = new LinkedHashMap<>(baseFields);
                    startFields.put("device_connected", Integer.toString(deviceConnected));
                    if (deviceConnected != 1) {
                        startFields.put("reason", "official_device_not_connected");
                        logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_MI_FIND_BAND,
                                "error", "find_failed", requestId, nonce, startFields);
                        safeUnbindService(holder[0]);
                        return;
                    }
                    transactDeviceSettingsFind(service, DEVICE_SETTINGS_TRANSACTION_START_FIND_DEVICE, did);
                    logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_MI_FIND_BAND,
                            "ok", "find_started", requestId, nonce, startFields);
                    handler.postDelayed(new Runnable() {
                        @Override
                        public void run() {
                            final Map<String, String> stopFields = new LinkedHashMap<>(baseFields);
                            stopFields.put("device_connected", "1");
                            try {
                                transactDeviceSettingsFind(service, DEVICE_SETTINGS_TRANSACTION_STOP_FIND_DEVICE, did);
                                logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_MI_FIND_BAND,
                                        "ok", "find_stopped", requestId, nonce, stopFields);
                                logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_MI_FIND_BAND,
                                        "ok", "find_complete", requestId, nonce, stopFields);
                            } catch (final Exception e) {
                                stopFields.put("reason", "stop_" + e.getClass().getSimpleName());
                                logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_MI_FIND_BAND,
                                        "error", "find_failed", requestId, nonce, stopFields);
                            } finally {
                                safeUnbindService(holder[0]);
                            }
                        }
                    }, durationMs);
                } catch (final Exception e) {
                    final Map<String, String> errorFields = new LinkedHashMap<>(baseFields);
                    errorFields.put("reason", "start_" + e.getClass().getSimpleName());
                    logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_MI_FIND_BAND,
                            "error", "find_failed", requestId, nonce, errorFields);
                    safeUnbindService(holder[0]);
                }
            }

            @Override
            public void onServiceDisconnected(final ComponentName name) {
                final Map<String, String> fields = new LinkedHashMap<>(baseFields);
                fields.put("service_component", name == null ? "" : name.flattenToShortString());
                logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_MI_FIND_BAND,
                        "ok", "binder_disconnected", requestId, nonce, fields);
            }
        };
        final boolean bindRequested;
        try {
            bindRequested = bindService(bindIntent, holder[0], Context.BIND_AUTO_CREATE);
        } catch (final Exception e) {
            baseFields.put("reason", "bind_exception_" + e.getClass().getSimpleName());
            logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_MI_FIND_BAND,
                    "error", "find_failed", requestId, nonce, baseFields);
            return;
        }
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_MI_FIND_BAND,
                bindRequested ? "ok" : "error", bindRequested ? "bind_requested" : "find_failed",
                requestId, nonce, baseFields);
        if (!bindRequested) {
            baseFields.put("reason", "bind_returned_false");
            logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_MI_FIND_BAND,
                    "error", "find_failed", requestId, nonce, baseFields);
        }
    }

    private int transactDeviceSettingsCheck(final IBinder binder, final String did) throws RemoteException {
        final Parcel data = Parcel.obtain();
        final Parcel reply = Parcel.obtain();
        try {
            data.writeInterfaceToken(DEVICE_SETTINGS_XMS_INTERFACE);
            data.writeString(valueOrEmpty(did));
            binder.transact(DEVICE_SETTINGS_TRANSACTION_CHECK_DEVICE_CONNECT_STATUS, data, reply, 0);
            reply.readException();
            return reply.readInt();
        } finally {
            reply.recycle();
            data.recycle();
        }
    }

    private void transactDeviceSettingsFind(final IBinder binder, final int code, final String did) throws RemoteException {
        final Parcel data = Parcel.obtain();
        final Parcel reply = Parcel.obtain();
        try {
            data.writeInterfaceToken(DEVICE_SETTINGS_XMS_INTERFACE);
            data.writeString(valueOrEmpty(did));
            data.writeStrongBinder(null);
            binder.transact(code, data, reply, 0);
            reply.readException();
        } finally {
            reply.recycle();
            data.recycle();
        }
    }

    private void safeUnbindService(final ServiceConnection connection) {
        try {
            if (connection != null) {
                unbindService(connection);
            }
        } catch (final Exception ignored) {
            // The binding may already have been released by the system.
        }
    }

    private void startFindBand(final Intent intent, final String requestId, final String nonce) {
        final String address = valueOrEmpty(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_ADDRESS)).toUpperCase();
        final int durationMs = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_FIND_DURATION_MS), 3000), 250, 10000);
        final GBDevice device = pickFindBandDevice(address);
        if (device == null) {
            final Map<String, String> fields = new LinkedHashMap<>();
            fields.put("address", address);
            fields.put("duration_ms", Integer.toString(durationMs));
            fields.put("reason", address.length() > 0 ? "device_missing" : "initialized_device_missing");
            logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_FIND_BAND,
                    "error", "find_failed", requestId, nonce, fields);
            return;
        }
        final Map<String, String> fields = findBandFields(device, durationMs, address);
        if (!device.isInitialized()) {
            fields.put("reason", "device_not_initialized");
            logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_FIND_BAND,
                    "error", "find_failed", requestId, nonce, fields);
            return;
        }
        try {
            GBApplication.deviceService(device).onFindDevice(true);
            logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_FIND_BAND,
                    "ok", "find_started", requestId, nonce, fields);
        } catch (final Exception e) {
            fields.put("reason", "start_" + e.getClass().getSimpleName());
            logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_FIND_BAND,
                    "error", "find_failed", requestId, nonce, fields);
            return;
        }

        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                final Map<String, String> stopFields = findBandFields(device, durationMs, address);
                try {
                    GBApplication.deviceService(device).onFindDevice(false);
                    logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_FIND_BAND,
                            "ok", "find_stopped", requestId, nonce, stopFields);
                    logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_FIND_BAND,
                            "ok", "find_complete", requestId, nonce, stopFields);
                } catch (final Exception e) {
                    stopFields.put("reason", "stop_" + e.getClass().getSimpleName());
                    logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_FIND_BAND,
                            "error", "find_failed", requestId, nonce, stopFields);
                }
            }
        }, durationMs);
    }

    private GBDevice pickFindBandDevice(final String requestedAddress) {
        if (requestedAddress != null && requestedAddress.length() > 0) {
            GBDevice device = GBApplication.app().getDeviceManager().getDeviceByAddress(requestedAddress);
            if (device == null) {
                device = DeviceHelper.getInstance().findAvailableDevice(requestedAddress, this);
            }
            return device;
        }
        final List<GBDevice> devices = GBApplication.app().getDeviceManager().getDevices();
        if (devices == null) {
            return null;
        }
        GBDevice fallback = null;
        for (final GBDevice device : devices) {
            if (device == null) {
                continue;
            }
            if (fallback == null) {
                fallback = device;
            }
            if (device.isInitialized()) {
                return device;
            }
        }
        return fallback;
    }

    private Map<String, String> findBandFields(final GBDevice device, final int durationMs, final String requestedAddress) {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("requested_address", valueOrEmpty(requestedAddress));
        fields.put("address", device == null ? "" : valueOrEmpty(device.getAddress()));
        fields.put("name", device == null ? "" : valueOrEmpty(device.getName()));
        fields.put("duration_ms", Integer.toString(durationMs));
        if (device != null) {
            fields.put("device_state", device.getState().name());
            fields.put("state_ordinal", Integer.toString(device.getStateOrdinal()));
            fields.put("initialized", Boolean.toString(device.isInitialized()));
        }
        return fields;
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


    private void startDfuStatusProbe(final Intent intent, final String requestId, final String nonce) {
        cleanupDfuStatusProbe();
        final BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        if (adapter == null) {
            logDfuFinal("error", "probe_failed", requestId, nonce, "bluetooth_adapter_missing");
            return;
        }
        if (!adapter.isEnabled()) {
            logDfuFinal("error", "probe_failed", requestId, nonce, "bluetooth_disabled");
            return;
        }
        dfuScanner = adapter.getBluetoothLeScanner();
        if (dfuScanner == null) {
            logDfuFinal("error", "probe_failed", requestId, nonce, "ble_scanner_missing");
            return;
        }

        dfuRequestId = requestId;
        dfuNonce = nonce;
        dfuStartedMs = System.currentTimeMillis();
        dfuTargetName = valueOrDefault(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_NAME), "Xiaomi Smart Band,Mi Band,Smart Band");
        dfuTargetAddress = valueOrEmpty(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_ADDRESS)).toUpperCase();
        dfuCandidateCount = 0;
        dfuServiceCount = 0;
        dfuWriteCount = 0;
        dfuNotificationCount = 0;
        dfuStatusParsed = false;
        final int seconds = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_SECONDS), 20), 1, MAX_SCAN_SECONDS);
        final int captureMs = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_CAPTURE_MS), 8000), 500, 30000);

        dfuScanCallback = new ScanCallback() {
            @Override
            public void onScanResult(final int callbackType, final ScanResult result) {
                handleDfuScanResult(result);
            }

            @Override
            public void onScanFailed(final int errorCode) {
                logCommand(HfImuCliContract.LOG_TAG_ERROR, HfImuCliContract.COMMAND_DFU_STATUS_PROBE,
                        "error", "scan_failed", dfuRequestId, dfuNonce, singleField("reason", "scan_failed_" + errorCode));
                logDfuFinal("error", "probe_failed", dfuRequestId, dfuNonce, "scan_failed_" + errorCode);
            }
        };

        final Map<String, String> fields = dfuBaseFields();
        fields.put("seconds", Integer.toString(seconds));
        fields.put("capture_ms", Integer.toString(captureMs));
        fields.put("allowed_write", "query_upgrade_status_D1_only");
        fields.put("blocked", "prepareTransfer,startTransfer,firmware_body,validate,upgrade,recovery,factory");
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_DFU_STATUS_PROBE, "ok", "probe_started", requestId, nonce, fields);
        if (dfuTargetAddress.length() > 0 && BluetoothAdapter.checkBluetoothAddress(dfuTargetAddress)) {
            final BluetoothDevice directDevice = adapter.getRemoteDevice(dfuTargetAddress);
            dfuCandidateCount++;
            final Map<String, String> directFields = dfuBaseFields();
            directFields.put("address", valueOrEmpty(directDevice.getAddress()));
            directFields.put("name", valueOrEmpty(directDevice.getName()));
            directFields.put("bond_state", bondStateName(directDevice.getBondState()));
            directFields.put("source", "direct_address");
            logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_DFU_STATUS_PROBE, "ok", "scan_candidate", requestId, nonce, directFields);
            connectDfuGatt(directDevice, directDevice.getName());
        } else {
            dfuScanner.startScan(dfuScanCallback);
        }

        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                stopDfuScanOnly();
                if (dfuGatt == null) {
                    logDfuFinal("ok", "probe_complete", dfuRequestId, dfuNonce,
                            dfuCandidateCount == 0 ? "no_candidate" : "no_gatt_connection");
                }
            }
        }, seconds * 1000L);
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                logDfuFinal("ok", "probe_complete", dfuRequestId, dfuNonce,
                        dfuStatusParsed ? "status_parsed" : "capture_window_elapsed");
            }
        }, seconds * 1000L + captureMs + 3000L);
    }

    private void handleDfuScanResult(final ScanResult result) {
        if (result == null || dfuRequestId == null) {
            return;
        }
        final BluetoothDevice device = result.getDevice();
        if (device == null || device.getAddress() == null) {
            return;
        }
        final ScanRecord record = result.getScanRecord();
        final String recordName = record == null ? "" : valueOrEmpty(record.getDeviceName());
        final String name = recordName.length() > 0 ? recordName : valueOrEmpty(device.getName());
        if (!matchesDfuTarget(device.getAddress(), name)) {
            return;
        }
        dfuCandidateCount++;
        final Map<String, String> fields = dfuBaseFields();
        fields.put("address", valueOrEmpty(device.getAddress()));
        fields.put("name", name);
        fields.put("rssi", Integer.toString(result.getRssi()));
        fields.put("bond_state", bondStateName(device.getBondState()));
        fields.put("service_uuids", record == null ? "" : serviceUuidListToString(record.getServiceUuids()));
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_DFU_STATUS_PROBE, "ok", "scan_candidate", dfuRequestId, dfuNonce, fields);
        if (dfuGatt == null) {
            connectDfuGatt(device, name);
        }
    }

    private boolean matchesDfuTarget(final String address, final String name) {
        if (dfuTargetAddress != null && dfuTargetAddress.length() > 0) {
            return sameAddress(dfuTargetAddress, address);
        }
        final String lowerName = valueOrEmpty(name).toLowerCase();
        for (final String token : valueOrEmpty(dfuTargetName).split(",")) {
            final String needle = token.trim().toLowerCase();
            if (needle.length() > 0 && lowerName.contains(needle)) {
                return true;
            }
        }
        return false;
    }

    private void connectDfuGatt(final BluetoothDevice device, final String name) {
        stopDfuScanOnly();
        final Map<String, String> fields = dfuBaseFields();
        fields.put("address", valueOrEmpty(device.getAddress()));
        fields.put("name", valueOrEmpty(name));
        fields.put("bond_state", bondStateName(device.getBondState()));
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_DFU_STATUS_PROBE, "ok", "gatt_connect_requested", dfuRequestId, dfuNonce, fields);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            dfuGatt = device.connectGatt(this, false, dfuGattCallback, BluetoothDevice.TRANSPORT_LE);
        } else {
            dfuGatt = device.connectGatt(this, false, dfuGattCallback);
        }
    }

    private final BluetoothGattCallback dfuGattCallback = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(final BluetoothGatt gatt, final int status, final int newState) {
            final Map<String, String> fields = dfuBaseFields();
            fields.put("gatt_status", Integer.toString(status));
            fields.put("new_state", bluetoothProfileStateName(newState));
            logCommand(status == BluetoothGatt.GATT_SUCCESS ? HfImuCliContract.LOG_TAG_STATE : HfImuCliContract.LOG_TAG_ERROR,
                    HfImuCliContract.COMMAND_DFU_STATUS_PROBE,
                    status == BluetoothGatt.GATT_SUCCESS ? "ok" : "error",
                    "gatt_state",
                    dfuRequestId,
                    dfuNonce,
                    fields);
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                gatt.discoverServices();
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED && !dfuStatusParsed) {
                logDfuFinal(status == BluetoothGatt.GATT_SUCCESS ? "ok" : "error", "probe_complete", dfuRequestId, dfuNonce,
                        status == BluetoothGatt.GATT_SUCCESS ? "disconnected_before_status" : "gatt_disconnected_status_" + status);
            }
        }

        @Override
        public void onServicesDiscovered(final BluetoothGatt gatt, final int status) {
            final List<BluetoothGattService> services = gatt.getServices();
            dfuServiceCount = services == null ? 0 : services.size();
            if (services != null) {
                for (final BluetoothGattService service : services) {
                    final Map<String, String> fields = dfuBaseFields();
                    fields.put("service_uuid", service.getUuid().toString());
                    fields.put("char_uuids", characteristicUuidListToString(service.getCharacteristics()));
                    logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_DFU_STATUS_PROBE, "ok", "gatt_service", dfuRequestId, dfuNonce, fields);
                }
            }
            if (status != BluetoothGatt.GATT_SUCCESS) {
                logDfuFinal("error", "probe_complete", dfuRequestId, dfuNonce, "service_discovery_status_" + status);
                return;
            }
            final BluetoothGattService service = gatt.getService(DFU_V5_SERVICE);
            if (service == null) {
                logDfuFinal("ok", "probe_complete", dfuRequestId, dfuNonce, "dfu_v5_service_missing");
                return;
            }
            final BluetoothGattCharacteristic cpt = service.getCharacteristic(DFU_V5_CPT_CHAR);
            final BluetoothGattCharacteristic pkt = service.getCharacteristic(DFU_V5_PKT_CHAR);
            final Map<String, String> fields = dfuBaseFields();
            fields.put("cpt_present", Boolean.toString(cpt != null));
            fields.put("pkt_present", Boolean.toString(pkt != null));
            fields.put("cpt_properties", cpt == null ? "" : Integer.toString(cpt.getProperties()));
            fields.put("pkt_properties", pkt == null ? "" : Integer.toString(pkt.getProperties()));
            logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_DFU_STATUS_PROBE, "ok", "dfu_v5_service_found", dfuRequestId, dfuNonce, fields);
            if (cpt == null) {
                logDfuFinal("ok", "probe_complete", dfuRequestId, dfuNonce, "dfu_v5_cpt_missing");
                return;
            }
            final int props = cpt.getProperties();
            final boolean canNotify = (props & BluetoothGattCharacteristic.PROPERTY_NOTIFY) != 0 || (props & BluetoothGattCharacteristic.PROPERTY_INDICATE) != 0;
            final boolean canWrite = (props & BluetoothGattCharacteristic.PROPERTY_WRITE) != 0 || (props & BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE) != 0;
            if (!canNotify) {
                logDfuFinal("ok", "probe_complete", dfuRequestId, dfuNonce, "dfu_v5_cpt_notify_missing");
                return;
            }
            if (!canWrite) {
                logDfuFinal("ok", "probe_complete", dfuRequestId, dfuNonce, "dfu_v5_cpt_write_missing");
                return;
            }
            requestDfuNotification(gatt, cpt);
        }

        @Override
        public void onDescriptorWrite(final BluetoothGatt gatt, final BluetoothGattDescriptor descriptor, final int status) {
            final Map<String, String> fields = dfuBaseFields();
            fields.put("descriptor_uuid", descriptor == null ? "" : descriptor.getUuid().toString());
            fields.put("char_uuid", descriptor == null || descriptor.getCharacteristic() == null ? "" : descriptor.getCharacteristic().getUuid().toString());
            fields.put("gatt_status", Integer.toString(status));
            logCommand(status == BluetoothGatt.GATT_SUCCESS ? HfImuCliContract.LOG_TAG_STATE : HfImuCliContract.LOG_TAG_ERROR,
                    HfImuCliContract.COMMAND_DFU_STATUS_PROBE,
                    status == BluetoothGatt.GATT_SUCCESS ? "ok" : "error",
                    "descriptor_write",
                    dfuRequestId,
                    dfuNonce,
                    fields);
            if (descriptor != null && DFU_V5_CPT_CHAR.equals(descriptor.getCharacteristic().getUuid())) {
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    writeDfuStatusQuery(gatt, descriptor.getCharacteristic());
                } else {
                    logDfuFinal("error", "probe_complete", dfuRequestId, dfuNonce, "cpt_descriptor_write_status_" + status);
                }
            }
        }

        @Override
        public void onCharacteristicWrite(final BluetoothGatt gatt, final BluetoothGattCharacteristic characteristic, final int status) {
            final Map<String, String> fields = dfuBaseFields();
            fields.put("char_uuid", characteristic == null ? "" : characteristic.getUuid().toString());
            fields.put("gatt_status", Integer.toString(status));
            logCommand(status == BluetoothGatt.GATT_SUCCESS ? HfImuCliContract.LOG_TAG_STATE : HfImuCliContract.LOG_TAG_ERROR,
                    HfImuCliContract.COMMAND_DFU_STATUS_PROBE,
                    status == BluetoothGatt.GATT_SUCCESS ? "ok" : "error",
                    "write_callback",
                    dfuRequestId,
                    dfuNonce,
                    fields);
            if (status != BluetoothGatt.GATT_SUCCESS) {
                logDfuFinal("error", "probe_complete", dfuRequestId, dfuNonce, "status_query_write_status_" + status);
            }
        }

        @Override
        public void onCharacteristicChanged(final BluetoothGatt gatt, final BluetoothGattCharacteristic characteristic) {
            final byte[] value = characteristic == null ? null : characteristic.getValue();
            logDfuNotification(characteristic == null ? "" : characteristic.getUuid().toString(), value);
        }
    };

    private void requestDfuNotification(final BluetoothGatt gatt, final BluetoothGattCharacteristic characteristic) {
        final Map<String, String> fields = dfuBaseFields();
        fields.put("service_uuid", DFU_V5_SERVICE.toString());
        fields.put("char_uuid", characteristic.getUuid().toString());
        final boolean enabled = gatt.setCharacteristicNotification(characteristic, true);
        fields.put("set_characteristic_notification", Boolean.toString(enabled));
        final BluetoothGattDescriptor descriptor = characteristic.getDescriptor(CCC_DESCRIPTOR);
        if (descriptor == null) {
            fields.put("descriptor_write_requested", "false");
            fields.put("reason", "missing_ccc_descriptor");
            logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_DFU_STATUS_PROBE, "ok", "notification_requested", dfuRequestId, dfuNonce, fields);
            logDfuFinal("ok", "probe_complete", dfuRequestId, dfuNonce, "dfu_v5_cpt_ccc_missing");
            return;
        }
        final int props = characteristic.getProperties();
        descriptor.setValue((props & BluetoothGattCharacteristic.PROPERTY_INDICATE) != 0
                ? BluetoothGattDescriptor.ENABLE_INDICATION_VALUE
                : BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
        fields.put("descriptor_write_requested", Boolean.toString(gatt.writeDescriptor(descriptor)));
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_DFU_STATUS_PROBE, "ok", "notification_requested", dfuRequestId, dfuNonce, fields);
    }

    private void writeDfuStatusQuery(final BluetoothGatt gatt, final BluetoothGattCharacteristic characteristic) {
        characteristic.setValue(DFU_V5_QUERY_STATUS);
        if ((characteristic.getProperties() & BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE) != 0
                && (characteristic.getProperties() & BluetoothGattCharacteristic.PROPERTY_WRITE) == 0) {
            characteristic.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE);
        } else {
            characteristic.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);
        }
        final boolean requested = gatt.writeCharacteristic(characteristic);
        dfuWriteCount++;
        final Map<String, String> fields = dfuBaseFields();
        fields.put("label", "query_upgrade_status_D1");
        fields.put("service_uuid", DFU_V5_SERVICE.toString());
        fields.put("char_uuid", characteristic.getUuid().toString());
        fields.put("hex", bytesToHex(DFU_V5_QUERY_STATUS, 8));
        fields.put("write_requested", Boolean.toString(requested));
        fields.put("blocked", "prepareTransfer,startTransfer,firmware_body,validate,upgrade,recovery,factory");
        logCommand(requested ? HfImuCliContract.LOG_TAG_STATE : HfImuCliContract.LOG_TAG_ERROR,
                HfImuCliContract.COMMAND_DFU_STATUS_PROBE,
                requested ? "ok" : "error",
                "write_result",
                dfuRequestId,
                dfuNonce,
                fields);
        if (!requested) {
            logDfuFinal("error", "probe_complete", dfuRequestId, dfuNonce, "status_query_write_not_requested");
        }
    }

    private void logDfuNotification(final String charUuid, final byte[] value) {
        dfuNotificationCount++;
        final Map<String, String> fields = dfuBaseFields();
        fields.put("char_uuid", valueOrEmpty(charUuid));
        fields.put("elapsed_ms", Long.toString(System.currentTimeMillis() - dfuStartedMs));
        fields.put("bytes_read", Integer.toString(value == null ? 0 : value.length));
        fields.put("hex", bytesToHex(value, 64));
        if (value != null && value.length >= 3 && (value[0] & 0xff) == 0x10 && (value[1] & 0xff) == 0xD1) {
            final int code = value[2] & 0xff;
            fields.put("response", "query_upgrade_status");
            fields.put("code", Integer.toString(code));
            fields.put("code_name", dfuCodeName(code));
            if (value.length >= 4) {
                final int upgradeStatus = value[3] & 0xff;
                fields.put("upgrade_status", Integer.toString(upgradeStatus));
                fields.put("upgrade_status_name", upgradeStatusName(upgradeStatus));
            }
            if (value.length >= 5) {
                fields.put("firmware_type", Integer.toString(value[4] & 0xff));
            }
            if (value.length >= 9) {
                fields.put("firmware_size", Long.toString(readLeUInt32(value, 5)));
            }
            if (value.length >= 13) {
                fields.put("firmware_upgraded_size", Long.toString(readLeUInt32(value, 9)));
            }
            dfuStatusParsed = true;
            logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_DFU_STATUS_PROBE, "ok", "status_response", dfuRequestId, dfuNonce, fields);
            logDfuFinal("ok", "probe_complete", dfuRequestId, dfuNonce, "status_parsed");
            return;
        }
        logCommand(HfImuCliContract.LOG_TAG_STATE, HfImuCliContract.COMMAND_DFU_STATUS_PROBE, "ok", "notification", dfuRequestId, dfuNonce, fields);
    }

    private void logDfuFinal(final String status, final String message, final String requestId, final String nonce, final String reason) {
        if (requestId == null && dfuRequestId == null) {
            return;
        }
        final Map<String, String> fields = dfuBaseFields();
        fields.put("candidate_count", Integer.toString(dfuCandidateCount));
        fields.put("service_count", Integer.toString(dfuServiceCount));
        fields.put("write_count", Integer.toString(dfuWriteCount));
        fields.put("notification_count", Integer.toString(dfuNotificationCount));
        fields.put("status_parsed", Boolean.toString(dfuStatusParsed));
        fields.put("duration_ms", Long.toString(dfuStartedMs == 0 ? 0 : System.currentTimeMillis() - dfuStartedMs));
        if (reason != null && reason.length() > 0) {
            fields.put("reason", reason);
        }
        cleanupDfuStatusProbe();
        logCommand("error".equals(status) ? HfImuCliContract.LOG_TAG_ERROR : HfImuCliContract.LOG_TAG_STATE,
                HfImuCliContract.COMMAND_DFU_STATUS_PROBE, status, message, requestId, nonce, fields);
    }

    private Map<String, String> dfuBaseFields() {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("target_name", valueOrEmpty(dfuTargetName));
        fields.put("target_address", valueOrEmpty(dfuTargetAddress));
        fields.put("safe_scope", "live_dfu_status_query_only");
        return fields;
    }

    private void stopDfuScanOnly() {
        if (dfuScanner != null && dfuScanCallback != null) {
            try {
                dfuScanner.stopScan(dfuScanCallback);
            } catch (final Exception ignored) {
            }
        }
        dfuScanCallback = null;
    }

    private void cleanupDfuStatusProbe() {
        stopDfuScanOnly();
        if (dfuGatt != null) {
            try {
                dfuGatt.disconnect();
            } catch (final Exception ignored) {
            }
            try {
                dfuGatt.close();
            } catch (final Exception ignored) {
            }
        }
        dfuGatt = null;
        dfuScanner = null;
        dfuRequestId = null;
        dfuNonce = null;
    }

    private static long readLeUInt32(final byte[] value, final int offset) {
        if (value == null || value.length < offset + 4) {
            return 0;
        }
        return ((long) value[offset] & 0xff)
                | (((long) value[offset + 1] & 0xff) << 8)
                | (((long) value[offset + 2] & 0xff) << 16)
                | (((long) value[offset + 3] & 0xff) << 24);
    }

    private static String dfuCodeName(final int code) {
        switch (code) {
            case 0:
                return "RESERVED";
            case 1:
                return "SUCCESS";
            case 2:
                return "INVALID_STATE";
            case 3:
                return "UNKNOWN_COMMAND";
            case 4:
                return "OPERATION_FAILED";
            case 15:
                return "SPACE_INSUFFICIENT";
            case 16:
                return "DIAL_ID_UNDEFINED";
            case 17:
                return "DIAL_BUILT_IN";
            default:
                return "UNKNOWN_" + code;
        }
    }

    private static String upgradeStatusName(final int status) {
        switch (status) {
            case 0:
                return "IDLE";
            case 1:
                return "WAITING_TRANSFER";
            case 2:
                return "IN_TRANSFER";
            case 3:
                return "VALIDATING";
            case 4:
                return "WAITING_UPGRADE";
            case 5:
                return "IN_UPGRADING";
            case 6:
                return "BUSY";
            case 7:
                return "WAITING_NEXT_FIRMWARE";
            case 255:
                return "DFU_RUNNING";
            default:
                return "UNKNOWN_" + status;
        }
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

    private static int[] parseXiaomiCommandTypeSubtype(final String hex) {
        final String cleanHex = valueOrEmpty(hex).replace("...", "").replaceAll("\\s+", "");
        if (cleanHex.length() < 4 || cleanHex.length() % 2 != 0 || !cleanHex.matches("[0-9a-fA-F]+")) {
            return new int[]{-1, -1};
        }
        final byte[] bytes = new byte[cleanHex.length() / 2];
        for (int i = 0; i < bytes.length; i++) {
            bytes[i] = (byte) Integer.parseInt(cleanHex.substring(i * 2, i * 2 + 2), 16);
        }
        int position = 0;
        int type = -1;
        int subtype = -1;
        while (position < bytes.length && (type < 0 || subtype < 0)) {
            final long key = readVarint(bytes, position);
            if (key < 0) {
                break;
            }
            position = (int) (key >>> 32);
            final int fieldNumber = (int) ((key & 0xffffffffL) >>> 3);
            final int wireType = (int) (key & 0x07L);
            if (wireType == 0) {
                final long value = readVarint(bytes, position);
                if (value < 0) {
                    break;
                }
                position = (int) (value >>> 32);
                final int intValue = (int) (value & 0xffffffffL);
                if (fieldNumber == 1) {
                    type = intValue;
                } else if (fieldNumber == 2) {
                    subtype = intValue;
                }
            } else if (wireType == 1) {
                position += 8;
            } else if (wireType == 2) {
                final long length = readVarint(bytes, position);
                if (length < 0) {
                    break;
                }
                position = (int) (length >>> 32) + (int) (length & 0xffffffffL);
            } else if (wireType == 5) {
                position += 4;
            } else {
                break;
            }
        }
        return new int[]{type, subtype};
    }

    private static long readVarint(final byte[] bytes, int position) {
        long value = 0;
        int shift = 0;
        while (position < bytes.length && shift < 64) {
            final int b = bytes[position] & 0xff;
            position++;
            value |= (long) (b & 0x7f) << shift;
            if ((b & 0x80) == 0) {
                return ((long) position << 32) | (value & 0xffffffffL);
            }
            shift += 7;
        }
        return -1;
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

    private void startGadgetbridgeSportXmsSppCapture(final String requestId, final String nonce, final String commandName) {
        cleanupGadgetbridgeSportXmsOpenReceiver();
        gbSportXmsRequestId = requestId;
        gbSportXmsNonce = nonce;
        gbSportXmsSppPackets = 0;
        gbSportXmsProtobufPackets = 0;
        gbSportXmsActivityPackets = 0;
        gbSportXmsOtherPackets = 0;
        gbSportXmsType8Subtype26Packets = 0;
        gbSportXmsType8Subtype50Packets = 0;
        gbSportXmsType8Subtype53Packets = 0;
        gbSportXmsFirstChannel = "";
        gbSportXmsFirstHex = "";
        gbSportXmsLastChannel = "";
        gbSportXmsLastHex = "";
        gbSportXmsSppReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(final Context context, final Intent sppIntent) {
                if (sppIntent == null || !XiaomiSppSupport.ACTION_DEBUG_SPP_PACKET.equals(sppIntent.getAction())) {
                    return;
                }
                final String channel = valueOrEmpty(sppIntent.getStringExtra(XiaomiSppSupport.EXTRA_CHANNEL));
                final int length = sppIntent.getIntExtra(XiaomiSppSupport.EXTRA_PAYLOAD_LENGTH, 0);
                final String hex = valueOrEmpty(sppIntent.getStringExtra(XiaomiSppSupport.EXTRA_PAYLOAD_HEX));
                final int[] commandTypeSubtype = parseXiaomiCommandTypeSubtype(hex);
                final int commandType = commandTypeSubtype[0];
                final int commandSubtype = commandTypeSubtype[1];
                gbSportXmsSppPackets++;
                if ("ProtobufCommand".equals(channel)) {
                    gbSportXmsProtobufPackets++;
                    if (commandType == 8 && commandSubtype == 26) {
                        gbSportXmsType8Subtype26Packets++;
                    } else if (commandType == 8 && commandSubtype == 50) {
                        gbSportXmsType8Subtype50Packets++;
                    } else if (commandType == 8 && commandSubtype == 53) {
                        gbSportXmsType8Subtype53Packets++;
                    }
                } else if ("Activity".equals(channel)) {
                    gbSportXmsActivityPackets++;
                } else {
                    gbSportXmsOtherPackets++;
                }
                if (gbSportXmsFirstHex.length() == 0) {
                    gbSportXmsFirstChannel = channel;
                    gbSportXmsFirstHex = hex;
                }
                gbSportXmsLastChannel = channel;
                gbSportXmsLastHex = hex;

                final Map<String, String> fields = new LinkedHashMap<>();
                fields.put("packet_index", Integer.toString(gbSportXmsSppPackets));
                fields.put("channel", channel);
                fields.put("payload_length", Integer.toString(length));
                fields.put("payload_hex", hex);
                if (commandType >= 0) {
                    fields.put("command_type", Integer.toString(commandType));
                }
                if (commandSubtype >= 0) {
                    fields.put("command_subtype", Integer.toString(commandSubtype));
                }
                fields.put("protobuf_packets", Integer.toString(gbSportXmsProtobufPackets));
                fields.put("activity_packets", Integer.toString(gbSportXmsActivityPackets));
                fields.put("xms_response_8_26_packets", Integer.toString(gbSportXmsType8Subtype26Packets));
                fields.put("xms_status_8_50_packets", Integer.toString(gbSportXmsType8Subtype50Packets));
                fields.put("xms_sensor_8_53_packets", Integer.toString(gbSportXmsType8Subtype53Packets));
                logCommand(HfImuCliContract.LOG_TAG_STATE, commandName,
                        "ok", "spp_packet", gbSportXmsRequestId, gbSportXmsNonce, fields);
            }
        };
        LocalBroadcastManager.getInstance(this).registerReceiver(
                gbSportXmsSppReceiver,
                new IntentFilter(XiaomiSppSupport.ACTION_DEBUG_SPP_PACKET)
        );
    }

    private void cleanupGadgetbridgeSportXmsOpenReceiver() {
        if (gbSportXmsSppReceiver == null) {
            return;
        }
        try {
            LocalBroadcastManager.getInstance(this).unregisterReceiver(gbSportXmsSppReceiver);
        } catch (final IllegalArgumentException ignored) {
            // Receiver was already gone.
        }
        gbSportXmsSppReceiver = null;
    }

    private void appendGadgetbridgeSportXmsSppSummaryFields(final Map<String, String> fields) {
        fields.put("spp_packets", Integer.toString(gbSportXmsSppPackets));
        fields.put("protobuf_packets", Integer.toString(gbSportXmsProtobufPackets));
        fields.put("activity_packets", Integer.toString(gbSportXmsActivityPackets));
        fields.put("other_spp_packets", Integer.toString(gbSportXmsOtherPackets));
        fields.put("xms_response_8_26_packets", Integer.toString(gbSportXmsType8Subtype26Packets));
        fields.put("xms_status_8_50_packets", Integer.toString(gbSportXmsType8Subtype50Packets));
        fields.put("xms_sensor_8_53_packets", Integer.toString(gbSportXmsType8Subtype53Packets));
        fields.put("first_spp_channel", valueOrEmpty(gbSportXmsFirstChannel));
        fields.put("first_spp_hex", valueOrEmpty(gbSportXmsFirstHex));
        fields.put("last_spp_channel", valueOrEmpty(gbSportXmsLastChannel));
        fields.put("last_spp_hex", valueOrEmpty(gbSportXmsLastHex));
    }

    private void startGadgetbridgeSportXmsOpen(final Intent intent, final String requestId, final String nonce) {
        startGadgetbridgeSportXmsCommand(intent, requestId, nonce,
                HfImuCliContract.COMMAND_GB_SPORT_XMS_OPEN, 1, 0,
                "opener_complete", "opener_failed");
    }

    private void startGadgetbridgeSportXmsStop(final Intent intent, final String requestId, final String nonce) {
        startGadgetbridgeSportXmsCommand(intent, requestId, nonce,
                HfImuCliContract.COMMAND_GB_SPORT_XMS_STOP, 4, 3,
                "stop_complete", "stop_failed");
    }

    private void startGadgetbridgeSportXmsCommand(final Intent intent, final String requestId, final String nonce,
                                                  final String commandName, final int defaultAppSportState,
                                                  final int defaultProtoSportState, final String completeMessage,
                                                  final String failedMessage) {
        final String requestedAddress = valueOrEmpty(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_ADDRESS)).toUpperCase();
        final int captureMs = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_CAPTURE_MS), 5000), 500, 60000);
        final int sportType = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_XMS_SPORT_TYPE), XMS_DEFAULT_SPORT_TYPE), 1, 9999);
        final int appSportState = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_XMS_SPORT_STATE), defaultAppSportState), 1, 4);
        final int protoSportState = clamp(mapSportRequestStateToHfaState(appSportState, defaultProtoSportState), 0, 3);
        final long now = System.currentTimeMillis();
        final int defaultTimezone = TimeZone.getDefault().getOffset(now) / 60000 / 15;
        final int timezone = clamp(parseInt(intent == null ? null : intent.getStringExtra(HfImuCliContract.EXTRA_XMS_TIMEZONE), defaultTimezone), -96, 96);
        final int timestampSeconds = (int) (now / 1000L);
        final GBDevice device = pickFindBandDevice(requestedAddress);
        final Map<String, String> fields = gadgetbridgeSportXmsOpenFields(device, requestedAddress, captureMs, sportType, timezone);
        fields.put("sport_state", Integer.toString(appSportState));
        fields.put("proto_sport_state", Integer.toString(protoSportState));

        if (device == null) {
            fields.put("reason", requestedAddress.length() > 0 ? "device_missing" : "initialized_device_missing");
            logCommand(HfImuCliContract.LOG_TAG_ERROR, commandName,
                    "error", failedMessage, requestId, nonce, fields);
            return;
        }
        if (!device.isInitialized()) {
            fields.put("reason", "device_not_initialized");
            logCommand(HfImuCliContract.LOG_TAG_ERROR, commandName,
                    "error", failedMessage, requestId, nonce, fields);
            return;
        }

        final byte[] payload = buildSportXmsHnsCommand(timestampSeconds, timezone, sportType, protoSportState);
        fields.put("timestamp_seconds", Integer.toString(timestampSeconds));
        fields.put("payload_schema", "devicecontact_hns_vga_v_parity");
        fields.put("type101_route", "transport_channel_only");
        fields.put("payload_bytes", Integer.toString(payload.length));
        fields.put("payload_hex", bytesToHex(payload, 64));
        logCommand(HfImuCliContract.LOG_TAG_STATE, commandName,
                "ok", "payload_built", requestId, nonce, fields);
        startGadgetbridgeSportXmsSppCapture(requestId, nonce, commandName);
        try {
            GBApplication.deviceService(device).onDebugSendRawProtobufCommand(payload);
            logCommand(HfImuCliContract.LOG_TAG_STATE, commandName,
                    "ok", "protobuf_send_requested", requestId, nonce, fields);
        } catch (final Exception e) {
            cleanupGadgetbridgeSportXmsOpenReceiver();
            fields.put("reason", "send_" + e.getClass().getSimpleName());
            appendGadgetbridgeSportXmsSppSummaryFields(fields);
            logCommand(HfImuCliContract.LOG_TAG_ERROR, commandName,
                    "error", failedMessage, requestId, nonce, fields);
            return;
        }

        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                final Map<String, String> doneFields = gadgetbridgeSportXmsOpenFields(device, requestedAddress, captureMs, sportType, timezone);
                doneFields.put("sport_state", Integer.toString(appSportState));
                doneFields.put("proto_sport_state", Integer.toString(protoSportState));
                doneFields.put("payload_bytes", Integer.toString(payload.length));
                appendGadgetbridgeSportXmsSppSummaryFields(doneFields);
                cleanupGadgetbridgeSportXmsOpenReceiver();
                logCommand(HfImuCliContract.LOG_TAG_STATE, commandName,
                        "ok", completeMessage, requestId, nonce, doneFields);
            }
        }, captureMs);
    }

    private static int mapSportRequestStateToHfaState(final int sportState, final int fallback) {
        if (sportState == 1) {
            return 0;
        }
        if (sportState == 2) {
            return 1;
        }
        if (sportState == 3) {
            return 2;
        }
        if (sportState == 4) {
            return 3;
        }
        return fallback;
    }

    private Map<String, String> gadgetbridgeSportXmsOpenFields(final GBDevice device, final String requestedAddress,
                                                               final int captureMs, final int sportType, final int timezone) {
        final Map<String, String> fields = new LinkedHashMap<>();
        fields.put("requested_address", valueOrEmpty(requestedAddress));
        fields.put("address", device == null ? "" : valueOrEmpty(device.getAddress()));
        fields.put("name", device == null ? "" : valueOrEmpty(device.getName()));
        fields.put("capture_ms", Integer.toString(captureMs));
        fields.put("sport_type", Integer.toString(sportType));
        fields.put("timezone", Integer.toString(timezone));
        if (device != null) {
            fields.put("device_state", device.getState().name());
            fields.put("state_ordinal", Integer.toString(device.getStateOrdinal()));
            fields.put("initialized", Boolean.toString(device.isInitialized()));
        }
        return fields;
    }

    private static byte[] buildSportXmsHnsCommand(final int timestampSeconds, final int timezone, final int sportType,
                                                  final int protoSportState) {
        final ByteArrayOutputStream oe4 = new ByteArrayOutputStream();
        writeVarintField(oe4, 1, timezone);

        final ByteArrayOutputStream hfa = new ByteArrayOutputStream();
        writeVarintField(hfa, 1, timestampSeconds & 0xffffffffL);
        writeLengthDelimitedField(hfa, 2, oe4.toByteArray());
        writeVarintField(hfa, 3, sportType);
        writeVarintField(hfa, 4, protoSportState);
        writeVarintField(hfa, 6, 3);

        final ByteArrayOutputStream uca = new ByteArrayOutputStream();
        writeLengthDelimitedField(uca, 20, hfa.toByteArray());

        final ByteArrayOutputStream hns = new ByteArrayOutputStream();
        writeVarintField(hns, 1, 8);
        writeVarintField(hns, 2, 26);
        writeLengthDelimitedField(hns, 10, uca.toByteArray());
        return hns.toByteArray();
    }

    private static void writeVarintField(final ByteArrayOutputStream out, final int fieldNumber, final long value) {
        writeVarint(out, ((long) fieldNumber << 3));
        writeVarint(out, value);
    }

    private static void writeLengthDelimitedField(final ByteArrayOutputStream out, final int fieldNumber, final byte[] value) {
        writeVarint(out, ((long) fieldNumber << 3) | 2L);
        writeVarint(out, value.length);
        out.write(value, 0, value.length);
    }

    private static void writeVarint(final ByteArrayOutputStream out, long value) {
        while ((value & ~0x7fL) != 0L) {
            out.write((int) ((value & 0x7fL) | 0x80L));
            value >>>= 7;
        }
        out.write((int) value);
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
        return transactSportXmsDeviceInfo(sportXmsBinder);
    }

    private SportXmsDeviceInfo transactSportXmsDeviceInfo(final IBinder binder) throws RemoteException {
        final Parcel data = Parcel.obtain();
        final Parcel reply = Parcel.obtain();
        try {
            data.writeInterfaceToken(SPORT_XMS_INTERFACE);
            binder.transact(XMS_TRANSACTION_GET_DEVICE_INFO, data, reply, 0);
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
