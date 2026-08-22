import Foundation
import CoreBluetooth
import CryptoKit

struct ReadRecord: Codable {
    let service: String
    let characteristic: String
    let properties: [String]
    var status: String
    var length: Int?
    var sha256_16: String?
    var hex: String?
    var error: String?
}
struct ReadProbeResult: Codable {
    let startedAt: String
    var endedAt: String?
    var centralState: String?
    var scanFound: Bool = false
    var connected: Bool = false
    var targetName: String?
    var peripheralIdentifier: String?
    var error: String?
    var reads: [ReadRecord] = []
    var notes: [String] = []
}

final class ReadProbe: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    private var central: CBCentralManager!
    private var target: CBPeripheral?
    private let targetSubstring: String
    private let timeout: TimeInterval
    private let iso = ISO8601DateFormatter()
    private var result = ReadProbeResult(startedAt: ISO8601DateFormatter().string(from: Date()))
    private var pending: [(CBService, CBCharacteristic)] = []
    private var current: (CBService, CBCharacteristic)?
    private var serviceIndex = 0

    init(targetSubstring: String, timeout: TimeInterval) {
        self.targetSubstring = targetSubstring
        self.timeout = timeout
        super.init()
        central = CBCentralManager(delegate: self, queue: nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + timeout) { self.finish("timeout") }
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        let s = stateString(central.state); result.centralState = s; fputs("central_state=\(s)\n", stderr)
        guard central.state == .poweredOn else { if [.unsupported,.unauthorized,.poweredOff].contains(central.state) { finish("central_\(s)") }; return }
        central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: true])
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String : Any], rssi RSSI: NSNumber) {
        let name = peripheral.name ?? (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? ""
        if name.localizedCaseInsensitiveContains(targetSubstring) {
            result.scanFound = true; result.targetName = name; result.peripheralIdentifier = peripheral.identifier.uuidString
            target = peripheral; peripheral.delegate = self; central.stopScan(); fputs("target_found=\(name)\n", stderr); central.connect(peripheral, options: nil)
        }
    }
    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) { result.connected = true; fputs("connected\n", stderr); peripheral.discoverServices(nil) }
    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) { result.error = "connect_failed: \(error?.localizedDescription ?? "unknown")"; finish("connect_failed") }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let e=error { result.error="discover_services: \(e.localizedDescription)"; finish("service_error"); return }
        serviceIndex = 0; discoverNext(peripheral)
    }
    private func discoverNext(_ p: CBPeripheral) {
        guard let services=p.services, serviceIndex < services.count else { buildPending(p); readNext(p); return }
        p.discoverCharacteristics(nil, for: services[serviceIndex])
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let e=error { result.notes.append("char_error \(service.uuid.uuidString): \(e.localizedDescription)") }
        serviceIndex += 1; discoverNext(peripheral)
    }
    private func buildPending(_ p: CBPeripheral) {
        for s in p.services ?? [] {
            for c in s.characteristics ?? [] where c.properties.contains(.read) {
                pending.append((s,c))
                result.reads.append(ReadRecord(service: s.uuid.uuidString, characteristic: c.uuid.uuidString, properties: props(c.properties), status: "pending", length: nil, sha256_16: nil, hex: nil, error: nil))
            }
        }
        fputs("readable_count=\(pending.count)\n", stderr)
    }
    private func readNext(_ p: CBPeripheral) {
        if pending.isEmpty { finish("reads_complete"); return }
        current = pending.removeFirst()
        p.readValue(for: current!.1)
    }
    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard let cur=current else { readNext(peripheral); return }
        let serviceUUID=cur.0.uuid.uuidString, charUUID=cur.1.uuid.uuidString
        if let idx=result.reads.firstIndex(where: {$0.service==serviceUUID && $0.characteristic==charUUID && $0.status=="pending"}) {
            if let e=error {
                result.reads[idx].status="error"; result.reads[idx].error=e.localizedDescription
            } else if let data=characteristic.value {
                result.reads[idx].status="ok"; result.reads[idx].length=data.count; result.reads[idx].sha256_16=String(Self.sha256(data).prefix(16)); result.reads[idx].hex=Self.hex(data)
            } else {
                result.reads[idx].status="nil"
            }
        }
        current=nil; readNext(peripheral)
    }
    private func finish(_ reason: String) {
        result.endedAt=iso.string(from: Date()); result.notes.append("finish_reason=\(reason)")
        if let p=target, central.state == .poweredOn { central.cancelPeripheralConnection(p) }
        let enc=JSONEncoder(); enc.outputFormatting=[.prettyPrinted,.sortedKeys]
        if let data=try? enc.encode(result) { FileHandle.standardOutput.write(data); FileHandle.standardOutput.write("\n".data(using:.utf8)!)} else { print("{}") }
        exit(result.error == nil ? 0 : 1)
    }
    private func stateString(_ state: CBManagerState) -> String { switch state { case .unknown: return "unknown"; case .resetting: return "resetting"; case .unsupported: return "unsupported"; case .unauthorized: return "unauthorized"; case .poweredOff: return "poweredOff"; case .poweredOn: return "poweredOn"; @unknown default: return "unknown_future" } }
    private func props(_ p: CBCharacteristicProperties) -> [String] { var out:[String]=[]; if p.contains(.read){out.append("read")}; if p.contains(.writeWithoutResponse){out.append("writeWithoutResponse")}; if p.contains(.write){out.append("write")}; if p.contains(.notify){out.append("notify")}; if p.contains(.indicate){out.append("indicate")}; if p.contains(.notifyEncryptionRequired){out.append("notifyEncryptionRequired")}; return out }
    private static func hex(_ data: Data)->String { data.map{String(format:"%02x",$0)}.joined() }
    private static func sha256(_ data: Data)->String { SHA256.hash(data:data).map{String(format:"%02x",$0)}.joined() }
}
let target=CommandLine.arguments.dropFirst().first ?? "Xiaomi Smart Band 9"
let timeout=CommandLine.arguments.dropFirst().dropFirst().first.flatMap(Double.init) ?? 35.0
let probe=ReadProbe(targetSubstring: target, timeout: timeout)
withExtendedLifetime(probe) { RunLoop.main.run() }
