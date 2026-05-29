package nodomain.freeyourgadget.gadgetbridge.service.btbr;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothSocket;
import android.content.Context;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Message;
import java.io.IOException;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Iterator;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import nodomain.freeyourgadget.gadgetbridge.GBApplication;
import nodomain.freeyourgadget.gadgetbridge.impl.GBDevice;
import nodomain.freeyourgadget.gadgetbridge.util.GB;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/* JADX INFO: loaded from: classes12.dex */
public final class BtBRQueue {
    public static final int HANDLER_SUBJECT_CONNECT = 0;
    public static final int HANDLER_SUBJECT_PERFORM_TRANSACTION = 1;
    private static final AtomicLong QUEUE_COUNTER = new AtomicLong(0);
    private static final AtomicLong THREAD_COUNTER = new AtomicLong(0);
    private final BluetoothAdapter mBtAdapter;
    private final int mBufferSize;
    private final SocketCallback mCallback;
    private final int mConnectDelayMillis;
    private final Context mContext;
    private final GBDevice mGbDevice;
    private int mPort;
    private final UUID mService;
    private final Handler mWriteHandler;
    private Thread readThread;
    private BluetoothSocket mBtSocket = null;
    private final HandlerThread mWriteHandlerThread = new HandlerThread("BtBRQueue_write_" + THREAD_COUNTER.getAndIncrement(), 10);
    private final Logger LOG = LoggerFactory.getLogger(BtBRQueue.class.getName() + "(" + QUEUE_COUNTER.getAndIncrement() + ")");
    private final AtomicBoolean mDisposed = new AtomicBoolean(false);

    /* JADX INFO: Access modifiers changed from: private */
    public Thread createReadThread() {
        return new Thread("BtBRQueue_read_" + THREAD_COUNTER.getAndIncrement()) { // from class: nodomain.freeyourgadget.gadgetbridge.service.btbr.BtBRQueue.1
            @Override // java.lang.Thread, java.lang.Runnable
            public void run() {
                BtBRQueue.this.LOG.debug("started thread {} for {}", getName(), BtBRQueue.this.mGbDevice.getAddress());
                byte[] buffer = new byte[BtBRQueue.this.mBufferSize];
                BtBRQueue.this.LOG.debug("Read thread started, entering loop");
                while (!BtBRQueue.this.mDisposed.get()) {
                    try {
                        if (BtBRQueue.this.mBtSocket == null) {
                            throw new IOException("mBtSocket was null");
                        }
                        int nRead = BtBRQueue.this.mBtSocket.getInputStream().read(buffer);
                        if (nRead == -1) {
                            throw new IOException("End of stream");
                        }
                        BtBRQueue.this.LOG.debug("Received {} bytes: {}", Integer.valueOf(nRead), GB.hexdump(buffer, 0, nRead));
                        try {
                            BtBRQueue.this.mCallback.onSocketRead(Arrays.copyOf(buffer, nRead));
                        } catch (Throwable ex) {
                            BtBRQueue.this.LOG.error("Failed to process received bytes in onSocketRead callback: ", ex);
                        }
                    } catch (IOException ex2) {
                        BtBRQueue.this.LOG.error("IO exception while reading message from socket, breaking out of read thread", (Throwable) ex2);
                    }
                }
                BtBRQueue.this.cleanup();
                if (BtBRQueue.this.mDisposed.get() || !GBApplication.getPrefs().getAutoReconnect(BtBRQueue.this.mGbDevice)) {
                    BtBRQueue.this.LOG.debug("Exited read thread loop, disconnecting");
                    BtBRQueue.this.mGbDevice.setUpdateState(GBDevice.State.NOT_CONNECTED, BtBRQueue.this.mContext);
                } else {
                    BtBRQueue.this.LOG.debug("Exited read thread loop, will wait for reconnect");
                    BtBRQueue.this.mGbDevice.setUpdateState(GBDevice.State.WAITING_FOR_RECONNECT, BtBRQueue.this.mContext);
                }
                BtBRQueue.this.LOG.debug("finished thread {}", getName());
            }
        };
    }

