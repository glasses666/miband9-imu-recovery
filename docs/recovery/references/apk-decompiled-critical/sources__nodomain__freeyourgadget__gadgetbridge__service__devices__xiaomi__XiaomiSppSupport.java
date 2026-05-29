package nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi;

import android.bluetooth.BluetoothAdapter;
import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import androidx.localbroadcastmanager.content.LocalBroadcastManager;
import j$.util.Objects;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import nodomain.freeyourgadget.gadgetbridge.deviceevents.GBDeviceEventUpdateDeviceInfo;
import nodomain.freeyourgadget.gadgetbridge.impl.GBDevice;
import nodomain.freeyourgadget.gadgetbridge.proto.xiaomi.XiaomiProto;
import nodomain.freeyourgadget.gadgetbridge.service.btbr.AbstractBTBRDeviceSupport;
import nodomain.freeyourgadget.gadgetbridge.service.btbr.TransactionBuilder;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.AbstractXiaomiSppProtocol;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiChannelHandler;
import nodomain.freeyourgadget.gadgetbridge.util.GB;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/* JADX INFO: loaded from: classes3.dex */
public class XiaomiSppSupport extends XiaomiConnectionSupport {
    public static final String ACTION_DEBUG_IMU_DATA = "nodomain.freeyourgadget.gadgetbridge.devices.xiaomi.ACTION_DEBUG_IMU_DATA";
    private static final Logger LOG = LoggerFactory.getLogger((Class<?>) XiaomiSppSupport.class);
    private final Context mContext;
    private final XiaomiSupport mXiaomiSupport;
    private int mImuPacketCount = 0;
    private long mLastStatTime = 0;
    AbstractBTBRDeviceSupport commsSupport = new AnonymousClass1(LOG, 1024, 5);
    private final ByteArrayOutputStream buffer = new ByteArrayOutputStream();
    private final Map<XiaomiChannelHandler.Channel, XiaomiChannelHandler> mChannelHandlers = new HashMap();
    private final Handler mVersionResponseTimeoutHandler = new Handler(Looper.getMainLooper());
    private AbstractXiaomiSppProtocol mProtocol = new XiaomiSppProtocolV1(this);

    /* JADX INFO: renamed from: nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSppSupport$1, reason: invalid class name */
    class AnonymousClass1 extends AbstractBTBRDeviceSupport {
        AnonymousClass1(Logger arg0, int arg1, int arg2) {
            super(arg0, arg1, arg2);
        }

        @Override // nodomain.freeyourgadget.gadgetbridge.service.DeviceSupport
        public boolean useAutoConnect() {
            return XiaomiSppSupport.this.mXiaomiSupport.useAutoConnect();
        }

        @Override // nodomain.freeyourgadget.gadgetbridge.service.btbr.SocketCallback
        public void onSocketRead(byte[] data) {
            XiaomiSppSupport.this.onSocketRead(data);
        }

        @Override // nodomain.freeyourgadget.gadgetbridge.service.btbr.AbstractBTBRDeviceSupport
        protected TransactionBuilder initializeDevice(TransactionBuilder builder) {
            String cachedFirmwareVersion;
            XiaomiSppSupport.this.reset();
            if (getDevice().getFirmwareVersion() == null) {
                GBDevice device = getDevice();
                if (XiaomiSppSupport.this.mXiaomiSupport.getCachedFirmwareVersion() != null) {
                    cachedFirmwareVersion = XiaomiSppSupport.this.mXiaomiSupport.getCachedFirmwareVersion();
                } else {
                    cachedFirmwareVersion = "N/A";
                }
                device.setFirmwareVersion(cachedFirmwareVersion);
            }
            builder.setDeviceState(GBDevice.State.INITIALIZING);
            builder.setDeviceState(GBDevice.State.AUTHENTICATING);
            builder.write(XiaomiSppPacketV1.newBuilder().channel(XiaomiChannelHandler.Channel.Version).needsResponse(true).opCode(0).dataType(0).frameSerial(0).build().encode(null, null));
            builder.run(new Runnable() { // from class: nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSppSupport$1$$ExternalSyntheticLambda0
                @Override // java.lang.Runnable
                public final void run() {
                    this.f$0.lambda$initializeDevice$0();
                }
            });
            return builder;
        }

        /* JADX INFO: Access modifiers changed from: private */
        public /* synthetic */ void lambda$initializeDevice$0() {
            XiaomiSppSupport.this.mVersionResponseTimeoutHandler.postDelayed(XiaomiSppSupport.this.new VersionTimeoutRunnable(), 5000L);
        }

        @Override // nodomain.freeyourgadget.gadgetbridge.service.btbr.AbstractBTBRDeviceSupport
        protected UUID getSupportedService() {
            return XiaomiUuids.UUID_SERVICE_SERIAL_PORT_PROFILE;
        }

