package nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.content.Context;
import android.content.Intent;
import android.location.Location;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.widget.Toast;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import nodomain.freeyourgadget.gadgetbridge.GBApplication;
import nodomain.freeyourgadget.gadgetbridge.activities.debug.ImuDebugActivity;
import nodomain.freeyourgadget.gadgetbridge.deviceevents.GBDeviceEventUpdatePreferences;
import nodomain.freeyourgadget.gadgetbridge.devices.DeviceCoordinator;
import nodomain.freeyourgadget.gadgetbridge.devices.xiaomi.XiaomiCoordinator;
import nodomain.freeyourgadget.gadgetbridge.devices.xiaomi.XiaomiFWHelper;
import nodomain.freeyourgadget.gadgetbridge.impl.GBDevice;
import nodomain.freeyourgadget.gadgetbridge.model.Alarm;
import nodomain.freeyourgadget.gadgetbridge.model.CalendarEventSpec;
import nodomain.freeyourgadget.gadgetbridge.model.CallSpec;
import nodomain.freeyourgadget.gadgetbridge.model.CannedMessagesSpec;
import nodomain.freeyourgadget.gadgetbridge.model.Contact;
import nodomain.freeyourgadget.gadgetbridge.model.MusicSpec;
import nodomain.freeyourgadget.gadgetbridge.model.MusicStateSpec;
import nodomain.freeyourgadget.gadgetbridge.model.NotificationSpec;
import nodomain.freeyourgadget.gadgetbridge.model.Reminder;
import nodomain.freeyourgadget.gadgetbridge.model.WorldClock;
import nodomain.freeyourgadget.gadgetbridge.proto.xiaomi.XiaomiProto;
import nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport;
import nodomain.freeyourgadget.gadgetbridge.service.devices.cmfwatchpro.CmfWatchProSupport;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSupport;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.services.AbstractXiaomiService;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.services.XiaomiCalendarService;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.services.XiaomiDataUploadService;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.services.XiaomiHealthService;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.services.XiaomiMusicService;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.services.XiaomiNotificationService;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.services.XiaomiPhonebookService;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.services.XiaomiScheduleService;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.services.XiaomiSystemService;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.services.XiaomiWatchfaceService;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.services.XiaomiWeatherService;
import nodomain.freeyourgadget.gadgetbridge.util.GB;
import nodomain.freeyourgadget.gadgetbridge.util.Prefs;
import org.apache.commons.lang3.StringUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/* JADX INFO: loaded from: classes3.dex */
public class XiaomiSupport extends AbstractDeviceSupport {
    private static final Logger LOG = LoggerFactory.getLogger((Class<?>) XiaomiSupport.class);
    private static final UUID IMU_SENSOR_SERVICE = UUID.fromString("00001812-0000-1000-8000-00805f9b34fb");
    private static final UUID IMU_CONTROL_CHAR = UUID.fromString("00002a4d-0000-1000-8000-00805f9b34fb");
    private static final UUID IMU_DATA_CHAR = UUID.fromString("00002a4d-0000-1000-8000-00805f9b34fb");
    private static final UUID GAMESIR_SERVICE = UUID.fromString("00008650-0000-1000-8000-00805f9b34fb");
    private static final UUID GAMESIR_HEARTBEAT_CHAR = UUID.fromString("0000865f-0000-1000-8000-00805f9b34fb");
    private static final UUID GAMESIR_UNLOCK_SERVICE = UUID.fromString("0000ff10-0000-1000-8000-00805f9b34fb");
    private static final UUID GAMESIR_UNLOCK_CHAR = UUID.fromString("0000ff12-0000-1000-8000-00805f9b34fb");
    private static final UUID CCC_DESCRIPTOR = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    private static final byte[] GAMESIR_UNPRIME = {0};
    private static final byte[] GAMESIR_PRIME = {7};
    private static final byte[] GAMESIR_UNLOCK_PAYLOAD = {1, 21, 1, 33, 34, 35, 36, 37, 38, 39, 40, 41, 24};
    private static final byte[] CMD_IMU_START_1 = {1, 3, 25};
    private static final byte[] CMD_IMU_START_2 = {1, 3, 0, 0, 0, 25};
    private static final byte[] CMD_IMU_START_3 = {2};
    private static final byte[] CMD_IMU_STOP = {3};
    private static final byte[] CMD_INIT = {CmfWatchProSupport.A5, CmfWatchProSupport.A5, 2, 0, 22, 0, 29, 77, 1, 1, 3, 0, 1, 0, 0, 2, 2, 0, 0, -4, 3, 2, 0, 32, 0, 4, 2, 0, 16, 39};
    private static final String[] EMOJI_SOURCE = {"😍", "😘", "😂", "😊", "😎", "😉", "💋", "👍", "🤣", "💕", "😀", "😄", "😭", "🥺", "🙏", "🥰", "🤔", "🔥", "😩", "😔", "😁", "👌", "😏", "😅", "🤍", "💔", "😌", "😢", "💙", "💜", "🎶", "😳", "💖", "🙌", "💯", "🙈", "😋", "😑", "😴", "😪", "😜", "😛", "😝", "😞", "😕", "💗", "👏", "😐", "👉", "💛", "💞", "💪", "🌹", "💀", "😱", "💘", "🤟", "😡", "📷", "🌸", "😈", "👈", "🎉", "💁", "🙊", "💚", "😫", "😤", "💓", "🌚", "👇", "😇", "👊", "👑", "😓", "😻", "🔴", "😥", "🤩", "😚", "😷", "👋", "💥", "🤭", "🌟", "🥱", "💩", "🚀"};
    private static final String[] EMOJI_TARGET = {"ꀂ", "ꀃ", "ꀄ", "ꀅ", "ꀆ", "ꀇ", "ꀈ", "ꀉ", "ꀊ", "ꀋ", "ꀌ", "ꀍ", "ꀎ", "ꀏ", "ꀑ", "ꀒ", "ꀓ", "ꀔ", "ꀗ", "ꀘ", "ꀙ", "ꀚ", "ꀛ", "ꀜ", "ꀝ", "ꀞ", "ꀟ", "ꀠ", "ꀡ", "ꀢ", "ꀤ", "ꀥ", "ꀦ", "ꀧ", "ꀨ", "ꀩ", "ꀫ", "ꀬ", "ꀭ", "ꀮ", "ꀯ", "ꀰ", "ꀱ", "ꀲ", "ꀳ", "ꀴ", "ꀵ", "ꀶ", "ꀷ", "ꀸ", "ꀹ", "ꀺ", "ꀻ", "ꀼ", "ꀽ", "ꀾ", "ꀿ", "ꁀ", "ꁁ", "ꁂ", "ꁃ", "ꁄ", "ꁅ", "ꁆ", "ꁇ", "ꁈ", "ꁉ", "ꁊ", "ꁍ", "ꁎ", "ꁏ", "ꁒ", "ꁓ", "ꁔ", "ꁕ", "ꁖ", "ꁗ", "ꁘ", "ꁙ", "ꁚ", "ꁜ", "ꁝ", "ꁞ", "ꁠ", "ꁡ", "ꁢ", "ꁣ", "ꁤ"};
    private final XiaomiAuthService authService = new XiaomiAuthService(this);
    private final XiaomiMusicService musicService = new XiaomiMusicService(this);
    private final XiaomiHealthService healthService = new XiaomiHealthService(this);
    private final XiaomiNotificationService notificationService = new XiaomiNotificationService(this);
    private final XiaomiScheduleService scheduleService = new XiaomiScheduleService(this);
    private final XiaomiWeatherService weatherService = new XiaomiWeatherService(this);
    private final XiaomiSystemService systemService = new XiaomiSystemService(this);
    private final XiaomiCalendarService calendarService = new XiaomiCalendarService(this);
    private final XiaomiWatchfaceService watchfaceService = new XiaomiWatchfaceService(this);
    private final XiaomiDataUploadService dataUploadService = new XiaomiDataUploadService(this);
    private final XiaomiPhonebookService phonebookService = new XiaomiPhonebookService(this);
    private String cachedFirmwareVersion = null;
    private XiaomiConnectionSupport connectionSupport = null;
    private final Map<Integer, AbstractXiaomiService> mServiceMap = new LinkedHashMap<Integer, AbstractXiaomiService>() { // from class: nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSupport.1
        {
            put(1, XiaomiSupport.this.authService);
            put(18, XiaomiSupport.this.musicService);
            put(8, XiaomiSupport.this.healthService);
            put(7, XiaomiSupport.this.notificationService);
            put(17, XiaomiSupport.this.scheduleService);
            put(10, XiaomiSupport.this.weatherService);
            put(2, XiaomiSupport.this.systemService);
            put(12, XiaomiSupport.this.calendarService);
            put(4, XiaomiSupport.this.watchfaceService);
            put(22, XiaomiSupport.this.dataUploadService);
            put(XiaomiPhonebookService.COMMAND_TYPE, XiaomiSupport.this.phonebookService);
        }
    };
    private boolean imuStreamingEnabled = false;
    private int imuPacketCount = 0;
    private BluetoothGatt imuGatt = null;
    private final BluetoothGattCallback imuGattCallback = new AnonymousClass4();

