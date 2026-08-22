import Foundation
import CoreBluetooth

struct DeviceRecord: Codable {
    let firstSeen: String
    var lastSeen: String
    let identifier: String
    var name: String?
    var localName: String?
    var rssi: Int
    var serviceUUIDs: [String]
    var overflowServiceUUIDs: [String]
    var solicitedServiceUUIDs: [String]
    var manufacturerDataHex: String?
    var serviceData: [String: String]
    var txPowerLevel: Int?
    var connectable: Bool?
}

final class Scanner: NSObject, CBCentralManagerDelegate {
    private var central: CBCentralManager!
    private let duration: TimeInterval
    private var records: [String: DeviceRecord] = [:]
    private let iso: ISO8601DateFormatter = ISO8601DateFormatter()
    private var didStart = false

    init(duration: TimeInterval) {
        self.duration = duration
        super.init()
        self.central = CBCentralManager(delegate: self, queue: nil)
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        let state: String
        switch central.state {
        case .unknown: state = "unknown"
        case .resetting: state = "resetting"
        case .unsupported: state = "unsupported"
        case .unauthorized: state = "unauthorized"
        case .poweredOff: state = "poweredOff"
        case .poweredOn: state = "poweredOn"
        @unknown default: state = "unknown_future"
        }
        fputs("central_state=\(state)\n", stderr)
        guard central.state == .poweredOn else {
            if [.unsupported, .unauthorized, .poweredOff].contains(central.state) {
                finish(exitCode: 2)
            }
            return
        }
        if !didStart {
            didStart = true
            central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: true])
            DispatchQueue.main.asyncAfter(deadline: .now() + duration) { self.finish(exitCode: 0) }
        }
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String : Any], rssi RSSI: NSNumber) {
        let now = iso.string(from: Date())
        let key = peripheral.identifier.uuidString
        let serviceUUIDs = (advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] ?? []).map { $0.uuidString }.sorted()
        let overflow = (advertisementData[CBAdvertisementDataOverflowServiceUUIDsKey] as? [CBUUID] ?? []).map { $0.uuidString }.sorted()
        let solicited = (advertisementData[CBAdvertisementDataSolicitedServiceUUIDsKey] as? [CBUUID] ?? []).map { $0.uuidString }.sorted()
        let localName = advertisementData[CBAdvertisementDataLocalNameKey] as? String
        let mfg = (advertisementData[CBAdvertisementDataManufacturerDataKey] as? Data).map { Self.hex($0) }
        var serviceData: [String: String] = [:]
        if let sd = advertisementData[CBAdvertisementDataServiceDataKey] as? [CBUUID: Data] {
            for (uuid, data) in sd { serviceData[uuid.uuidString] = Self.hex(data) }
        }
        let tx = advertisementData[CBAdvertisementDataTxPowerLevelKey] as? Int
        let connectable = advertisementData[CBAdvertisementDataIsConnectable] as? Bool
        if var existing = records[key] {
            existing.lastSeen = now
            existing.name = peripheral.name ?? existing.name
            existing.localName = localName ?? existing.localName
            existing.rssi = RSSI.intValue
            existing.serviceUUIDs = Array(Set(existing.serviceUUIDs + serviceUUIDs)).sorted()
            existing.overflowServiceUUIDs = Array(Set(existing.overflowServiceUUIDs + overflow)).sorted()
            existing.solicitedServiceUUIDs = Array(Set(existing.solicitedServiceUUIDs + solicited)).sorted()
            existing.manufacturerDataHex = mfg ?? existing.manufacturerDataHex
            existing.serviceData.merge(serviceData) { _, new in new }
            existing.txPowerLevel = tx ?? existing.txPowerLevel
            existing.connectable = connectable ?? existing.connectable
            records[key] = existing
        } else {
            records[key] = DeviceRecord(firstSeen: now, lastSeen: now, identifier: key, name: peripheral.name, localName: localName, rssi: RSSI.intValue, serviceUUIDs: serviceUUIDs, overflowServiceUUIDs: overflow, solicitedServiceUUIDs: solicited, manufacturerDataHex: mfg, serviceData: serviceData, txPowerLevel: tx, connectable: connectable)
        }
    }

    private func finish(exitCode: Int32) {
        central.stopScan()
        let out = records.values.sorted { (a, b) in
            if a.rssi != b.rssi { return a.rssi > b.rssi }
            return (a.localName ?? a.name ?? a.identifier) < (b.localName ?? b.name ?? b.identifier)
        }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        if let data = try? encoder.encode(out) {
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write("\n".data(using: .utf8)!)
        } else {
            print("[]")
        }
        exit(exitCode)
    }

    private static func hex(_ data: Data) -> String {
        data.map { String(format: "%02x", $0) }.joined()
    }
}

let duration = CommandLine.arguments.dropFirst().first.flatMap(Double.init) ?? 12.0
let scanner = Scanner(duration: duration)
withExtendedLifetime(scanner) {
    RunLoop.main.run()
}