        @Override // nodomain.freeyourgadget.gadgetbridge.service.btbr.AbstractBTBRDeviceSupport, nodomain.freeyourgadget.gadgetbridge.service.DeviceSupport
        public void dispose() {
            XiaomiSppSupport.this.mXiaomiSupport.onDisconnect();
            super.dispose();
        }
    }

    public XiaomiSppSupport(XiaomiSupport xiaomiSupport, Context context) {
        this.mXiaomiSupport = xiaomiSupport;
        this.mContext = context;
        this.mChannelHandlers.put(XiaomiChannelHandler.Channel.Version, new XiaomiChannelHandler() { // from class: nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSppSupport$$ExternalSyntheticLambda0
            @Override // nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiChannelHandler
            public final void handle(byte[] bArr) {
                this.f$0.handleVersionPacket(bArr);
            }
        });
        Map<XiaomiChannelHandler.Channel, XiaomiChannelHandler> map = this.mChannelHandlers;
        XiaomiChannelHandler.Channel channel = XiaomiChannelHandler.Channel.ProtobufCommand;
        XiaomiSupport xiaomiSupport2 = this.mXiaomiSupport;
        Objects.requireNonNull(xiaomiSupport2);
        map.put(channel, new XiaomiBleProtocolV1$$ExternalSyntheticLambda0(xiaomiSupport2));
        this.mChannelHandlers.put(XiaomiChannelHandler.Channel.Activity, new XiaomiChannelHandler() { // from class: nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSppSupport$$ExternalSyntheticLambda1
            @Override // nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiChannelHandler
            public final void handle(byte[] bArr) {
                this.f$0.handleActivityOrImu(bArr);
            }
        });
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void handleActivityOrImu(byte[] payload) {
        handleImuData(payload);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiConnectionSupport
    public void setContext(GBDevice device, BluetoothAdapter adapter, Context context) {
        this.commsSupport.setContext(device, adapter, context);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiConnectionSupport
    public boolean connect() {
        return this.commsSupport.connect();
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiConnectionSupport
    public void dispose() {
        this.commsSupport.dispose();
        this.mVersionResponseTimeoutHandler.removeCallbacksAndMessages(null);
    }

    protected XiaomiAuthService getAuthService() {
        return this.mXiaomiSupport.getAuthService();
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiConnectionSupport
    public void onUploadProgress(int textRsrc, int progressPercent, boolean ongoing) {
        try {
            TransactionBuilder builder = this.commsSupport.createTransactionBuilder("send data upload progress");
            builder.setProgress(textRsrc, ongoing, progressPercent);
            builder.queue();
        } catch (Exception e) {
            LOG.error("Failed to update progress notification", (Throwable) e);
        }
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiConnectionSupport
    public void runOnQueue(String taskName, Runnable runnable) {
        if (this.commsSupport == null) {
            LOG.error("commsSupport is null, unable to queue task");
            return;
        }
        TransactionBuilder b = this.commsSupport.createTransactionBuilder("run task " + taskName + " on queue");
        b.run(runnable);
        b.queue();
    }

    private void skipBuffer(int newStart) {
        byte[] bufferState = this.buffer.toByteArray();
        this.buffer.reset();
        if (newStart < 0) {
            newStart = bufferState.length;
        }
        if (newStart >= bufferState.length) {
            return;
        }
        this.buffer.write(bufferState, newStart, bufferState.length - newStart);
    }

    private void processBuffer() {
        int skipBytes;
        boolean shouldProcess = true;
        while (shouldProcess) {
            byte[] bufferState = this.buffer.toByteArray();
            AbstractXiaomiSppProtocol.ParseResult parseResult = this.mProtocol.processPacket(bufferState);
            LOG.debug("processBuffer(): protocol.processPacket() returned status {}", parseResult.status);
            switch (parseResult.status) {
                case Incomplete:
                    skipBytes = 0;
                    shouldProcess = false;
                    break;
                case Complete:
                    skipBytes = parseResult.packetSize;
                    break;
                case Invalid:
                    skipBytes = this.mProtocol.findNextPacketOffset(bufferState);
                    if (skipBytes < 0) {
                        skipBytes = bufferState.length;
                    }
                    break;
                default:
                    throw new IllegalStateException(String.format("Unhandled parse state %s", parseResult.status));
            }
            if (skipBytes > 0) {
                LOG.debug("processBuffer(): skipping {} bytes for state {}", Integer.valueOf(skipBytes), parseResult.status);
                skipBuffer(skipBytes);
            }
        }
    }

    public void onSocketRead(byte[] data) {
        if (data != null && data.length > 0) {
            Log.i("MI_IMU_RAW_RX", GB.hexdump(data));
        }
        try {
            this.buffer.write(data);
        } catch (IOException ex) {
            LOG.error("Exception while writing buffer: ", (Throwable) ex);
        }
        processBuffer();
    }

    protected void onPacketReceived(XiaomiChannelHandler.Channel channel, byte[] payload) {
        XiaomiChannelHandler handler = this.mChannelHandlers.get(channel);
        if (handler != null) {
            handler.handle(payload);
        } else {
            LOG.warn("Unhandled SppPacket on channel {}", channel);
        }
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiConnectionSupport
    public void sendCommand(String taskName, XiaomiProto.Command command) {
        try {
            TransactionBuilder builder = this.commsSupport.createTransactionBuilder("send " + taskName);
            sendCommand(builder, command);
            builder.queue();
        } catch (Exception ex) {
            LOG.error("Caught unexpected exception while sending command, device may not have been informed!", (Throwable) ex);
        }
    }

    public void sendCommand(TransactionBuilder builder, XiaomiProto.Command command) {
        LOG.debug("sendCommand(): encoded command for task '{}': {}", builder.getTaskName(), GB.hexdump(command.toByteArray()));
        if (command.getType() == 1) {
            builder.write(this.mProtocol.encodePacket(XiaomiChannelHandler.Channel.Authentication, command.toByteArray()));
        } else {
            builder.write(this.mProtocol.encodePacket(XiaomiChannelHandler.Channel.ProtobufCommand, command.toByteArray()));
        }
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiConnectionSupport
    public void sendDataChunk(String taskName, byte[] chunk, XiaomiSendCallback callback) {
        LOG.debug("sendDataChunk(): encoded data chunk for task '{}': {}", taskName, GB.hexdump(chunk));
        this.commsSupport.createTransactionBuilder("send " + taskName).write(this.mProtocol.encodePacket(XiaomiChannelHandler.Channel.Data, chunk)).queue();
        if (callback != null) {
            callback.onSend();
        }
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiConnectionSupport
    public void sendRawBytes(byte[] bytes, XiaomiSendCallback callback) {
        LOG.debug("sendRawBytes(): sending {} raw bytes", Integer.valueOf(bytes.length));
        this.commsSupport.createTransactionBuilder("send raw bytes").write(bytes).queue();
        if (callback != null) {
            callback.onSend();
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void handleVersionPacket(byte[] payloadBytes) {
        this.mVersionResponseTimeoutHandler.removeCallbacksAndMessages(null);
        if (payloadBytes != null && payloadBytes.length > 0) {
            LOG.debug("Received SPP protocol version: {}", GB.hexdump(payloadBytes));
            GBDeviceEventUpdateDeviceInfo event = new GBDeviceEventUpdateDeviceInfo("SPP_PROTOCOL: ", GB.hexdump(payloadBytes));
            this.mXiaomiSupport.evaluateGBDeviceEvent(event);
            if (payloadBytes[0] >= 2) {
                LOG.info("handleVersionPacket(): detected protocol version higher than 2, switching protocol");
                this.mProtocol = new XiaomiSppProtocolV2(this);
            }
        }
        if (this.mProtocol.initializeSession()) {
            this.mXiaomiSupport.getAuthService().startEncryptedHandshake();
        }
    }

    public void reset() {
        this.buffer.reset();
        this.mVersionResponseTimeoutHandler.removeCallbacksAndMessages(null);
        this.mProtocol = new XiaomiSppProtocolV1(this);
    }

    private void handleImuData(byte[] payload) {
        this.mImuPacketCount++;
        long now = System.currentTimeMillis();
        Intent intent = new Intent(ACTION_DEBUG_IMU_DATA);
        if (payload.length >= 14) {
            short[] values = new short[payload.length / 2];
            ByteBuffer.wrap(payload).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer().get(values);
            intent.putExtra("values", values);
        }
        if (now - this.mLastStatTime >= 1000) {
            float rate = this.mImuPacketCount / ((now - this.mLastStatTime) / 1000.0f);
            intent.putExtra("rate", rate);
            this.mLastStatTime = now;
            this.mImuPacketCount = 0;
            LOG.info("MI_IMU_STATS: Rate={} Hz", Float.valueOf(rate));
        }
        intent.putExtra("total_packets", this.mImuPacketCount);
        intent.putExtra("raw_hex", GB.hexdump(payload, 0, payload.length));
        LocalBroadcastManager.getInstance(this.mContext).sendBroadcast(intent);
    }

    class VersionTimeoutRunnable implements Runnable {
        VersionTimeoutRunnable() {
        }

        @Override // java.lang.Runnable
        public void run() {
            XiaomiSppSupport.LOG.warn("SPP protocol version request timed out");
            XiaomiSppSupport.this.handleVersionPacket(new byte[0]);
        }
    }
}
