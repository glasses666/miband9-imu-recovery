package nodomain.freeyourgadget.gadgetbridge.activities.debug;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Bundle;
import android.widget.TextView;
import androidx.localbroadcastmanager.content.LocalBroadcastManager;
import nodomain.freeyourgadget.gadgetbridge.R;
import nodomain.freeyourgadget.gadgetbridge.activities.AbstractGBActivity;
import nodomain.freeyourgadget.gadgetbridge.service.devices.xiaomi.XiaomiSppSupport;

/* JADX INFO: loaded from: classes12.dex */
public class ImuDebugActivity extends AbstractGBActivity {
    private final BroadcastReceiver mReceiver = new BroadcastReceiver() { // from class: nodomain.freeyourgadget.gadgetbridge.activities.debug.ImuDebugActivity.1
        @Override // android.content.BroadcastReceiver
        public void onReceive(Context context, Intent intent) {
            if (XiaomiSppSupport.ACTION_DEBUG_IMU_DATA.equals(intent.getAction())) {
                ImuDebugActivity.this.updateUI(intent);
            }
        }
    };
    private TextView tvAccel;
    private TextView tvGyro;
    private TextView tvRaw;
    private TextView tvStats;

    @Override // nodomain.freeyourgadget.gadgetbridge.activities.AbstractGBActivity, androidx.fragment.app.FragmentActivity, androidx.activity.ComponentActivity, androidx.core.app.ComponentActivity, android.app.Activity
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_imu_debug);
        this.tvStats = (TextView) findViewById(R.id.tv_imu_stats);
        this.tvAccel = (TextView) findViewById(R.id.tv_accel_data);
        this.tvGyro = (TextView) findViewById(R.id.tv_gyro_data);
        this.tvRaw = (TextView) findViewById(R.id.tv_raw_log);
    }

    @Override // nodomain.freeyourgadget.gadgetbridge.activities.AbstractGBActivity, androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onResume() {
        super.onResume();
        LocalBroadcastManager.getInstance(this).registerReceiver(this.mReceiver, new IntentFilter(XiaomiSppSupport.ACTION_DEBUG_IMU_DATA));
    }

    @Override // androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onPause() {
        super.onPause();
        LocalBroadcastManager.getInstance(this).unregisterReceiver(this.mReceiver);
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void updateUI(Intent intent) {
        short[] values = intent.getShortArrayExtra("values");
        float rate = intent.getFloatExtra("rate", 0.0f);
        int total = intent.getIntExtra("total_packets", 0);
        String rawHex = intent.getStringExtra("raw_hex");
        if (values != null && values.length >= 7) {
            this.tvAccel.setText(String.format("X: %6d\nY: %6d\nZ: %6d", Short.valueOf(values[1]), Short.valueOf(values[2]), Short.valueOf(values[3])));
            this.tvGyro.setText(String.format("X: %6d\nY: %6d\nZ: %6d", Short.valueOf(values[4]), Short.valueOf(values[5]), Short.valueOf(values[6])));
        }
        this.tvStats.setText(String.format("Rate: %.1f Hz\nTotal Packets: %d", Float.valueOf(rate), Integer.valueOf(total)));
        this.tvRaw.setText(rawHex);
    }
}
