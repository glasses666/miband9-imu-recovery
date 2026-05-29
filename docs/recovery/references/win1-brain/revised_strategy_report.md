# 项目重定向报告：Mi Band 9 IMU 数据获取

## 1. 关键误判修正 (基于外部分析反馈)

经过对 `gptana` 建议和固件字符串的再分析，我们确认了之前的重大误判：

*   **`hyn92xx` 不是 IMU**: 固件中的 `/vendor/touch/hyn_cst9217_XL_3206_fw.bin` 路径证实 `hyn92xx` 是 **Hynitron 触控芯片** 的驱动。
*   **`set_work_mode` 无效**: `ENUM_MODE_DEBUG_RAWDATA` 开启的是触控屏的原始电容数据，而非加速度计/陀螺仪数据。
*   **结论**: 立即停止针对 `hyn92xx` 和 `set_work_mode` 的 Fuzzing，因为这是一条死胡同。

---

## 2. 可行性边界重新评估

根据 Xiaomi Vela 官方文档和 GPT 分析：

| 方案 | 理论上限 | 优势 | 劣势 | 结论 |
| :--- | :--- | :--- | :--- | :--- |
| **SPP (Data Channel)** | 未知 | 理论带宽大 | 入口未找到，可能是工厂私有 | **暂停** (除非 Btsnoop 发现线索) |
| **Vela 快应用 (JS)** | ~50Hz (Game Mode) | **官方支持接口**，开发门槛低 | 无陀螺仪接口(?需验证)，频率受限 | **首选 (Plan A)** |
| **NuttShell (NUS)** | >100Hz | 也就是 Linux/Unix Shell | 需要 Auth Key 和特定激活指令 | **备选 (Plan B)** |

**目前最稳妥的路线是 Plan A (Vela 快应用)，先拿到 50Hz 数据实现闭环，再探索 Plan B。**

---

## 3. 执行计划更新

### 阶段一：建立 Vela 快应用数据通路 (Plan A)
目标：编写一个运行在手环上的 JS 应用，采集加速度数据并通过蓝牙发回手机/PC。

1.  **开发 Vela 应用 (`app.ux`)**:
    *   使用 `@system.sensor` 接口订阅加速度计 (`subscribeAccelerometer`)。
    *   设置频率为 `game` (20ms/50Hz)。
    *   即使没有陀螺仪文档，也尝试调用 `subscribeGyroscope` 碰运气。
2.  **建立通信 (`@system.interconnect`)**:
    *   使用 Vela 的 `interconnect` 模块，将数据发送给手机伴侣 App。
    *   或者尝试将数据打印到 Console，通过 `btsnoop` 或 ADB 抓取。

### 阶段二：流量取证 (Plan B)
目标：确认官方 Mi Fitness App 是否使用了我们未知的“私有高频通道”。

1.  **用户行动**：请在断开 Gadgetbridge 的情况下，连接官方 **Mi Fitness** App。
2.  **操作**：在 App 中开启一次“运动记录”，或者寻找任何可能用到实施姿态的功能（如表盘预览、指南针校准）。
3.  **抓包**：获取 Android 的 `btsnoop_hci.log`。
4.  **分析**：使用 `xiaomi_protobuf_extractor` 或 Wireshark 查看是否有 **Protobuf Channel (1)** 或 **Data Channel (2)** 的大量数据传输。
    *   如果没有：说明官方也没用高频数据，硬件能力被锁定。
    *   如果有：逆向该数据包结构，复刻到 Gadgetbridge。

---

## 4. 提交给 GPT 的新 Prompt (咨询代码实现)

如果你想让 GPT 帮你写 Vela 代码，可以使用以下提示词：

```markdown
我决定放弃隐藏的 Debug 模式，转而使用 **Xiaomi Vela 快应用 (Quick App)** 接口来开发一个数据采集应用。

**目标：**
开发一个运行在 Mi Band 9 (Vela OS) 上的 JS 快应用，功能如下：
1. 使用 `system.sensor` 监听加速度数据 (频率设为 'game')。
2. 尝试监听陀螺仪数据 (如果有未公开接口)。
3. 使用 `system.interconnect` 或其他方式，将采集到的数据实时发送给连接的手机 App (或通过日志输出)。

**请提供：**
1. `manifest.json` 配置示例 (需要声明哪些权限？)。
2. `app.ux` 或 `index.ux` 的完整代码实现。
3. 如果 `subscribeGyroscope` 不在文档中，通常 Vela/NuttX 的 JS 绑定会有什么命名惯例可以尝试？
```
