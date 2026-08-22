import Foundation
import CoreBluetooth
import CryptoKit

struct SequenceWriteEvent: Codable { let characteristic: String; let length: Int; let sha256_16: String; let hexPrefix: String; let hex: String }
struct SequenceWriteRecord: Codable { let index: Int; let label: String; let characteristic: String; let length: Int; let sha256_16: String; let type: String }
struct PayloadItem { let label: String; let data: Data }
struct SequenceWriteResult: Codable {
    let startedAt: String
    var endedAt: String?
    var centralState: String?
    var scanFound = false
    var connected = false
    var targetName: String?
    var peripheralIdentifier: String?
    var writeUUID: String
    var notifyState: [String: String] = [:]
    var writes: [SequenceWriteRecord] = []
    var events: [SequenceWriteEvent] = []
    var error: String?
    var notes: [String] = []
}

final class SequenceWriteProbe: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    private var central: CBCentralManager!
    private var target: CBPeripheral?
    private let targetSubstring: String
    private let writeUUID: String
    private let payloads: [PayloadItem]
    private let listenSeconds: TimeInterval
    private let interWriteDelay: TimeInterval
    private let iso = ISO8601DateFormatter()
    private var result: SequenceWriteResult
    private var notifyChars: [CBCharacteristic] = []
    private var writeChar: CBCharacteristic?
    private var nextWriteIndex = 0

    init(targetSubstring: String, writeUUID: String, payloads: [PayloadItem], listenSeconds: TimeInterval, interWriteDelay: TimeInterval) {
        self.targetSubstring = targetSubstring
        self.writeUUID = writeUUID.uppercased()
        self.payloads = payloads
        self.listenSeconds = listenSeconds
        self.interWriteDelay = interWriteDelay
        self.result = SequenceWriteResult(startedAt: ISO8601DateFormatter().string(from: Date()), writeUUID: self.writeUUID)
        super.init()
        central = CBCentralManager(delegate: self, queue: nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + listenSeconds + interWriteDelay * Double(payloads.count) + 45) { self.finish("timeout") }
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
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { self.writeNext() }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        if let e = error { result.notifyState[characteristic.uuid.uuidString] = "error: \(e.localizedDescription)" }
        else { result.notifyState[characteristic.uuid.uuidString] = characteristic.isNotifying ? "notifying" : "not_notifying" }
        fputs("notify_state \(characteristic.uuid.uuidString)=\(result.notifyState[characteristic.uuid.uuidString] ?? "?")\n", stderr)
    }

    private func writeNext() {
        guard let peripheral = target, let ch = writeChar else { return }
        guard nextWriteIndex < payloads.count else {
            DispatchQueue.main.asyncAfter(deadline: .now() + listenSeconds) { self.finish("listen_complete") }
            return
        }
        let item = payloads[nextWriteIndex]
        let type: CBCharacteristicWriteType = ch.properties.contains(.writeWithoutResponse) ? .withoutResponse : .withResponse
        peripheral.writeValue(item.data, for: ch, type: type)
        let digest = SHA256.hash(data: item.data).map { String(format: "%02x", $0) }.joined()
        result.writes.append(SequenceWriteRecord(index: nextWriteIndex, label: item.label, characteristic: ch.uuid.uuidString, length: item.data.count, sha256_16: String(digest.prefix(16)), type: type == .withoutResponse ? "withoutResponse" : "withResponse"))
        fputs("wrote index=\(nextWriteIndex) label=\(item.label) uuid=\(ch.uuid.uuidString) len=\(item.data.count) type=\(type == .withoutResponse ? "withoutResponse" : "withResponse")\n", stderr)
        nextWriteIndex += 1
        DispatchQueue.main.asyncAfter(deadline: .now() + interWriteDelay) { self.writeNext() }
    }

    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        if let e = error { result.notes.append("write_error \(characteristic.uuid.uuidString): \(e.localizedDescription)") }
        else { result.notes.append("write_ack \(characteristic.uuid.uuidString)") }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard error == nil, let data = characteristic.value else { return }
        let hex = Self.hex(data)
        result.events.append(SequenceWriteEvent(characteristic: characteristic.uuid.uuidString, length: data.count, sha256_16: String(Self.sha256(data).prefix(16)), hexPrefix: String(hex.prefix(32)), hex: hex))
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

func decodeHex(_ hexInput: String) -> Data? {
    let hex = hexInput.filter { !$0.isWhitespace }
    guard hex.count % 2 == 0 else { return nil }
    var bytes = Data(); var idx = hex.startIndex
    while idx < hex.endIndex {
        let next = hex.index(idx, offsetBy: 2)
        guard let byte = UInt8(hex[idx..<next], radix: 16) else { return nil }
        bytes.append(byte); idx = next
    }
    return bytes
}

func loadPayloads(path: String) -> [PayloadItem] {
    guard let text = try? String(contentsOfFile: path, encoding: .utf8) else { fputs("cannot read payload file\n", stderr); exit(64) }
    var items: [PayloadItem] = []
    for rawLine in text.split(separator: "\n", omittingEmptySubsequences: false) {
        let noComment = rawLine.split(separator: "#", maxSplits: 1, omittingEmptySubsequences: false).first.map(String.init) ?? ""
        let line = noComment.trimmingCharacters(in: .whitespacesAndNewlines)
        if line.isEmpty { continue }
        let parts = line.split(separator: " ", maxSplits: 1, omittingEmptySubsequences: true)
        let label: String
        let hex: String
        if parts.count == 2 {
            label = String(parts[0])
            hex = String(parts[1])
        } else {
            label = "payload_\(items.count)"
            hex = line
        }
        guard let data = decodeHex(hex) else { fputs("invalid payload hex for \(label)\n", stderr); exit(64) }
        items.append(PayloadItem(label: label, data: data))
    }
    if items.isEmpty { fputs("payload file is empty\n", stderr); exit(64) }
    return items
}

func parseArgs() -> (String, String, [PayloadItem], TimeInterval, TimeInterval) {
    let args = Array(CommandLine.arguments.dropFirst())
    if args.count < 2 {
        fputs("usage: ble_sar_sequence_probe <target-name-substring> <payload-file> [listen-seconds] [write-uuid] [inter-write-delay]\n", stderr)
        exit(64)
    }
    let target = args[0]
    let payloads = loadPayloads(path: args[1])
    let listen = args.count >= 3 ? (Double(args[2]) ?? 8.0) : 8.0
    let writeUUID = args.count >= 4 ? args[3] : "005F"
    let delay = args.count >= 5 ? (Double(args[4]) ?? 1.2) : 1.2
    return (target, writeUUID, payloads, listen, delay)
}

let (target, writeUUID, payloads, listen, delay) = parseArgs()
let probe = SequenceWriteProbe(targetSubstring: target, writeUUID: writeUUID, payloads: payloads, listenSeconds: listen, interWriteDelay: delay)
withExtendedLifetime(probe) { RunLoop.main.run() }
