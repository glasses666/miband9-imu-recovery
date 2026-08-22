// Minimal SportXms/812 plaintext command builder extracted from Mi Fitness.
//
// This is deliberately package-less so it can be compiled and run outside Android:
//   javac tools/miband9ctl/gadgetbridge_port_skeleton/XiaomiSportXms812Command.java
//   java -cp tools/miband9ctl/gadgetbridge_port_skeleton XiaomiSportXms812Command 1800000000 32
//
// The returned bytes are the protobuf-nano hns command body before Xiaomi transport
// encryption/framing. In Gadgetbridge, send these bytes through the authenticated
// Xiaomi ProtobufCommand/PB channel, not as raw GATT bytes.

import java.io.ByteArrayOutputStream;
import java.util.Locale;

public final class XiaomiSportXms812Command {
    private XiaomiSportXms812Command() {}

    public static byte[] buildStartCommand(final long timestampSec, final int timezoneValue) {
        return buildCommand(timestampSec, timezoneValue, 812, 1, 3, null);
    }

    public static byte[] buildCommand(
            final long timestampSec,
            final int timezoneValue,
            final int sportType,
            final int appSportState,
            final int selectVersion,
            final Integer accessoryWearMode
    ) {
        final byte[] oe4 = fieldVarint(1, timezoneValue);

        final ByteArrayOutputStream hfa = new ByteArrayOutputStream();
        write(hfa, fieldVarint(1, timestampSec));
        write(hfa, fieldMessage(2, oe4));
        write(hfa, fieldVarint(3, sportType));
        write(hfa, fieldVarint(4, sportStateToProto(appSportState)));
        write(hfa, fieldVarint(6, selectVersion));
        if (accessoryWearMode != null) {
            write(hfa, fieldVarint(10, accessoryWearMode));
        }

        final byte[] uca = fieldMessage(20, hfa.toByteArray());

        final ByteArrayOutputStream hns = new ByteArrayOutputStream();
        write(hns, fieldVarint(1, 8));
        write(hns, fieldVarint(2, 26));
        write(hns, fieldMessage(10, uca));
        return hns.toByteArray();
    }

    private static int sportStateToProto(final int state) {
        if (state == 1) return 0;
        if (state == 2) return 1;
        if (state == 3) return 2;
        return 3;
    }

    private static byte[] fieldVarint(final int fieldNumber, final long value) {
        final ByteArrayOutputStream out = new ByteArrayOutputStream();
        write(out, varint((fieldNumber << 3) | 0));
        write(out, varint(value));
        return out.toByteArray();
    }

    private static byte[] fieldMessage(final int fieldNumber, final byte[] payload) {
        final ByteArrayOutputStream out = new ByteArrayOutputStream();
        write(out, varint((fieldNumber << 3) | 2));
        write(out, varint(payload.length));
        write(out, payload);
        return out.toByteArray();
    }

    private static byte[] varint(long value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative varints are not supported here");
        }
        final ByteArrayOutputStream out = new ByteArrayOutputStream();
        while (true) {
            int b = (int) (value & 0x7fL);
            value >>>= 7;
            if (value != 0) {
                out.write(b | 0x80);
            } else {
                out.write(b);
                return out.toByteArray();
            }
        }
    }

    private static void write(final ByteArrayOutputStream out, final byte[] bytes) {
        out.write(bytes, 0, bytes.length);
    }

    public static String toHex(final byte[] bytes) {
        final StringBuilder sb = new StringBuilder(bytes.length * 3);
        for (int i = 0; i < bytes.length; i++) {
            if (i > 0) sb.append(' ');
            sb.append(String.format(Locale.ROOT, "%02x", bytes[i] & 0xff));
        }
        return sb.toString();
    }

    public static void main(final String[] args) {
        final long timestampSec = args.length > 0 ? Long.parseLong(args[0]) : System.currentTimeMillis() / 1000L;
        final int timezoneValue = args.length > 1 ? Integer.parseInt(args[1]) : 32;
        final byte[] command = buildStartCommand(timestampSec, timezoneValue);
        System.out.println(toHex(command));
    }
}