    @Override // nodomain.freeyourgadget.gadgetbridge.service.DeviceSupport
    public boolean useAutoConnect() {
        return true;
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.service.DeviceSupport
    public void setAutoReconnect(boolean enabled) {
        super.setAutoReconnect(enabled);
        if (this.connectionSupport != null) {
            this.connectionSupport.setAutoReconnect(enabled);
        }
    }

    private XiaomiConnectionSupport createConnectionSpecificSupport() {
        DeviceCoordinator.ConnectionType connType = getCoordinator().getConnectionType();
        if (connType == DeviceCoordinator.ConnectionType.BOTH) {
            connType = getDevicePrefs().getForcedConnectionTypeFromPrefs();
        }
        switch (connType) {
            case BLE:
            case BOTH:
                return new XiaomiBleSupport(this);
            case BT_CLASSIC:
                return new XiaomiSppSupport(this, getContext());
            default:
                return null;
        }
    }

    public XiaomiConnectionSupport getConnectionSpecificSupport() {
        if (this.connectionSupport == null) {
            this.connectionSupport = createConnectionSpecificSupport();
        }
        return this.connectionSupport;
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.DeviceSupport
    public boolean connect() {
        if (getConnectionSpecificSupport() != null) {
            return getConnectionSpecificSupport().connect();
        }
        LOG.error("getConnectionSpecificSupport returned null, could not connect");
        return false;
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.DeviceSupport
    public void dispose() {
        for (AbstractXiaomiService service : this.mServiceMap.values()) {
            service.dispose();
        }
        if (this.connectionSupport != null) {
            XiaomiConnectionSupport connectionSupport = this.connectionSupport;
            this.connectionSupport = null;
            connectionSupport.dispose();
        }
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.service.DeviceSupport
    public void setContext(GBDevice device, BluetoothAdapter adapter, Context context) {
        if (device.getFirmwareVersion() != null) {
            setCachedFirmwareVersion(device.getFirmwareVersion());
        }
        super.setContext(device, adapter, context);
        for (AbstractXiaomiService service : this.mServiceMap.values()) {
            service.setContext(context);
        }
        if (getConnectionSpecificSupport() != null) {
            getConnectionSpecificSupport().setContext(device, adapter, context);
        }
    }

    public String getCachedFirmwareVersion() {
        return this.cachedFirmwareVersion;
    }

    public void setCachedFirmwareVersion(String version) {
        this.cachedFirmwareVersion = version;
    }

    public void onDisconnect() {
        for (AbstractXiaomiService service : this.mServiceMap.values()) {
            service.onDisconnect();
        }
    }

    public void handleCommandBytes(byte[] plainValue) {
        LOG.debug("Got command: {}", GB.hexdump(plainValue));
        try {
            XiaomiProto.Command cmd = XiaomiProto.Command.parseFrom(plainValue);
            AbstractXiaomiService service = this.mServiceMap.get(Integer.valueOf(cmd.getType()));
            if (service != null) {
                service.handleCommand(cmd);
            } else {
                LOG.warn("Unexpected watch command type {}", Integer.valueOf(cmd.getType()));
            }
        } catch (Exception e) {
            LOG.error("Failed to parse bytes as protobuf command payload", (Throwable) e);
        }
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSendConfiguration(String config) {
        Prefs prefs = getDevicePrefs();
        for (AbstractXiaomiService service : this.mServiceMap.values()) {
            if (service.onSendConfiguration(config, prefs)) {
                return;
            }
        }
        LOG.warn("Unhandled config changed: {}", config);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSetTime() {
        this.systemService.setCurrentTime();
        if (getCoordinator().supportsCalendarEvents(getDevice())) {
            this.calendarService.syncCalendar();
        }
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onTestNewFunction() {
        LOG.info("onTestNewFunction: Sending RFCOMM Golden Key to Channel 5");
        getConnectionSpecificSupport().sendRawBytes(CMD_INIT, null);
        showToast("Sent RFCOMM Init! Check logcat for MI_IMU_RAW");
        try {
            Intent intent = new Intent(getContext(), (Class<?>) ImuDebugActivity.class);
            intent.addFlags(268435456);
            getContext().startActivity(intent);
        } catch (Exception e) {
            LOG.error("Failed to launch IMU Debug Activity", (Throwable) e);
        }
    }

    private void startImuBleConnection() {
        LOG.info("Starting IMU BLE connection - scanning for GameSir-Nova Pro...");
        this.imuPacketCount = 0;
        try {
            BluetoothAdapter btAdapter = BluetoothAdapter.getDefaultAdapter();
            if (btAdapter == null) {
                LOG.error("BluetoothAdapter is null");
                return;
            }
            final BluetoothLeScanner scanner = btAdapter.getBluetoothLeScanner();
            if (scanner == null) {
                LOG.error("LE Scanner is null, cannot scan for GameSir");
                return;
            }
            final ScanCallback scanCallback = new ScanCallback() { // from class: nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSupport.2
                @Override // android.bluetooth.le.ScanCallback
                public void onScanResult(int callbackType, ScanResult result) {
                    BluetoothDevice scanDevice = result.getDevice();
                    String name = scanDevice.getName();
                    String address = scanDevice.getAddress();
                    if (name != null && (name.contains("GameSir") || name.contains("Nova") || name.contains("Wireless Controller"))) {
                        XiaomiSupport.LOG.info("Found GameSir device: {} [{}] - Connecting...", name, address);
                        scanner.stopScan(this);
                        if (XiaomiSupport.this.imuGatt == null) {
                            if (scanDevice.getBondState() != 12) {
                                XiaomiSupport.LOG.info("Requesting bond with GameSir device...");
                                scanDevice.createBond();
                            }
                            XiaomiSupport.this.imuGatt = scanDevice.connectGatt(XiaomiSupport.this.getContext(), false, XiaomiSupport.this.imuGattCallback, 2);
                            return;
                        }
                        return;
                    }
                    if (name != null) {
                        XiaomiSupport.LOG.debug("Ignoring device: {} [{}]", name, address);
                    }
                }

                @Override // android.bluetooth.le.ScanCallback
                public void onScanFailed(int errorCode) {
                    XiaomiSupport.LOG.error("BLE scan failed with error: {}", Integer.valueOf(errorCode));
                }
            };
            LOG.info("Started BLE scan for GameSir-Nova Pro...");
            scanner.startScan(scanCallback);
            new Handler(Looper.getMainLooper()).postDelayed(new Runnable() { // from class: nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSupport.3
                @Override // java.lang.Runnable
                public void run() {
                    try {
                        scanner.stopScan(scanCallback);
                        if (XiaomiSupport.this.imuGatt == null) {
                            XiaomiSupport.LOG.warn("GameSir device not found after 15s scan");
                            XiaomiSupport.this.showToast("GameSir device not found - ensure band is authenticated");
                        }
                    } catch (Exception e) {
                    }
                }
            }, 15000L);
        } catch (Exception e) {
            LOG.error("Failed to start IMU scan/connection", (Throwable) e);
        }
    }

    private void stopImuBleConnection() {
        BluetoothGattCharacteristic controlChar;
        LOG.info("Stopping IMU BLE connection...");
        if (this.imuGatt != null) {
            try {
                BluetoothGattService service = this.imuGatt.getService(IMU_SENSOR_SERVICE);
                if (service != null && (controlChar = service.getCharacteristic(IMU_CONTROL_CHAR)) != null) {
                    controlChar.setValue(CMD_IMU_STOP);
                    this.imuGatt.writeCharacteristic(controlChar);
                }
            } catch (Exception e) {
                LOG.error("Error sending IMU stop command", (Throwable) e);
            }
            this.imuGatt.disconnect();
            this.imuGatt.close();
            this.imuGatt = null;
        }
        LOG.info("IMU streaming stopped, total packets: {}", Integer.valueOf(this.imuPacketCount));
    }

    /* JADX INFO: renamed from: nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSupport$4, reason: invalid class name */
    class AnonymousClass4 extends BluetoothGattCallback {
        AnonymousClass4() {
        }

        @Override // android.bluetooth.BluetoothGattCallback
        public void onConnectionStateChange(BluetoothGatt gatt, int status, int newState) {
            XiaomiSupport.LOG.info("IMU GATT connection state changed: {} -> {}", Integer.valueOf(status), Integer.valueOf(newState));
            if (newState == 2) {
                XiaomiSupport.LOG.info("Connected to IMU GATT, discovering services...");
                gatt.discoverServices();
            } else if (newState == 0) {
                XiaomiSupport.LOG.warn("Disconnected from IMU GATT");
                XiaomiSupport.this.imuGatt = null;
            }
        }

        @Override // android.bluetooth.BluetoothGattCallback
        public void onServicesDiscovered(BluetoothGatt gatt, int status) {
            BluetoothGattCharacteristic hbChar;
            XiaomiSupport.LOG.info("IMU services discovered, status={}", Integer.valueOf(status));
            if (status != 0) {
                return;
            }
            BluetoothGattService gsService = gatt.getService(XiaomiSupport.GAMESIR_SERVICE);
            if (gsService != null && (hbChar = gsService.getCharacteristic(XiaomiSupport.GAMESIR_HEARTBEAT_CHAR)) != null) {
                XiaomiSupport.LOG.info("Handshake Step 1: Priming 865F with 0x07");
                hbChar.setValue(XiaomiSupport.GAMESIR_PRIME);
                gatt.writeCharacteristic(hbChar);
                return;
            }
            setupImuNotifications(gatt);
        }

        private void setupImuNotifications(BluetoothGatt gatt) {
            BluetoothGattCharacteristic reportChar;
            BluetoothGattService hidService = gatt.getService(XiaomiSupport.IMU_SENSOR_SERVICE);
            if (hidService != null && (reportChar = hidService.getCharacteristic(XiaomiSupport.IMU_DATA_CHAR)) != null) {
                XiaomiSupport.LOG.info("Enabling notifications for HID Report: 2A4D");
                gatt.setCharacteristicNotification(reportChar, true);
                BluetoothGattDescriptor desc = reportChar.getDescriptor(XiaomiSupport.CCC_DESCRIPTOR);
                if (desc != null) {
                    desc.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                    gatt.writeDescriptor(desc);
                }
            }
        }

        @Override // android.bluetooth.BluetoothGattCallback
        public void onCharacteristicWrite(final BluetoothGatt gatt, BluetoothGattCharacteristic characteristic, int status) {
            XiaomiSupport.LOG.info("IMU characteristic write complete: {}, status={}", characteristic.getUuid(), Integer.valueOf(status));
            if (status != 0) {
                return;
            }
            if (characteristic.getUuid().equals(XiaomiSupport.GAMESIR_HEARTBEAT_CHAR)) {
                XiaomiSupport.LOG.info("Handshake Step 2: Waiting 100ms then unlocking 0xFF12");
                new Handler(Looper.getMainLooper()).postDelayed(new Runnable() { // from class: nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSupport$4$$ExternalSyntheticLambda0
                    @Override // java.lang.Runnable
                    public final void run() {
                        XiaomiSupport.AnonymousClass4.lambda$onCharacteristicWrite$0(gatt);
                    }
                }, 100L);
            } else if (characteristic.getUuid().equals(XiaomiSupport.GAMESIR_UNLOCK_CHAR)) {
                XiaomiSupport.LOG.info("Handshake Complete! Subscribing to HID reports...");
                setupImuNotifications(gatt);
            }
        }

        static /* synthetic */ void lambda$onCharacteristicWrite$0(BluetoothGatt gatt) {
            BluetoothGattCharacteristic unlockChar;
            BluetoothGattService unlockService = gatt.getService(XiaomiSupport.GAMESIR_UNLOCK_SERVICE);
            if (unlockService != null && (unlockChar = unlockService.getCharacteristic(XiaomiSupport.GAMESIR_UNLOCK_CHAR)) != null) {
                XiaomiSupport.LOG.info("Handshake Step 3: Writing unlock payload to 0xFF12");
                unlockChar.setValue(XiaomiSupport.GAMESIR_UNLOCK_PAYLOAD);
                gatt.writeCharacteristic(unlockChar);
            }
        }

        @Override // android.bluetooth.BluetoothGattCallback
        public void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic) {
            byte[] value = characteristic.getValue();
            if (characteristic.getUuid().equals(XiaomiSupport.GAMESIR_HEARTBEAT_CHAR)) {
                XiaomiSupport.LOG.debug("GameSir Heartbeat: {}", GB.hexdump(value));
            } else if (characteristic.getUuid().equals(XiaomiSupport.IMU_DATA_CHAR)) {
                XiaomiSupport.this.handleImuData(value);
            }
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void handleImuData(byte[] value) {
        if (value == null) {
            return;
        }
        this.imuPacketCount++;
        LOG.info("HID IMU DATA [{}]: {}", Integer.valueOf(value.length), GB.hexdump(value));
        if (value.length >= 6) {
            Log.i("MI_IMU_RAW", GB.hexdump(value));
        }
        if (this.imuPacketCount % 50 == 0) {
            showToast("Captured " + this.imuPacketCount + " HID reports");
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void showToast(final String msg) {
        new Handler(Looper.getMainLooper()).post(new Runnable() { // from class: nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSupport.5
            @Override // java.lang.Runnable
            public void run() {
                Toast.makeText(GBApplication.getContext(), msg, 0).show();
            }
        });
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onFindPhone(boolean start) {
        this.systemService.onFindPhone(start);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onFindDevice(boolean start) {
        this.systemService.onFindWatch(start);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSetPhoneVolume(float volume) {
        this.musicService.onSetPhoneVolume(volume);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSetGpsLocation(Location location) {
        this.healthService.onSetGpsLocation(location);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSetReminders(ArrayList<? extends Reminder> reminders) {
        this.scheduleService.onSetReminders(reminders);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSetWorldClocks(ArrayList<? extends WorldClock> clocks) {
        this.scheduleService.onSetWorldClocks(clocks);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onNotification(NotificationSpec notificationSpec) {
        this.notificationService.onNotification(notificationSpec);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onDeleteNotification(int id) {
        this.notificationService.onDeleteNotification(id);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSetAlarms(ArrayList<? extends Alarm> alarms) {
        this.scheduleService.onSetAlarms(alarms);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSetCallState(CallSpec callSpec) {
        this.notificationService.onSetCallState(callSpec);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSetCannedMessages(CannedMessagesSpec cannedMessagesSpec) {
        this.notificationService.onSetCannedMessages(cannedMessagesSpec);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSetMusicState(MusicStateSpec stateSpec) {
        this.musicService.onSetMusicState(stateSpec);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSetMusicInfo(MusicSpec musicSpec) {
        this.musicService.onSetMusicInfo(musicSpec);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onInstallApp(Uri uri, Bundle options) {
        XiaomiFWHelper fwHelper = new XiaomiFWHelper(uri, getContext());
        if (!fwHelper.isValid()) {
            LOG.warn("Uri {} is not valid", uri);
            return;
        }
        if (fwHelper.isFirmware()) {
            this.systemService.installFirmware(fwHelper);
        } else if (fwHelper.isWatchface()) {
            this.watchfaceService.installWatchface(fwHelper);
        } else {
            LOG.warn("Unknown fwhelper for {}", uri);
        }
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onAppInfoReq() {
        this.watchfaceService.requestWatchfaceList();
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onAppStart(UUID uuid, boolean start) {
        if (start) {
            this.watchfaceService.setWatchface(uuid);
        }
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onAppDelete(UUID uuid) {
        this.watchfaceService.deleteWatchface(uuid);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onFetchRecordedData(int dataTypes) {
        this.healthService.onFetchRecordedData(dataTypes);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onHeartRateTest() {
        this.healthService.onHeartRateTest();
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onEnableRealtimeHeartRateMeasurement(boolean enable) {
        this.healthService.enableRealtimeStats(enable);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onEnableRealtimeSteps(boolean enable) {
        this.healthService.enableRealtimeStats(enable);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onEnableHeartRateSleepSupport(boolean enable) {
        this.healthService.setHeartRateConfig();
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSetHeartRateMeasurementInterval(int seconds) {
        this.healthService.setHeartRateConfig();
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onAddCalendarEvent(CalendarEventSpec calendarEventSpec) {
        this.calendarService.onAddCalendarEvent(calendarEventSpec);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onDeleteCalendarEvent(byte type, long id) {
        this.calendarService.onDeleteCalendarEvent(type, id);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSendWeather() {
        this.weatherService.onSendWeather();
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.devices.EventHandler
    public void onSetContacts(ArrayList<? extends Contact> contacts) {
        this.phonebookService.setContacts(contacts);
    }

    public XiaomiCoordinator getCoordinator() {
        return (XiaomiCoordinator) this.gbDevice.getDeviceCoordinator();
    }

    protected void onAuthSuccess() {
        LOG.info("onAuthSuccess");
        getConnectionSpecificSupport().onAuthSuccess();
        if (GBApplication.getPrefs().syncTime()) {
            this.systemService.setCurrentTime();
        }
        for (AbstractXiaomiService service : this.mServiceMap.values()) {
            service.initialize();
        }
    }

    public void sendCommand(String taskName, XiaomiProto.Command command) {
        getConnectionSpecificSupport().sendCommand(taskName, command);
    }

    public void sendCommand(String taskName, int type, int subtype) {
        sendCommand(taskName, XiaomiProto.Command.newBuilder().setType(type).setSubtype(subtype).build());
    }

    public XiaomiAuthService getAuthService() {
        return this.authService;
    }

    public XiaomiDataUploadService getDataUploadService() {
        return this.dataUploadService;
    }

    public XiaomiHealthService getHealthService() {
        return this.healthService;
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.service.DeviceSupport
    public String customStringFilter(String inputString) {
        return StringUtils.replaceEach(inputString, EMOJI_SOURCE, EMOJI_TARGET);
    }

    public void setFeatureSupported(String featureKey, boolean supported) {
        LOG.debug("Setting feature {} -> {}", featureKey, supported ? "supported" : "not supported");
        evaluateGBDeviceEvent(new GBDeviceEventUpdatePreferences(featureKey, Boolean.valueOf(supported)));
    }
}
