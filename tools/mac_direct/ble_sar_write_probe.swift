import Foundation
import CoreBluetooth
import CryptoKit

struct SarWriteEvent: Codable { let characteristic: String; let length: Int; let sha256_16: String; let hexPrefix: String; let hex: String }
struct SarWriteResult: Codable {
    let startedAt: String
    var endedAt: String?
    var centralState: String?
    var scanFound = false
    var connected = false
    var targetName: String?
    var peripheralIdentifier: String?
    var writeUUID: String
    var writeLen: Int
    var writeSha256_16: String
    var notifyState: [String: String] = [:]
    var wrote = false
    var events: [SarWriteEvent] = []
    var error: String?
    var notes: [String] = []
}

final class SarWriteProbe: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    private var central: CBCentralManager!
    private var target: CBPeripheral?
    private let targetSubstring: String
    private let writeUUID: String
    private let payload: Data
    private let listenSeconds: TimeInterval
    private let iso = ISO8601DateFormatter()
    private var result: SarWriteResult
    private var notifyChars: [CBCharacteristic] = []
    private var writeChar: CBCharacteristic?
    private var notifySettled = false

    init(targetSubstring: String, writeUUID: String, payload: Data, listenSeconds: TimeInterval) {
        self.targetSubstring = targetSubstring
        self.writeUUID = writeUUID.uppercased()
        self.payload = payload
        self.listenSeconds = listenSeconds
        let digest = SHA256.hash(data: payload).map { String(format: "%02x", $0) }.joined()
        self.result = SarWriteResult(startedAt: ISO8601DateFormatter().string(from: Date()), writeUUID: self.writeUUID, writeLen: payload.count, writeSha256_16: String(digest.prefix(16)))
        super.init()
        central = CBCentralManager(delegate: self, queue: nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + listenSeconds + 30) { self.finish("timeout") }
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        let s = stateString(central.state); result.centralState = s; fputs("central_state=\(s)\n", stderr)
        if central.state == .poweredOn { central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: true]) }
        else if [.unsupported, .unauthorized, .poweredOff].contains(central.state) { finish("central_\(s)") }
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String : Any], rssi RSSI: NSNumber) {
        let name = peripheral.name ?? (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? ""
        if name.localizedCaseInsensitiveContains(targetSubstring) {
            result.scanFound = true; result.targetName = name; result.peripheralIdentifier = peripheral.identifier.uuidString
            target = peripheral; peripheral.delegate = self; central.stopScan(); fputs("target_found=\(name) rssi=\(RSSI)\n", stderr); central.connect(peripheral, options: nil)
        }
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) { result.connected = true; fputs("connected\n", stderr); peripheral.discoverServices([CBUUID(string: "FE95")]) }
    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) { result.error = "connect_failed: \(error?.localizedDescription ?? "unknown")"; finish("connect_failed") }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let e = error { result.error = "services: \(e.localizedDescription)"; finish("service_error"); return }
        guard let service = peripheral.services?.first(where: { $0.uuid.uuidString.uppercased() == "FE95" }) else { result.error = "FE95_missing"; finish("fe95_missing"); return }
        peripheral.discoverCharacteristics([CBUUID(string: "005E"), CBUUID(string: "005F")], for: service)
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let e = error { result.error = "chars: \(e.localizedDescription)"; finish("char_error"); return }
        let chars = service.characteristics ?? []
        notifyChars = chars.filter { $0.properties.contains(.notify) }
        writeChar = chars.first(where: { $0.uuid.uuidString.uppercased() == writeUUID })
        guard let writeChar = writeChar else { result.error = "write_char_missing_\(writeUUID)"; finish("write_missing"); return }
        if !writeChar.properties.contains(.writeWithoutResponse) && !writeChar.properties.contains(.write) { result.error = "write_char_not_writable_\(writeUUID)"; finish("write_not_writable"); return }
        for ch in notifyChars { result.notifyState[ch.uuid.uuidString] = "set_requested"; peripheral.setNotifyValue(true, for: ch) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { self.writeOnce() }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        if let e = error { result.notifyState[characteristic.uuid.uuidString] = "error: \(e.localizedDescription)" }
        else { result.notifyState[characteristic.uuid.uuidString] = characteristic.isNotifying ? "notifying" : "not_notifying" }
        fputs("notify_state \(characteristic.uuid.uuidString)=\(result.notifyState[characteristic.uuid.uuidString] ?? "?")\n", stderr)
    }

    private func writeOnce() {
        guard !result.wrote, let peripheral = target, let ch = writeChar else { return }
        let type: CBCharacteristicWriteType = ch.properties.contains(.writeWithoutResponse) ? .withoutResponse : .withResponse
        peripheral.writeValue(payload, for: ch, type: type)
        result.wrote = true
        fputs("wrote uuid=\(ch.uuid.uuidString) len=\(payload.count) type=\(type == .withoutResponse ? "withoutResponse" : "withResponse")\n", stderr)
        DispatchQueue.main.asyncAfter(deadline: .now() + listenSeconds) { self.finish("listen_complete") }
    }

    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        if let e = error { result.notes.append("write_error \(characteristic.uuid.uuidString): \(e.localizedDescription)") }
        else { result.notes.append("write_ack \(characteristic.uuid.uuidString)") }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard error == nil, let data = characteristic.value else { return }
        let hex = Self.hex(data)
        result.events.append(SarWriteEvent(characteristic: characteristic.uuid.uuidString, length: data.count, sha256_16: String(Self.sha256(data).prefix(16)), hexPrefix: String(hex.prefix(32)), hex: hex))
    }

    private func finish(_ reason: String) {
        result.endedAt = iso.string(from: Date()); result.notes.append("finish_reason=\(reason)")
        if let p = target, central.state == .poweredOn { for ch in notifyChars { p.setNotifyValue(false, for: ch) }; central.cancelPeripheralConnection(p) }
        let enc = JSONEncoder(); enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        if let data = try? enc.encode(result) { FileHandle.standardOutput.write(data); FileHandle.standardOutput.write("\n".data(using: .utf8)!)} else { print("{}") }
        exit(result.error == nil ? 0 : 1)
    }
    private func stateString(_ state: CBManagerState) -> String { switch state { case .unknown: return "unknown"; case .resetting: return "resetting"; case .unsupported: return "unsupported"; case .unauthorized: return "unauthorized"; case .poweredOff: return "poweredOff"; case .poweredOn: return "poweredOn"; @unknown default: return "unknown_future" } }
    private static func hex(_ data: Data) -> String { data.map { String(format: "%02x", $0) }.joined() }
    private static func sha256(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
}

