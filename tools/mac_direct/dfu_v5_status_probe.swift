import Foundation
import CoreBluetooth
import CryptoKit

struct DfuEvent: Codable {
    let characteristic: String
    let length: Int
    let hex: String
    let sha256_16: String
    let receivedAt: String
}

struct DfuWrite: Codable {
    let label: String
    let characteristic: String
    let length: Int
    let hex: String
    let writeType: String
}

struct DfuStatus: Codable {
    let commandOk: Bool
    let code: Int
    let codeName: String
    let upgradeStatusRaw: Int?
    let upgradeStatusName: String?
    let firmwareType: Int?
    let firmwareSize: UInt32?
    let firmwareUpgradedSize: UInt32?
    let rawResponseHex: String
}

struct ProbeResult: Codable {
    let startedAt: String
    var endedAt: String?
    var centralState: String?
    var scanFound: Bool = false
    var retrieveConnectedFound: Bool = false
    var connected: Bool = false
    var targetName: String?
    var peripheralIdentifier: String?
    var serviceUUID: String = DfuV5StatusProbe.dfuServiceUUID.uuidString
    var cptUUID: String = DfuV5StatusProbe.cptUUID.uuidString
    var pktUUID: String = DfuV5StatusProbe.pktUUID.uuidString
    var cptProperties: [String] = []
    var pktProperties: [String] = []
    var notifyState: [String: String] = [:]
    var writes: [DfuWrite] = []
    var events: [DfuEvent] = []
    var parsedStatus: DfuStatus?
    var error: String?
    var notes: [String] = []
}

