# Mi Band 9 (GameSir Mode) IMU Protocol Analysis

## 1. Context & Objective
**Device**: Xiaomi Mi Band 9 (M2345B1)
**Mode**: "GameSir-Nova Pro" (Triggered by specific byte sequence over SPP or App selection).
**Goal**: Enable high-frequency raw IMU data stream (Accelerometer/Gyroscope) via BLE.
**Previous Success**: Data stream successfully enabled via **Classic Bluetooth RFCOMM (Channel 5)** using a specific binary initialization sequence (Protobuf encapsulated).

## 2. BLE Interaction Layer (The "GameSir" Interface)
The device exposes a generic access profile with custom services when in GameSir mode on Windows/Android. It does **not** behave like a standard HID device (no `0x1812` service observed on Windows/nRF Connect in some states).

### Identified Services & Characteristics
*   **Service `0x8650`**
    *   **`0x865F` (Notify/Write/Read)**: **Primary Control/Response Channel**.
        *   Behaves like a command-response interface.
    *   `0x8655` (Notify/Write/Read): Purpose unknown, potentially related to auth.
*   **Service `0xFF10`**
    *   **`0xFF12` (Write)**: **Command Input**.
    *   **`0xFF11` (Notify)**: **Data Output** (Likely IMU stream or ACK).

## 3. Key Findings

### A. The "Checksum" Protocol
All responses received on `0x865F` strictly follow a **Sum Checksum** rule:
`Last Byte == Sum(All Preceding Bytes) & 0xFF`

**Evidence**:
1.  **Command**: `07` (Sent to `0x865F`)
    *   **Response**: `07 00 06 00 00 0D`
    *   **Check**: `07+00+06+00+00 = 0D` (Valid)
2.  **Command**: `08` (Sent to `0x865F`)
    *   **Response**: `08 00 07 00 05 01 15`
    *   **Check**: `08+00+07+00+05+01 = 15` (Valid)

### B. The "0xFF12" Breakthrough (The Missing Link)
We successfully observed **one** instance where writing to `0xFF12` triggered a response on `0x865F`. This proves `0xFF12` is the entry point for deeper commands.

*   **Action**: Write `01 01 03` to `0xFF12`
*   **Result**: Notify on `0x865F`: `24 01 05 48 72`
*   **Analysis**:
    *   `24` = Opcode/Status?
    *   `01 05 48` = Payload
    *   `72` = Checksum (`24 + 01 + 05 + 48 = 72`) -> **VALID**

## 4. The RFCOMM Correlation
We have a known working sequence from RFCOMM that activates the sensor. We suspect this payload needs to be tunneled through the BLE characteristics, likely wrapped with the Checksum Protocol.

**RFCOMM Payload (Hex)**:
```
Header: a5 a5
Len:    02 00
Cmd:    16 00
Data:   1d 4d 01 01 03 00 01 00 00 02 02 00 00 fc 03 02 00 20 00 04 02 00 10 27
```
*Note: The sequence `01 01 03` appears comfortably inside the RFCOMM payload.*

## 5. Current Bottlenecks & Hypotheses

### Bottleneck: Reproducibility
We cannot reliably reproduce the `0xFF12` -> `0x865F` response.
*   **Hypothesis 1 (State Machine)**: The device is in a "Locked" state. It requires a specific "Handshake" or "Prime" sequence on `0x865F` (e.g., writing `01`, `02`, `03`...) before `0xFF12` becomes active.
*   **Hypothesis 2 (Timing)**: The BLE link policy might sleep aggressively. Commands need to be sent immediately after a Keep-Alive packet (like `07`).

### Bottleneck: Protocol Encapsulation
We are unsure if the BLE characteristic expects:
1.  **Raw RFCOMM Payload**: Just the bytes.
2.  **Checksummed Payload**: `[Payload] + [Checksum]`
3.  **Fragmented Packets**: BLE MTU limitations (20 bytes) might require splitting the long RFCOMM instruction.

## 6. Next Steps for Analysis
1.  **Analyze the "Prime" Sequence**: What exactly did we do before the successful `0xFF12` write? (Was it a specific heartbeat on `0x865F`?)
2.  **Construct the Packet**:
    *   Take the RFCOMM payload: `0101030001000002020000fc03020020000402001027`
    *   Calculate Checksum: `0x68`
    *   Construct Candidate: `0101030001000002020000fc0302002000040200102768`
3.  **Fuzzing Strategy**: Systematically test typical "Unlock" opcodes (`10`, `11`, `20`, `A0`) on `0x865F` to see if connection state changes.