func parseArgs() -> (String, String, Data, TimeInterval) {
    let args = Array(CommandLine.arguments.dropFirst())
    if args.count < 2 {
        fputs("usage: ble_sar_write_probe <target-name-substring> <hex-payload> [listen-seconds] [write-uuid]\n", stderr)
        exit(64)
    }
    let target = args[0]
    let hex = args[1].filter { !$0.isWhitespace }
    guard hex.count % 2 == 0 else { fputs("hex payload must have even length\n", stderr); exit(64) }
    var bytes = Data(); var idx = hex.startIndex
    while idx < hex.endIndex { let next = hex.index(idx, offsetBy: 2); guard let byte = UInt8(hex[idx..<next], radix: 16) else { fputs("invalid hex payload\n", stderr); exit(64) }; bytes.append(byte); idx = next }
    let listen = args.count >= 3 ? (Double(args[2]) ?? 8.0) : 8.0
    let writeUUID = args.count >= 4 ? args[3] : "005F"
    return (target, writeUUID, bytes, listen)
}

let (target, writeUUID, payload, listen) = parseArgs()
let probe = SarWriteProbe(targetSubstring: target, writeUUID: writeUUID, payload: payload, listenSeconds: listen)
withExtendedLifetime(probe) { RunLoop.main.run() }
