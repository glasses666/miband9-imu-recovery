import Foundation
import CoreBluetooth

struct CharRecord: Codable {
    let uuid: String
    let properties: [String]
    let descriptors: [String]?
}
struct ServiceRecord: Codable {
    let uuid: String
    let isPrimary: Bool
    var characteristics: [CharRecord]
}
struct ProbeResult: Codable {
    let startedAt: String
    var endedAt: String?
    let targetNameSubstring: String
    var centralState: String?
    var scanFound: Bool = false
    var peripheralIdentifier: String?
    var peripheralName: String?
    var localName: String?
    var lastRSSI: Int?
    var connected: Bool = false
    var disconnected: Bool = false
    var error: String?
    var services: [ServiceRecord] = []
    var notes: [String] = []
}

final class Probe: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    private var central: CBCentralManager!
    private var target: CBPeripheral?
    private let targetSubstring: String
    private let timeout: TimeInterval
    private var result: ProbeResult
    private let iso = ISO8601DateFormatter()
    private var serviceIndex: Int = 0

    init(targetSubstring: String, timeout: TimeInterval) {
        self.targetSubstring = targetSubstring
        self.timeout = timeout
        self.result = ProbeResult(startedAt: ISO8601DateFormatter().string(from: Date()), targetNameSubstring: targetSubstring)
        super.init()
        self.central = CBCentralManager(delegate: self, queue: nil)
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
        central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: true])
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String : Any], rssi RSSI: NSNumber) {
        let name = peripheral.name ?? (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? ""
        if name.localizedCaseInsensitiveContains(targetSubstring) {
            result.scanFound = true
            result.peripheralIdentifier = peripheral.identifier.uuidString
            result.peripheralName = peripheral.name
            result.localName = advertisementData[CBAdvertisementDataLocalNameKey] as? String
            result.lastRSSI = RSSI.intValue
            target = peripheral
            peripheral.delegate = self
            central.stopScan()
            fputs("target_found=\(name) rssi=\(RSSI) id=\(peripheral.identifier.uuidString)\n", stderr)
            central.connect(peripheral, options: nil)
        }
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        result.connected = true
        fputs("connected=\(peripheral.identifier.uuidString)\n", stderr)
        peripheral.discoverServices(nil)
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        result.error = "didFailToConnect: \(error?.localizedDescription ?? "unknown")"
        finish("connect_failed")
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        result.disconnected = true
        if let e = error { result.notes.append("disconnect_error: \(e.localizedDescription)") }
        if result.services.isEmpty { finish("disconnected_before_services") }
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let e = error {
            result.error = "didDiscoverServices: \(e.localizedDescription)"
            finish("service_discovery_failed")
            return
        }
        let services = peripheral.services ?? []
        result.services = services.map { ServiceRecord(uuid: $0.uuid.uuidString, isPrimary: $0.isPrimary, characteristics: []) }
        if services.isEmpty { finish("no_services") ; return }
        serviceIndex = 0
        discoverNextService(peripheral)
    }

    private func discoverNextService(_ peripheral: CBPeripheral) {
        guard let services = peripheral.services, serviceIndex < services.count else { finish("services_discovered") ; return }
        peripheral.discoverCharacteristics(nil, for: services[serviceIndex])
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let e = error { result.notes.append("char_discovery_error \(service.uuid.uuidString): \(e.localizedDescription)") }
        let chars = (service.characteristics ?? []).map { ch in
            CharRecord(uuid: ch.uuid.uuidString, properties: props(ch.properties), descriptors: nil)
        }
        if let idx = result.services.firstIndex(where: { $0.uuid == service.uuid.uuidString }) {
            result.services[idx].characteristics = chars
        }
        serviceIndex += 1
        discoverNextService(peripheral)
    }

    private func finish(_ reason: String) {
        result.endedAt = iso.string(from: Date())
        result.notes.append("finish_reason=\(reason)")
        if let p = target, central.state == .poweredOn {
            central.cancelPeripheralConnection(p)
        }
        let enc = JSONEncoder(); enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        if let data = try? enc.encode(result) { FileHandle.standardOutput.write(data); FileHandle.standardOutput.write("\n".data(using: .utf8)!) }
        else { print("{}") }
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
        if p.contains(.broadcast) { out.append("broadcast") }
        if p.contains(.read) { out.append("read") }
        if p.contains(.writeWithoutResponse) { out.append("writeWithoutResponse") }
        if p.contains(.write) { out.append("write") }
        if p.contains(.notify) { out.append("notify") }
        if p.contains(.indicate) { out.append("indicate") }
        if p.contains(.authenticatedSignedWrites) { out.append("authenticatedSignedWrites") }
        if p.contains(.extendedProperties) { out.append("extendedProperties") }
        if p.contains(.notifyEncryptionRequired) { out.append("notifyEncryptionRequired") }
        if p.contains(.indicateEncryptionRequired) { out.append("indicateEncryptionRequired") }
        return out
    }
}

let target = CommandLine.arguments.dropFirst().first ?? "Xiaomi Smart Band 9"
let timeout = CommandLine.arguments.dropFirst().dropFirst().first.flatMap(Double.init) ?? 25.0
let probe = Probe(targetSubstring: target, timeout: timeout)
withExtendedLifetime(probe) { RunLoop.main.run() }
