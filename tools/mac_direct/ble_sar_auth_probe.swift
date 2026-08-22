import Foundation
import CoreBluetooth
import CryptoKit

struct AuthWriteEvent: Codable { let characteristic: String; let length: Int; let sha256_16: String; let hexPrefix: String; let hex: String }
struct AuthWriteRecord: Codable { let index: Int; let label: String; let characteristic: String; let length: Int; let sha256_16: String; let type: String }
struct AuthPayloadItem { let label: String; let data: Data }
struct AuthProbeResult: Codable {
    let startedAt: String
    var endedAt: String?
    var centralState: String?
    var scanFound = false
    var connected = false
    var targetName: String?
    var peripheralIdentifier: String?
    var writeUUID: String
    var notifyState: [String: String] = [:]
    var writes: [AuthWriteRecord] = []
    var events: [AuthWriteEvent] = []
    var helperInvoked = false
    var authStep3Queued = false
    var error: String?
    var notes: [String] = []
}

final class AuthProbe: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    private var central: CBCentralManager!
    private var target: CBPeripheral?
    private let targetSubstring: String
    private let writeUUID: String
    private let initialPayloads: [AuthPayloadItem]
    private let listenSeconds: TimeInterval
    private let interWriteDelay: TimeInterval
    private let outDir: String
    private let authTar: String
    private let pythonPath: String
    private let helperPath: String
    private let postAuthActions: String
    private let knownPeripheralIdentifier: UUID?
    private let iso = ISO8601DateFormatter()
    private var result: AuthProbeResult
    private var notifyChars: [CBCharacteristic] = []
    private var writeChar: CBCharacteristic?
    private var nextWriteIndex = 0
    private var extraWriteIndex = 100
    private var tryingHelper = false
    private var rxBuffer = Data()
    private var ackedDataSequences = Set<Int>()
    private var pendingEncryptedSanityFrame: Data?
    private var encryptedSanityQueued = false
    private var pendingPostAuthFrames: [(label: String, data: Data)] = []
    private var postAuthFramesQueued = false

    init(targetSubstring: String, writeUUID: String, initialPayloads: [AuthPayloadItem], authTar: String, outDir: String, listenSeconds: TimeInterval, interWriteDelay: TimeInterval, pythonPath: String, helperPath: String, postAuthActions: String, knownPeripheralIdentifier: UUID?) {
        self.targetSubstring = targetSubstring
        self.writeUUID = writeUUID.uppercased()
        self.initialPayloads = initialPayloads
        self.authTar = authTar
        self.outDir = outDir
        self.listenSeconds = listenSeconds
        self.interWriteDelay = interWriteDelay
        self.pythonPath = pythonPath
        self.helperPath = helperPath
        self.postAuthActions = postAuthActions
        self.knownPeripheralIdentifier = knownPeripheralIdentifier
        self.result = AuthProbeResult(startedAt: ISO8601DateFormatter().string(from: Date()), writeUUID: self.writeUUID)
        super.init()
        central = CBCentralManager(delegate: self, queue: nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + listenSeconds + interWriteDelay * Double(initialPayloads.count) + 60) { self.finish("timeout") }
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        let s = stateString(central.state); result.centralState = s; fputs("central_state=\(s)\n", stderr)
        if central.state == .poweredOn {
            if let known = knownPeripheralIdentifier, let existing = central.retrievePeripherals(withIdentifiers: [known]).first {
                result.scanFound = true
                result.peripheralIdentifier = existing.identifier.uuidString
                result.targetName = existing.name
                result.notes.append("using_retrieved_known_peripheral")
                target = existing
                existing.delegate = self
                central.stopScan()
                central.connect(existing, options: nil)
                return
            }
            let connected = central.retrieveConnectedPeripherals(withServices: [CBUUID(string: "FE95")])
            if let existing = connected.first(where: { ($0.name ?? "").localizedCaseInsensitiveContains(targetSubstring) }) {
                result.scanFound = true
                result.notes.append("using_retrieved_connected_peripheral")
                target = existing
                existing.delegate = self
                central.stopScan()
                central.connect(existing, options: nil)
            } else {
                central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: true])
            }
        }
        else if [.unsupported, .unauthorized, .poweredOff].contains(central.state) { finish("central_\(s)") }
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String : Any], rssi RSSI: NSNumber) {
        let name = peripheral.name ?? (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? ""
        if name.localizedCaseInsensitiveContains(targetSubstring) {
            result.scanFound = true; result.targetName = name; result.peripheralIdentifier = peripheral.identifier.uuidString
            target = peripheral; peripheral.delegate = self; central.stopScan(); fputs("target_found=\(name) rssi=\(RSSI)\n", stderr); central.connect(peripheral, options: nil)
        }
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) { target = peripheral; peripheral.delegate = self; result.connected = true; fputs("connected\n", stderr); peripheral.discoverServices([CBUUID(string: "FE95")]) }
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
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { self.writeInitialNext() }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        if let e = error { result.notifyState[characteristic.uuid.uuidString] = "error: \(e.localizedDescription)" }
        else { result.notifyState[characteristic.uuid.uuidString] = characteristic.isNotifying ? "notifying" : "not_notifying" }
        fputs("notify_state \(characteristic.uuid.uuidString)=\(result.notifyState[characteristic.uuid.uuidString] ?? "?")\n", stderr)
    }

    private func writeInitialNext() {
        guard nextWriteIndex < initialPayloads.count else { return }
        let item = initialPayloads[nextWriteIndex]
        writeFrame(label: item.label, data: item.data, index: nextWriteIndex)
        nextWriteIndex += 1
        if nextWriteIndex < initialPayloads.count {
            DispatchQueue.main.asyncAfter(deadline: .now() + interWriteDelay) { self.writeInitialNext() }
        } else {
            // Finish later after either auth step3 is built or no WatchNonce appears.
            DispatchQueue.main.asyncAfter(deadline: .now() + listenSeconds) { self.finish("listen_complete") }
        }
    }

    private func writeFrame(label: String, data: Data, index: Int) {
        guard let peripheral = target, let ch = writeChar else { return }
        let type: CBCharacteristicWriteType = ch.properties.contains(.writeWithoutResponse) ? .withoutResponse : .withResponse
        peripheral.writeValue(data, for: ch, type: type)
        let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        result.writes.append(AuthWriteRecord(index: index, label: label, characteristic: ch.uuid.uuidString, length: data.count, sha256_16: String(digest.prefix(16)), type: type == .withoutResponse ? "withoutResponse" : "withResponse"))
        fputs("wrote index=\(index) label=\(label) uuid=\(ch.uuid.uuidString) len=\(data.count) type=\(type == .withoutResponse ? "withoutResponse" : "withResponse")\n", stderr)
    }

    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        if let e = error { result.notes.append("write_error \(characteristic.uuid.uuidString): \(e.localizedDescription)") }
        else { result.notes.append("write_ack \(characteristic.uuid.uuidString)") }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard error == nil, let data = characteristic.value else { return }
        let hex = Self.hex(data)
        result.events.append(AuthWriteEvent(characteristic: characteristic.uuid.uuidString, length: data.count, sha256_16: String(Self.sha256(data).prefix(16)), hexPrefix: String(hex.prefix(32)), hex: hex))
        autoAckDataFrames(chunk: data)
        if nextWriteIndex >= initialPayloads.count && !result.authStep3Queued && !tryingHelper {
            tryBuildAndSendAuthStep3()
        }
    }

    private func autoAckDataFrames(chunk: Data) {
        rxBuffer.append(chunk)
        while true {
            guard rxBuffer.count >= 8 else { return }
            if rxBuffer[rxBuffer.startIndex] != 0xA5 || rxBuffer[rxBuffer.index(after: rxBuffer.startIndex)] != 0xA5 {
                if let idx = rxBuffer.firstIndex(of: 0xA5), idx != rxBuffer.startIndex { rxBuffer.removeSubrange(rxBuffer.startIndex..<idx) }
                else { rxBuffer.removeAll(keepingCapacity: true) }
                continue
            }
            let b2 = rxBuffer[rxBuffer.index(rxBuffer.startIndex, offsetBy: 2)]
            let seq = Int(rxBuffer[rxBuffer.index(rxBuffer.startIndex, offsetBy: 3)])
            let lenLo = Int(rxBuffer[rxBuffer.index(rxBuffer.startIndex, offsetBy: 4)])
            let lenHi = Int(rxBuffer[rxBuffer.index(rxBuffer.startIndex, offsetBy: 5)])
            let total = 8 + lenLo + (lenHi << 8)
            guard rxBuffer.count >= total else { return }
            let packetType = Int(b2 & 0x0f)
            if packetType == 3 && !ackedDataSequences.contains(seq) {
                let ack = Data([0xA5, 0xA5, 0x01, UInt8(seq & 0xff), 0x00, 0x00, 0x00, 0x00])
                writeFrame(label: "ack_rx_data_\(seq)", data: ack, index: extraWriteIndex)
                extraWriteIndex += 1
                ackedDataSequences.insert(seq)
            }
            let frameEnd = rxBuffer.index(rxBuffer.startIndex, offsetBy: total)
            let packet = rxBuffer[rxBuffer.startIndex..<frameEnd]
            maybeQueueEncryptedSanity(packet: Data(packet))
            rxBuffer.removeSubrange(rxBuffer.startIndex..<frameEnd)
        }
    }

    private func maybeQueueEncryptedSanity(packet: Data) {
        guard !postAuthFramesQueued else { return }
        guard packet.count >= 14 else { return }
        let packetType = Int(packet[packet.index(packet.startIndex, offsetBy: 2)] & 0x0f)
        guard packetType == 3 else { return }
        let payloadStart = packet.index(packet.startIndex, offsetBy: 8)
        let payload = packet[payloadStart..<packet.endIndex]
        guard payload.count >= 6 else { return }
        let bytes = Array(payload.prefix(6))
        // DATA plaintext auth final: channel=1 opcode=1, Command type=1 subtype=27.
        if bytes[0] == 0x01 && bytes[1] == 0x01 && bytes[2] == 0x08 && bytes[3] == 0x01 && bytes[4] == 0x10 && bytes[5] == 0x1b {
            postAuthFramesQueued = true
            if pendingPostAuthFrames.isEmpty, let sanity = pendingEncryptedSanityFrame {
                pendingPostAuthFrames = [(label: "encrypted_device_info_get", data: sanity)]
            }
            sendPostAuthFrame(index: 0)
        }
    }

    private func sendPostAuthFrame(index: Int) {
        guard index < pendingPostAuthFrames.count else { return }
        let item = pendingPostAuthFrames[index]
        writeFrame(label: item.label, data: item.data, index: extraWriteIndex)
        extraWriteIndex += 1
        if item.label == "encrypted_device_info_get" {
            encryptedSanityQueued = true
            result.notes.append("encrypted_sanity_queued=device_info_get")
        }
        result.notes.append("post_auth_queued=\(item.label)")
        let next = index + 1
        if next < pendingPostAuthFrames.count {
            let delay: TimeInterval = (item.label == "encrypted_sportxms_start" && pendingPostAuthFrames[next].label == "encrypted_sportxms_stop") ? 12.0 : 1.5
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) { self.sendPostAuthFrame(index: next) }
        }
    }

    private func tryBuildAndSendAuthStep3() {
        tryingHelper = true
        result.helperInvoked = true
        let statePath = outDir + "/auth_live_state.json"
        let helperOutPath = outDir + "/auth_step3_helper.local.json"
        writeResultSnapshot(to: statePath)

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: pythonPath)
        var helperArgs = [helperPath, "--state-json", statePath, "--payloads", outDir + "/payloads.txt", "--auth-tar", authTar, "--data-seq", "1"]
        for action in postAuthActions.split(separator: ",").map({ $0.trimmingCharacters(in: .whitespacesAndNewlines) }).filter({ !$0.isEmpty }) {
            helperArgs.append("--post-auth-action")
            helperArgs.append(action)
        }
        proc.arguments = helperArgs
        let pipe = Pipe(); proc.standardOutput = pipe
        let errPipe = Pipe(); proc.standardError = errPipe
        do {
            try proc.run(); proc.waitUntilExit()
        } catch {
            result.notes.append("auth_step3_helper_run_error=\(error.localizedDescription)")
            tryingHelper = false
            return
        }
        let outData = pipe.fileHandleForReading.readDataToEndOfFile()
        let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
        try? outData.write(to: URL(fileURLWithPath: helperOutPath))
        if !errData.isEmpty { try? errData.write(to: URL(fileURLWithPath: outDir + "/auth_step3_helper.stderr")) }
        guard let obj = try? JSONSerialization.jsonObject(with: outData) as? [String: Any] else {
            result.notes.append("auth_step3_helper_invalid_json")
            tryingHelper = false
            return
        }
        if let ok = obj["ok"] as? Bool, ok,
           let step3Hex = obj["auth_step3_frame_hex"] as? String,
           let step3 = decodeHex(step3Hex) {
            result.notes.append("auth_step3_helper_file=\(helperOutPath)")
            if let redacted = obj["redacted"] as? [String: Any], let redactedData = try? JSONSerialization.data(withJSONObject: redacted, options: [.sortedKeys]), let redactedString = String(data: redactedData, encoding: .utf8) {
                result.notes.append("auth_step3_redacted=\(redactedString)")
            }
            if let postFrames = obj["post_auth_frames"] as? [[String: Any]] {
                pendingPostAuthFrames = postFrames.compactMap { frameObj in
                    guard let label = frameObj["label"] as? String,
                          let hex = frameObj["frame_hex"] as? String,
                          let data = decodeHex(hex) else { return nil }
                    return (label: label, data: data)
                }
            }
            if pendingPostAuthFrames.isEmpty,
               let sanityHex = obj["encrypted_device_info_get_frame_hex"] as? String,
               let sanity = decodeHex(sanityHex) {
                pendingEncryptedSanityFrame = sanity
            }
            writeFrame(label: "auth_step3", data: step3, index: self.extraWriteIndex); self.extraWriteIndex += 1
            self.result.authStep3Queued = true
        } else {
            result.notes.append("auth_step3_helper_not_ready=\(obj["error"] ?? "unknown")")
            tryingHelper = false
        }
    }

    private func writeResultSnapshot(to path: String) {
        let enc = JSONEncoder(); enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        if let data = try? enc.encode(result) { try? data.write(to: URL(fileURLWithPath: path)) }
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

func loadPayloads(path: String) -> [AuthPayloadItem] {
    guard let text = try? String(contentsOfFile: path, encoding: .utf8) else { fputs("cannot read payload file\n", stderr); exit(64) }
    var items: [AuthPayloadItem] = []
    for rawLine in text.split(separator: "\n", omittingEmptySubsequences: false) {
        let noComment = rawLine.split(separator: "#", maxSplits: 1, omittingEmptySubsequences: false).first.map(String.init) ?? ""
        let line = noComment.trimmingCharacters(in: .whitespacesAndNewlines)
        if line.isEmpty { continue }
        let parts = line.split(separator: " ", maxSplits: 1, omittingEmptySubsequences: true)
        let label: String
        let hex: String
        if parts.count == 2 { label = String(parts[0]); hex = String(parts[1]) }
        else { label = "payload_\(items.count)"; hex = line }
        guard let data = decodeHex(hex) else { fputs("invalid payload hex for \(label)\n", stderr); exit(64) }
        items.append(AuthPayloadItem(label: label, data: data))
    }
    if items.isEmpty { fputs("payload file is empty\n", stderr); exit(64) }
    return items
}

func parseArgs() -> (String, String, [AuthPayloadItem], String, String, TimeInterval, TimeInterval, String, String, String, UUID?) {
    let args = Array(CommandLine.arguments.dropFirst())
    if args.count < 4 {
        fputs("usage: ble_sar_auth_probe <target-name-substring> <payload-file> <auth-tar> <out-dir> [listen-seconds] [write-uuid] [inter-write-delay] [python] [helper] [post-auth-actions] [known-peripheral-uuid]\n", stderr)
        exit(64)
    }
    let target = args[0]
    let payloadPath = args[1]
    let authTar = args[2]
    let outDir = args[3]
    let listen = args.count >= 5 ? (Double(args[4]) ?? 20.0) : 20.0
    let writeUUID = args.count >= 6 ? args[5] : "005F"
    let delay = args.count >= 7 ? (Double(args[6]) ?? 1.2) : 1.2
    let python = args.count >= 8 ? args[7] : "/tmp/miband9_crypto_venv/bin/python"
    let helper = args.count >= 9 ? args[8] : "tools/mac_direct/build_auth_step3_from_events.py"
    let postAuthActions = args.count >= 10 ? args[9] : "device_info_get"
    let knownIdentifier = args.count >= 11 ? UUID(uuidString: args[10]) : nil
    return (target, writeUUID, loadPayloads(path: payloadPath), authTar, outDir, listen, delay, python, helper, postAuthActions, knownIdentifier)
}

let (target, writeUUID, payloads, authTar, outDir, listen, delay, pythonPath, helperPath, postAuthActions, knownIdentifier) = parseArgs()
let probe = AuthProbe(targetSubstring: target, writeUUID: writeUUID, initialPayloads: payloads, authTar: authTar, outDir: outDir, listenSeconds: listen, interWriteDelay: delay, pythonPath: pythonPath, helperPath: helperPath, postAuthActions: postAuthActions, knownPeripheralIdentifier: knownIdentifier)
withExtendedLifetime(probe) { RunLoop.main.run() }
