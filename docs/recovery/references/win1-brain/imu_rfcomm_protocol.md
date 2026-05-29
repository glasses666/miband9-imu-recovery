# Mi Band 9 IMU 成功协议记录

## 📌 核心发现

**IMU 数据通过 RFCOMM (Channel 5) 传输，使用 Xiaomi 私有协议 + Protobuf！**

---

## 1. 连接参数

| 参数 | 值 |
|------|-----|
| **协议** | Bluetooth Classic RFCOMM |
| **通道** | Channel 5 |
| **MAC** | `08:16:D5:B7:80:8F` (用户设备) |

---

## 2. 初始化命令序列 (激活 IMU)

必须按顺序发送以下 3 条命令：

```python
CMDS = [
    # 1. Init (初始化)
    bytes.fromhex("a5a5020016001d4d0101030001000002020000fc03020020000402001027"),

    # 2. Config/Auth (配置/认证)
    bytes.fromhex("a5a503001d008cb801010801101a1a15f201120a10f0ad2fd756d4fe746f53bba92763adc5"),

    # 3. Ack (确认)
    bytes.fromhex("a5a5010000000000"),
]
```

**发送间隔**: 每条命令后等待 **500ms**。

---

## 3. 数据包格式

### 3.1 帧结构

```
+--------+--------+--------+--------+-----------+
| Magic  | Type   | Length | CRC    | Payload   |
| a5 a5  | 2B     | 2B     | 2B     | N Bytes   |
+--------+--------+--------+--------+-----------+
     2B       2B       2B       2B      Length
```

- **Magic**: `0xA5A5` (固定)
- **Type**:
  - `0x0003` = IMU 数据包
  - 其他 = 控制/状态包
- **Length**: Payload 长度 (小端)
- **CRC**: 校验和 (小端)

### 3.2 Payload (Protobuf 格式)

| Field # | Wire Type | 含义 |
|---------|-----------|------|
| 1 | Varint | Sensor ID (可能) |
| 2 | Varint | Sequence 序列号 |
| 3 | Bytes | 原始 IMU 数据 |

### 3.3 IMU 数据 (Field 3 内部)

```
+-------+-------+-------+-------+-------+-------+ ...
|  X    |  X    |  Y    |  Y    |  Z    |  Z    |
| int16 | int16 | int16 |
+-------+-------+-------+-------+-------+-------+
```

- 每组 6 字节 = 1 个 XYZ 采样点
- 格式: **Little-endian signed int16**
- 范围: -32768 ~ +32767 (需要转换为 g 或 mg)

---

## 4. 示例输出

```
timestamp: 1767547733.390
Seq: 26
Data: [506, 2612, 21776, 3240, 31510, -4585, 865, 6122, ...]
```

每个数值都是 16 位有符号整数，代表加速度计或陀螺仪的某个轴向数据。

---

## 5. 相关文件

| 文件 | 用途 |
|------|------|
| `replay_sensor_init.py` | 发送初始化命令并捕获数据流 |
| `parse_sensor_dump.py` | 解析捕获的二进制数据 |
| `sensor_stream_replay.bin` | 捕获的原始数据流 |
| `sensor_dump.bin` | 另一份数据转储 |

---

## 6. 关键结论

| 路径 | 协议 | 状态 |
|------|------|------|
| **RFCOMM Ch5 + Protobuf** | 私有协议 | ✅ **已成功** |
| **GameSir HID (0x1812)** | BLE HID | ❌ 无数据 |
| **fee1 BLE GATT** | BLE GATT | ❌ 需要先 SPP 认证 |

**真正的 IMU 数据在 RFCOMM，不在 GameSir HID！**

---

## 7. 下一步

既然 Windows 已经连接了 "GameSir-Nova Pro"，但我们需要的是 **RFCOMM Channel 5**：

1. 修改 `replay_sensor_init.py` 使其在 Windows 上运行 (使用 PyBluez 或 Bleak 的经典蓝牙支持)。
2. 或者在 Android 上通过 Gadgetbridge 发送这些初始化命令。
