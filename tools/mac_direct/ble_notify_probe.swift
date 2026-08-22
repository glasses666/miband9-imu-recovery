import Foundation
import CoreBluetooth
import CryptoKit

struct NotifyEvent: Codable { let characteristic: String; let length: Int; let sha256_16: String; let hexPrefix: String; let hex: String }
struct NotifyProbeResult: Codable {
    let startedAt: String
    var endedAt: String?
    var centralState: String?
    var scanFound = false
    var connected = false
    var targetName: String?
    var peripheralIdentifier: String?
    var notifyState: [String: String] = [:]
    var events: [NotifyEvent] = []
    var error: String?
    var notes: [String] = []
}
final class NotifyProbe: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    private var central: CBCentralManager!
    private var target: CBPeripheral?
    private let targetSubstring: String
    private let listenSeconds: TimeInterval
    private let iso = ISO8601DateFormatter()
    private var result = NotifyProbeResult(startedAt: ISO8601DateFormatter().string(from: Date()))
    private var fe95: CBService?
    private var notifyChars: [CBCharacteristic] = []
    init(targetSubstring: String, listenSeconds: TimeInterval) { self.targetSubstring=targetSubstring; self.listenSeconds=listenSeconds; super.init(); central=CBCentralManager(delegate:self, queue:nil); DispatchQueue.main.asyncAfter(deadline:.now()+listenSeconds+25){ self.finish("timeout") } }
    func centralManagerDidUpdateState(_ central: CBCentralManager) { let s=stateString(central.state); result.centralState=s; fputs("central_state=\(s)\n",stderr); if central.state == .poweredOn { central.scanForPeripherals(withServices:nil, options:[CBCentralManagerScanOptionAllowDuplicatesKey:true]) } else if [.unsupported,.unauthorized,.poweredOff].contains(central.state){ finish("central_\(s)") } }
    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData:[String:Any], rssi RSSI:NSNumber){ let name=peripheral.name ?? (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? ""; if name.localizedCaseInsensitiveContains(targetSubstring){ result.scanFound=true; result.targetName=name; result.peripheralIdentifier=peripheral.identifier.uuidString; target=peripheral; peripheral.delegate=self; central.stopScan(); fputs("target_found=\(name)\n",stderr); central.connect(peripheral, options:nil) } }
    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral){ result.connected=true; fputs("connected\n",stderr); peripheral.discoverServices([CBUUID(string:"FE95")]) }
    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?){ result.error="connect_failed: \(error?.localizedDescription ?? "unknown")"; finish("connect_failed") }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?){ if let e=error{ result.error="services: \(e.localizedDescription)"; finish("service_error"); return }; fe95=peripheral.services?.first(where:{$0.uuid.uuidString.uppercased()=="FE95"}); guard let s=fe95 else { result.error="FE95_missing"; finish("fe95_missing"); return }; peripheral.discoverCharacteristics([CBUUID(string:"005E"), CBUUID(string:"005F")], for:s) }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?){ if let e=error{ result.error="chars: \(e.localizedDescription)"; finish("char_error"); return }; notifyChars=(service.characteristics ?? []).filter{$0.properties.contains(.notify)}; for ch in notifyChars{ result.notifyState[ch.uuid.uuidString]="set_requested"; peripheral.setNotifyValue(true, for: ch) }; DispatchQueue.main.asyncAfter(deadline:.now()+listenSeconds){ self.finish("listen_complete") } }
    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?){ if let e=error{ result.notifyState[characteristic.uuid.uuidString]="error: \(e.localizedDescription)" } else { result.notifyState[characteristic.uuid.uuidString]=characteristic.isNotifying ? "notifying" : "not_notifying" }; fputs("notify_state \(characteristic.uuid.uuidString)=\(result.notifyState[characteristic.uuid.uuidString] ?? "?")\n",stderr) }
    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?){ guard error == nil, let data=characteristic.value else { return }; let hex=Self.hex(data); result.events.append(NotifyEvent(characteristic: characteristic.uuid.uuidString, length: data.count, sha256_16: String(Self.sha256(data).prefix(16)), hexPrefix: String(hex.prefix(32)), hex: hex)) }
    private func finish(_ reason:String){ result.endedAt=iso.string(from:Date()); result.notes.append("finish_reason=\(reason)"); if let p=target, central.state == .poweredOn { for ch in notifyChars { p.setNotifyValue(false, for: ch) }; central.cancelPeripheralConnection(p) }; let enc=JSONEncoder(); enc.outputFormatting=[.prettyPrinted,.sortedKeys]; if let data=try? enc.encode(result){ FileHandle.standardOutput.write(data); FileHandle.standardOutput.write("\n".data(using:.utf8)!)} else {print("{}")}; exit(result.error == nil ? 0:1) }
    private func stateString(_ state: CBManagerState)->String{ switch state{ case .unknown:return"unknown"; case .resetting:return"resetting"; case .unsupported:return"unsupported"; case .unauthorized:return"unauthorized"; case .poweredOff:return"poweredOff"; case .poweredOn:return"poweredOn"; @unknown default:return"unknown_future" } }
    private static func hex(_ data: Data)->String { data.map{String(format:"%02x",$0)}.joined() }
    private static func sha256(_ data: Data)->String { SHA256.hash(data:data).map{String(format:"%02x",$0)}.joined() }
}
let target=CommandLine.arguments.dropFirst().first ?? "Xiaomi Smart Band 9"
let listen=CommandLine.arguments.dropFirst().dropFirst().first.flatMap(Double.init) ?? 8.0
let probe=NotifyProbe(targetSubstring: target, listenSeconds: listen)
withExtendedLifetime(probe){ RunLoop.main.run() }
