package nodomain.freeyourgadget.gadgetbridge.service.btbr;

import android.bluetooth.BluetoothDevice;
import android.os.ParcelUuid;
import java.util.UUID;
import nodomain.freeyourgadget.gadgetbridge.Logging;
import nodomain.freeyourgadget.gadgetbridge.impl.GBDevice;
import nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport;
import nodomain.freeyourgadget.gadgetbridge.service.btle.BleNamesResolver;
import org.slf4j.Logger;

/* JADX INFO: loaded from: classes12.dex */
public abstract class AbstractBTBRDeviceSupport extends AbstractDeviceSupport implements SocketCallback {
    protected final Object ConnectionMonitor;
    private final Logger logger;
    private final int mBufferSize;
    private int mPort;
    private BtBRQueue mQueue;
    private UUID mSupportedService;

    public AbstractBTBRDeviceSupport(Logger logger, int bufferSize) {
        this(logger, bufferSize, -1);
    }

    public AbstractBTBRDeviceSupport(Logger logger, int bufferSize, int port) {
        this.ConnectionMonitor = new Object();
        this.mSupportedService = null;
        this.mPort = -1;
        this.logger = logger;
        this.mBufferSize = bufferSize;
        this.mPort = port;
        if (logger == null) {
            throw new IllegalArgumentException("logger must not be null");
        }
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.DeviceSupport
    public boolean connect() throws Throwable {
        AbstractBTBRDeviceSupport abstractBTBRDeviceSupport;
        synchronized (this.ConnectionMonitor) {
            try {
                try {
                    UUID supportedService = getSupportedService();
                    if (supportedService == null) {
                        ParcelUuid[] uuids = getBluetoothDeviceUuids();
                        if (uuids == null || uuids.length == 0) {
                            this.logger.warn("Device provided no UUIDs to connect to: {}", this.gbDevice);
                        } else {
                            for (ParcelUuid uuid : uuids) {
                                this.logger.debug("discovered service: {}: {}", BleNamesResolver.resolveServiceName(uuid.toString()), uuid);
                            }
                        }
                        throw new NullPointerException("No supported service UUID specified");
                    }
                    if (this.mQueue != null) {
                        abstractBTBRDeviceSupport = this;
                    } else {
                        abstractBTBRDeviceSupport = this;
                        abstractBTBRDeviceSupport.mQueue = new BtBRQueue(getBluetoothAdapter(), getDevice(), getContext(), abstractBTBRDeviceSupport, supportedService, getBufferSize(), getConnectDelayMillis(), this.mPort);
                    }
                    return abstractBTBRDeviceSupport.mQueue.connect();
                } catch (Throwable th) {
                    th = th;
                    throw th;
                }
            } catch (Throwable th2) {
                th = th2;
            }
        }
    }

    protected ParcelUuid[] getBluetoothDeviceUuids() {
        BluetoothDevice btDevice = getBluetoothAdapter().getRemoteDevice(this.gbDevice.getAddress());
        return btDevice.getUuids();
    }

    public void disconnect() {
        synchronized (this.ConnectionMonitor) {
            if (this.mQueue != null) {
                this.mQueue.disconnect();
            }
        }
    }

    protected TransactionBuilder initializeDevice(TransactionBuilder builder) {
        return builder;
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.DeviceSupport
    public void dispose() {
        synchronized (this.ConnectionMonitor) {
            if (this.mQueue != null) {
                this.mQueue.dispose();
                this.mQueue = null;
            }
        }
    }

    public TransactionBuilder createTransactionBuilder(String taskName) {
        return new TransactionBuilder(taskName, this);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.AbstractDeviceSupport, nodomain.freeyourgadget.gadgetbridge.service.DeviceSupport
    public boolean isConnected() {
        return this.mQueue != null && this.mQueue.isConnected();
    }

    BtBRQueue getQueue() {
        return this.mQueue;
    }

    protected void addSupportedService(UUID aSupportedService) {
        this.mSupportedService = aSupportedService;
    }

    protected UUID getSupportedService() {
        return this.mSupportedService;
    }

    protected int getBufferSize() {
        return this.mBufferSize;
    }

    protected int getConnectDelayMillis() {
        return 0;
    }

    public void logMessageContent(byte[] value) {
        this.logger.info("RECEIVED DATA WITH LENGTH: {}", value != null ? Integer.valueOf(value.length) : "(null)");
        Logging.logBytes(this.logger, value);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.btbr.SocketCallback
    public void onConnectionEstablished() {
        try {
            initializeDevice(createTransactionBuilder("Initializing device")).queue();
        } catch (Exception ex) {
            GBDevice device = getDevice();
            if (device != null) {
                this.logger.error("Exception raised while initializing device {} (address {}), disconnecting", device.getName(), device.getAddress(), ex);
                device.setState(GBDevice.State.WAITING_FOR_RECONNECT);
                device.sendDeviceUpdateIntent(getContext());
                return;
            }
            this.logger.error("Exception raised while initializing unknown device", (Throwable) ex);
        }
    }
}
