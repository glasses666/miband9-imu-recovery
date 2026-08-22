package nodomain.freeyourgadget.gadgetbridge.devices.xiaomi.watches;

import java.util.regex.Pattern;
import nodomain.freeyourgadget.gadgetbridge.R;
import nodomain.freeyourgadget.gadgetbridge.devices.DeviceCoordinator;
import nodomain.freeyourgadget.gadgetbridge.devices.xiaomi.XiaomiCoordinator;
import nodomain.freeyourgadget.gadgetbridge.impl.GBDevice;

/* JADX INFO: loaded from: classes10.dex */
public class MiBand9Coordinator extends XiaomiCoordinator {
    @Override // nodomain.freeyourgadget.gadgetbridge.devices.DeviceCoordinator
    public int getDeviceNameResource() {
        return R.string.devicetype_miband9;
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.devices.AbstractDeviceCoordinator
    protected Pattern getSupportedDeviceName() {
        return Pattern.compile("^Xiaomi Smart Band 9 [0-9A-F]{4}$");
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.devices.AbstractDeviceCoordinator, nodomain.freeyourgadget.gadgetbridge.devices.DeviceCoordinator
    public int getDefaultIconResource() {
        return R.drawable.ic_device_miband6;
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.devices.AbstractBLEDeviceCoordinator, nodomain.freeyourgadget.gadgetbridge.devices.AbstractDeviceCoordinator, nodomain.freeyourgadget.gadgetbridge.devices.DeviceCoordinator
    public DeviceCoordinator.ConnectionType getConnectionType() {
        return DeviceCoordinator.ConnectionType.BT_CLASSIC;
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.devices.AbstractDeviceCoordinator, nodomain.freeyourgadget.gadgetbridge.devices.DeviceCoordinator
    public boolean isExperimental() {
        return true;
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.devices.DeviceCoordinator
    public DeviceCoordinator.DeviceKind getDeviceKind(GBDevice device) {
        return DeviceCoordinator.DeviceKind.FITNESS_BAND;
    }
}