final class DfuV5StatusProbe: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    // Mi Fitness NewDfuProfile: v4v.C(5424/5425/5426)
    // v4v.C(0x1530) expands against base 00000000-0000-3512-2118-0009af100700.
    static let dfuServiceUUID = CBUUID(string: "00000000-1530-3512-2118-0009AF100700")
    static let cptUUID = CBUUID(string: "00000000-1531-3512-2118-0009AF100700")
    static let pktUUID = CBUUID(string: "00000000-1532-3512-2118-0009AF100700")
    static let fe95UUID = CBUUID(string: "FE95")

    private var central: CBCentralManager!
    private var target: CBPeripheral?
    private var cpt: CBCharacteristic?
    private let targetSubstring: String
    private let timeout: TimeInterval
    private let knownPeripheralID: UUID?
    private let iso = ISO8601DateFormatter()
    private var result = ProbeResult(startedAt: ISO8601DateFormatter().string(from: Date()))
    private var wroteStatusQuery = false
    private var finished = false

    init(targetSubstring: String, timeout: TimeInterval, knownPeripheralID: UUID?) {
        self.targetSubstring = targetSubstring
        self.timeout = timeout
        self.knownPeripheralID = knownPeripheralID
        super.init()
        central = CBCentralManager(delegate: self, queue: nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + timeout) { self.finish("timeout") }
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        let s = stateString(central.state)
        result.centralState = s
        fputs("central_state=\(s)\n", stderr)
        guard central.state == .poweredOn else {
            if [.unsupported, .unauthorized, .poweredOff].contains(central.state) { finish("central_\(s)") }
            return
        }

        if let knownPeripheralID = knownPeripheralID {
            let known = central.retrievePeripherals(withIdentifiers: [knownPeripheralID])
            result.notes.append("retrieve_by_identifier_count=\(known.count)")
            if let p = known.first {
                connect(p, source: "retrievePeripheralsByIdentifier")
                return
            }
        }

        var candidates: [CBPeripheral] = []
        let dfuConnected = central.retrieveConnectedPeripherals(withServices: [Self.dfuServiceUUID])
        let fe95Connected = central.retrieveConnectedPeripherals(withServices: [Self.fe95UUID])
        candidates.append(contentsOf: dfuConnected)
        for p in fe95Connected where !candidates.contains(where: { $0.identifier == p.identifier }) { candidates.append(p) }
        result.notes.append("retrieve_connected_dfu_count=\(dfuConnected.count)")
        result.notes.append("retrieve_connected_fe95_count=\(fe95Connected.count)")

        if let p = candidates.first(where: { ($0.name ?? "").localizedCaseInsensitiveContains(targetSubstring) }) ?? candidates.first {
            result.retrieveConnectedFound = true
            connect(p, source: "retrieveConnected")
            return
        }

        central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: true])
        result.notes.append("scan_started_nil_services")
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String: Any], rssi RSSI: NSNumber) {
        let name = peripheral.name ?? (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? ""
        if name.localizedCaseInsensitiveContains(targetSubstring) {
            result.scanFound = true
            connect(peripheral, source: "scan", advertisedName: name)
        }
    }

    private func connect(_ peripheral: CBPeripheral, source: String, advertisedName: String? = nil) {
        central.stopScan()
        target = peripheral
        peripheral.delegate = self
        result.targetName = advertisedName ?? peripheral.name
        result.peripheralIdentifier = peripheral.identifier.uuidString
        result.notes.append("connect_source=\(source)")
        fputs("target=\(result.targetName ?? "unknown") source=\(source)\n", stderr)
        central.connect(peripheral, options: nil)
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        result.connected = true
        fputs("connected\n", stderr)
        peripheral.discoverServices([Self.dfuServiceUUID])
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        result.error = "connect_failed: \(error?.localizedDescription ?? "unknown")"
        finish("connect_failed")
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let e = error {
            result.error = "discover_services: \(e.localizedDescription)"
            finish("service_error")
            return
        }
        guard let service = peripheral.services?.first(where: { $0.uuid == Self.dfuServiceUUID }) else {
            result.error = "dfu_v5_service_not_found"
            finish("dfu_service_missing")
            return
        }
        peripheral.discoverCharacteristics([Self.cptUUID, Self.pktUUID], for: service)
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let e = error {
            result.error = "discover_characteristics: \(e.localizedDescription)"
            finish("characteristic_error")
            return
        }
        for ch in service.characteristics ?? [] {
            if ch.uuid == Self.cptUUID {
                cpt = ch
                result.cptProperties = props(ch.properties)
            } else if ch.uuid == Self.pktUUID {
                result.pktProperties = props(ch.properties)
            }
        }
        guard let cpt = cpt else {
            result.error = "dfu_cpt_characteristic_missing"
            finish("cpt_missing")
            return
        }
        guard cpt.properties.contains(.notify) || cpt.properties.contains(.indicate) else {
            result.error = "dfu_cpt_no_notify_or_indicate"
            finish("cpt_notify_missing")
            return
        }
        result.notifyState[cpt.uuid.uuidString] = "enabling"
        peripheral.setNotifyValue(true, for: cpt)
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        if let e = error {
            result.notifyState[characteristic.uuid.uuidString] = "error: \(e.localizedDescription)"
            result.error = "notify_enable_failed: \(e.localizedDescription)"
            finish("notify_failed")
            return
        }
        result.notifyState[characteristic.uuid.uuidString] = characteristic.isNotifying ? "notifying" : "not_notifying"
        if characteristic.uuid == Self.cptUUID && characteristic.isNotifying && !wroteStatusQuery {
            writeStatusQuery(peripheral, characteristic)
        }
    }

    private func writeStatusQuery(_ peripheral: CBPeripheral, _ characteristic: CBCharacteristic) {
        let payload = Data([0xD1]) // Mi Fitness NewDfuProfile.queryUpgradeStatus only.
        let writeType: CBCharacteristicWriteType
        if characteristic.properties.contains(.write) {
            writeType = .withResponse
        } else if characteristic.properties.contains(.writeWithoutResponse) {
            writeType = .withoutResponse
        } else {
            result.error = "dfu_cpt_not_writable"
            finish("cpt_not_writable")
            return
        }
        wroteStatusQuery = true
        result.writes.append(DfuWrite(label: "query_upgrade_status_D1", characteristic: characteristic.uuid.uuidString, length: payload.count, hex: hex(payload), writeType: writeType == .withResponse ? "withResponse" : "withoutResponse"))
        fputs("write query_upgrade_status_D1 type=\(writeType == .withResponse ? "withResponse" : "withoutResponse")\n", stderr)
        peripheral.writeValue(payload, for: characteristic, type: writeType)
        if writeType == .withoutResponse {
            DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) { if self.result.parsedStatus == nil { self.finish("status_wait_complete") } }
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        if let e = error {
            result.error = "write_status_query_failed: \(e.localizedDescription)"
            finish("write_failed")
            return
        }
        result.notes.append("write_complete=\(characteristic.uuid.uuidString)")
        DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) { if self.result.parsedStatus == nil { self.finish("status_wait_complete") } }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        if let e = error {
            result.error = "notify_value_error: \(e.localizedDescription)"
            finish("notify_value_error")
            return
        }
        guard let data = characteristic.value else { return }
        let hx = hex(data)
        result.events.append(DfuEvent(characteristic: characteristic.uuid.uuidString, length: data.count, hex: hx, sha256_16: String(sha256(data).prefix(16)), receivedAt: iso.string(from: Date())))
        if characteristic.uuid == Self.cptUUID, let parsed = parseStatusResponse(data) {
            result.parsedStatus = parsed
            finish("status_response_parsed")
        }
    }

    private func parseStatusResponse(_ data: Data) -> DfuStatus? {
        let b = [UInt8](data)
        guard b.count >= 3, b[0] == 0x10, b[1] == 0xD1 else { return nil }
        let code = Int(b[2])
        let payload = Array(b.dropFirst(3))
        let statusRaw = payload.count >= 1 ? Int(payload[0]) : nil
        let firmwareType = payload.count >= 2 ? Int(payload[1]) : nil
        let size = payload.count >= 6 ? UInt32(payload[2]) | (UInt32(payload[3]) << 8) | (UInt32(payload[4]) << 16) | (UInt32(payload[5]) << 24) : nil
        let upgraded = payload.count >= 10 ? UInt32(payload[6]) | (UInt32(payload[7]) << 8) | (UInt32(payload[8]) << 16) | (UInt32(payload[9]) << 24) : nil
        return DfuStatus(
            commandOk: code == 1,
            code: code,
            codeName: codeName(code),
            upgradeStatusRaw: statusRaw,
            upgradeStatusName: statusRaw.flatMap(upgradeStatusName),
            firmwareType: firmwareType,
            firmwareSize: size,
            firmwareUpgradedSize: upgraded,
            rawResponseHex: hex(data)
        )
    }

    private func finish(_ reason: String) {
        if finished { return }
        finished = true
        result.endedAt = iso.string(from: Date())
        result.notes.append("finish_reason=\(reason)")
        if let p = target, central.state == .poweredOn { central.cancelPeripheralConnection(p) }
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        if let data = try? enc.encode(result) {
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write("\n".data(using: .utf8)!)
        } else {
            print("{}")
        }
        exit(result.error == nil ? 0 : 1)
    }

    private func stateString(_ state: CBManagerState) -> String {
        switch state {
        case .unknown: return "unknown"
        case .resetting: return "resetting"
        case .unsupported: return "unsupported"
        case .unauthorized: return "unauthorized"
        case .poweredOff: return "poweredOff"
        case .poweredOn: return "poweredOn"
        @unknown default: return "unknown_future"
        }
    }

    private func props(_ p: CBCharacteristicProperties) -> [String] {
        var out: [String] = []
        if p.contains(.read) { out.append("read") }
        if p.contains(.writeWithoutResponse) { out.append("writeWithoutResponse") }
        if p.contains(.write) { out.append("write") }
        if p.contains(.notify) { out.append("notify") }
        if p.contains(.indicate) { out.append("indicate") }
        if p.contains(.notifyEncryptionRequired) { out.append("notifyEncryptionRequired") }
        return out
    }

    private func codeName(_ code: Int) -> String {
        switch code {
        case 0: return "RESERVED"
        case 1: return "SUCCESS"
        case 2: return "INVALID_STATE"
        case 3: return "UNKNOWN_COMMAND"
        case 4: return "OPERATION_FAILED"
        case 15: return "SPACE_INSUFFICIENT"
        case 16: return "DIAL_ID_UNDEFINED"
        case 17: return "DIAL_BUILT_IN"
        default: return "UNKNOWN_\(code)"
        }
    }

    private func upgradeStatusName(_ value: Int) -> String {
        switch value {
        case 0: return "IDLE"
        case 1: return "WAITING_TRANSFER"
        case 2: return "IN_TRANSFER"
        case 3: return "VALIDATING"
        case 4: return "WAITING_UPGRADE"
        case 5: return "IN_UPGRADING"
        case 6: return "BUSY"
        case 7: return "WAITING_NEXT_FIRMWARE"
        case 255: return "DFU_RUNNING"
        default: return "UNKNOWN_\(value)"
        }
    }

    private func hex(_ data: Data) -> String { data.map { String(format: "%02x", $0) }.joined() }
    private func sha256(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
}

let args = Array(CommandLine.arguments.dropFirst())
let target = args.count >= 1 ? args[0] : "Xiaomi Smart Band 9"
let timeout = args.count >= 2 ? (Double(args[1]) ?? 35.0) : 35.0
let knownID = args.count >= 3 ? UUID(uuidString: args[2]) : nil
let probe = DfuV5StatusProbe(targetSubstring: target, timeout: timeout, knownPeripheralID: knownID)
withExtendedLifetime(probe) { RunLoop.main.run() }
