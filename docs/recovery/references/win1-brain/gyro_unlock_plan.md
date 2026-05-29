# 小米手环 9 陀螺仪 (Yaw) 这里挖掘方案

基于 DeepResearch 报告的深度分析，我们现在的目标是打破 Vela SDK 的“人为限制”，获取硬件本身具备的陀螺仪数据。

## 核心发现 (来自报告)
1. **硬件具备**：手环搭载 ST LSM6DSO 6轴芯片 (Accel + Gyro)。
2. **系统限制**：`system.sensor` 仅公开了 Accel 和 Compass (部分支持)。
3. **隐藏线索**：文档中 `interval: 'game'` (20ms) 暗示了高动态场景的存在，底层可能并未完全剔除 Gyro 代码。

## 行动路线图

### 阶段一：JS 反射攻击 (最快，成本最低)
尝试在 vela 应用中“盲调”那些文档里没写的接口。如果底层 C++ 绑定还在，我们就能直接拿到数据。

- [ ] **探测 1**：直接调用 `sensor.subscribeGyroscope`
- [ ] **探测 2**：枚举 `system.sensor` 对象的所有属性 (查看是否有隐藏方法)
- [ ] **探测 3**：尝试申请未公开权限 (manifest.json 添加 `system.sensor.gyro` 等)

### 阶段二：蓝牙 Protobuf 嗅探 (Plan B)
如果 JS 彻底被阉割，我们就去截获官方 App 的通信。
- [ ] 打开官方“体感游戏”模式 (该模式必须回传 Gyro)
- [ ] 使用 ADB 抓取 `btsnoop_hci.log`
- [ ] 分析 Protobuf 数据结构，找到开启 Gyro 的指令

---

## 阶段一：详细实施步骤 (JS 反射)

我们将修改 `index.ux`，注入一段“探测代码”。

1. **枚举属性**：打印 `sensor` 对象的所有 Key，看有没有惊喜。
2. **盲测调用**：不管有没有，直接强行调用 `subscribeGyroscope` 并挂载回调。
3. **权限试探**：在 manifest 里加一些“可能是真的”权限字符串。

### 待注入代码片段
```javascript
// 1. 反射探测
console.log("Sensor Keys: " + JSON.stringify(Object.keys(sensor)));
console.log("Sensor Props: " + JSON.stringify(Object.getOwnPropertyNames(sensor)));

// 2. 盲测 Gyro
try {
    if (sensor.subscribeGyroscope) {
        console.log("Found subscribeGyroscope! Trying to invoke...");
        sensor.subscribeGyroscope({
            callback: function(ret) {
                console.log("GYRO_DATA: " + JSON.stringify(ret));
            },
            fail: function(msg, code) {
                console.log("Gyro Subscribe Failed: " + msg + " code:" + code);
            }
        });
    } else {
        console.log("subscribeGyroscope not found in sensor object.");
    }
} catch (e) {
    console.log("Crash during gyro probe: " + e);
}
```