    public BtBRQueue(BluetoothAdapter btAdapter, final GBDevice gbDevice, Context context, SocketCallback socketCallback, UUID supportedService, int bufferSize, int connectDelayMillis, int port) {
        this.mPort = -1;
        this.mBtAdapter = btAdapter;
        this.mGbDevice = gbDevice;
        this.mContext = context;
        this.mCallback = socketCallback;
        this.mService = supportedService;
        this.mBufferSize = bufferSize;
        this.mConnectDelayMillis = connectDelayMillis;
        this.mPort = port;
        this.mWriteHandlerThread.start();
        new Handler(this.mWriteHandlerThread.getLooper()).post(new Runnable() { // from class: nodomain.freeyourgadget.gadgetbridge.service.btbr.BtBRQueue$$ExternalSyntheticLambda0
            @Override // java.lang.Runnable
            public final void run() {
                this.f$0.lambda$new$0(gbDevice);
            }
        });
        this.LOG.debug("Write handler thread for {} is prepared, creating write handler", gbDevice.getAddress());
        this.mWriteHandler = new Handler(this.mWriteHandlerThread.getLooper()) { // from class: nodomain.freeyourgadget.gadgetbridge.service.btbr.BtBRQueue.2
            @Override // android.os.Handler
            public void handleMessage(Message msg) {
                switch (msg.what) {
                    case 0:
                        if (BtBRQueue.this.mBtSocket == null) {
                            BtBRQueue.this.LOG.error("Got request to connect to RFCOMM socket, but it is null");
                            if (!GBApplication.getPrefs().getAutoReconnect(BtBRQueue.this.mGbDevice)) {
                                BtBRQueue.this.mGbDevice.setUpdateState(GBDevice.State.NOT_CONNECTED, BtBRQueue.this.mContext);
                            } else {
                                BtBRQueue.this.mGbDevice.setUpdateState(GBDevice.State.WAITING_FOR_RECONNECT, BtBRQueue.this.mContext);
                            }
                        } else {
                            if (BtBRQueue.this.mConnectDelayMillis > 0) {
                                BtBRQueue.this.LOG.debug("Waiting {} ms before connecting to RFCOMM socket", Integer.valueOf(BtBRQueue.this.mConnectDelayMillis));
                                try {
                                    Thread.sleep(BtBRQueue.this.mConnectDelayMillis);
                                } catch (InterruptedException e) {
                                    BtBRQueue.this.LOG.error("Interrupted while waiting for connect", (Throwable) e);
                                }
                            }
                            try {
                                BtBRQueue.this.LOG.debug("Connecting to RFCOMM socket for {}", BtBRQueue.this.mGbDevice.getName());
                                BtBRQueue.this.mBtSocket.connect();
                                BtBRQueue.this.LOG.info("Connected to RFCOMM socket for {}", BtBRQueue.this.mGbDevice.getName());
                                BtBRQueue.this.setDeviceConnectionState(GBDevice.State.CONNECTED);
                                if (BtBRQueue.this.readThread == null || !BtBRQueue.this.readThread.isAlive()) {
                                    BtBRQueue.this.readThread = BtBRQueue.this.createReadThread();
                                }
                                BtBRQueue.this.readThread.start();
                                BtBRQueue.this.onConnectionEstablished();
                                break;
                            } catch (IOException e2) {
                                BtBRQueue.this.LOG.error("IO exception while establishing socket connection: ", (Throwable) e2);
                                BtBRQueue.this.cleanup();
                                if (!GBApplication.getPrefs().getAutoReconnect(BtBRQueue.this.mGbDevice)) {
                                    BtBRQueue.this.mGbDevice.setUpdateState(GBDevice.State.NOT_CONNECTED, BtBRQueue.this.mContext);
                                    return;
                                } else {
                                    BtBRQueue.this.mGbDevice.setUpdateState(GBDevice.State.WAITING_FOR_RECONNECT, BtBRQueue.this.mContext);
                                    return;
                                }
                            } catch (SecurityException e3) {
                                BtBRQueue.this.LOG.error("Security exception while establishing socket connection: ", (Throwable) e3);
                                BtBRQueue.this.cleanup();
                                if (!GBApplication.getPrefs().getAutoReconnect(BtBRQueue.this.mGbDevice)) {
                                    BtBRQueue.this.mGbDevice.setUpdateState(GBDevice.State.NOT_CONNECTED, BtBRQueue.this.mContext);
                                    return;
                                } else {
                                    BtBRQueue.this.mGbDevice.setUpdateState(GBDevice.State.WAITING_FOR_RECONNECT, BtBRQueue.this.mContext);
                                    return;
                                }
                            }
                        }
                        break;
                    case 1:
                        try {
                            if (!BtBRQueue.this.isConnected()) {
                                BtBRQueue.this.LOG.debug("Not connected, updating device state to WAITING_FOR_RECONNECT");
                                BtBRQueue.this.setDeviceConnectionState(GBDevice.State.WAITING_FOR_RECONNECT);
                            } else {
                                Object obj = msg.obj;
                                if (!(obj instanceof Transaction)) {
                                    BtBRQueue.this.LOG.error("msg.obj is not an instance of Transaction");
                                } else {
                                    Transaction transaction = (Transaction) obj;
                                    Iterator<BtBRAction> it = transaction.getActions().iterator();
                                    while (true) {
                                        if (it.hasNext()) {
                                            BtBRAction action = it.next();
                                            if (BtBRQueue.this.LOG.isDebugEnabled()) {
                                                BtBRQueue.this.LOG.debug("About to run action: {}", action);
                                            }
                                            if (action.run(BtBRQueue.this.mBtSocket)) {
                                                BtBRQueue.this.LOG.debug("Action ok: {}", action);
                                            } else {
                                                BtBRQueue.this.LOG.error("Action returned false, cancelling further actions in transaction: {}", action);
                                            }
                                        }
                                    }
                                }
                            }
                        } catch (Throwable ex) {
                            BtBRQueue.this.LOG.error("IO Write Thread died: ", ex);
                            return;
                        }
                        break;
                    default:
                        BtBRQueue.this.LOG.warn("Unhandled write handler message {}", Integer.valueOf(msg.what));
                        break;
                }
            }
        };
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$new$0(GBDevice gbDevice) {
        this.LOG.debug("started thread {} for {}", Thread.currentThread().getName(), gbDevice.getAddress());
    }

    public boolean connect() {
        GBDevice.State state = this.mGbDevice.getState();
        if (state.equalsOrHigherThan(GBDevice.State.CONNECTING)) {
            this.LOG.warn("connect - ignored, state is {}", state);
            return false;
        }
        if (this.mBtSocket != null) {
            this.LOG.warn("connect - ignored, mBtSocket isn't null");
            return false;
        }
        if (this.mDisposed.get()) {
            this.LOG.error("connect - ignored, this BtBRQueue has already been disposed");
            return false;
        }
        this.LOG.info("Attempting to connect to {} ({})", this.mGbDevice.getName(), this.mGbDevice.getAddress());
        this.mBtAdapter.cancelDiscovery();
        GBDevice.State originalState = this.mGbDevice.getState();
        setDeviceConnectionState(GBDevice.State.CONNECTING);
        try {
            BluetoothDevice btDevice = this.mBtAdapter.getRemoteDevice(this.mGbDevice.getAddress());
            if (this.mPort > 0) {
                this.LOG.info("Creating RFCOMM socket to direct port: {}", Integer.valueOf(this.mPort));
                try {
                    Method m = btDevice.getClass().getMethod("createRfcommSocket", Integer.TYPE);
                    this.mBtSocket = (BluetoothSocket) m.invoke(btDevice, Integer.valueOf(this.mPort));
                } catch (Exception e) {
                    this.LOG.error("Reflection failed to create RFCOMM socket for port {}, falling back to UUID: ", Integer.valueOf(this.mPort), e);
                    this.mBtSocket = btDevice.createRfcommSocketToServiceRecord(this.mService);
                }
            } else {
                this.mBtSocket = btDevice.createRfcommSocketToServiceRecord(this.mService);
            }
            this.LOG.debug("Socket created, connecting in handler");
            this.mWriteHandler.sendMessageAtFrontOfQueue(this.mWriteHandler.obtainMessage(0));
            return true;
        } catch (IOException e2) {
            this.LOG.error("Unable to connect to RFCOMM endpoint: ", (Throwable) e2);
            setDeviceConnectionState(originalState);
            cleanup();
            return false;
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void onConnectionEstablished() {
        this.mCallback.onConnectionEstablished();
    }

    public void disconnect() {
        if (this.mWriteHandlerThread.isAlive()) {
            this.mWriteHandlerThread.quit();
            this.LOG.debug("finished thread {}", this.mWriteHandlerThread.getName());
        }
        if (this.mBtSocket != null && this.mBtSocket.isConnected()) {
            try {
                this.mBtSocket.close();
            } catch (IOException e) {
                this.LOG.error("IO exception while closing socket in disconnect(): ", (Throwable) e);
            }
        }
        this.mBtSocket = null;
        setDeviceConnectionState(GBDevice.State.NOT_CONNECTED);
    }

    boolean isConnected() {
        return this.mGbDevice.isConnected() && this.mBtSocket != null && this.mBtSocket.isConnected();
    }

    public void add(Transaction transaction) {
        this.LOG.debug("Adding transaction to looper message queue: {}", transaction);
        if (!transaction.isEmpty()) {
            this.mWriteHandler.obtainMessage(1, transaction).sendToTarget();
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void setDeviceConnectionState(GBDevice.State newState) {
        this.LOG.debug("New device connection state: {}", newState);
        this.mGbDevice.setState(newState);
        this.mGbDevice.sendDeviceUpdateIntent(this.mContext, GBDevice.DeviceUpdateSubject.CONNECTION_STATE);
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void cleanup() {
        if (this.mBtSocket != null) {
            try {
                this.mBtSocket.close();
            } catch (IOException e) {
            }
            this.mBtSocket = null;
        }
    }

    public void dispose() {
        if (this.mDisposed.getAndSet(true)) {
            this.LOG.warn("dispose() was called repeatedly");
            return;
        }
        disconnect();
        if (this.readThread != null && this.readThread.isAlive()) {
            this.readThread.interrupt();
            this.readThread = null;
        }
    }
}
