import Foundation
import IOBluetooth
import CryptoKit

struct Event: Codable { let characteristic: String; let length: Int; let sha256_16: String; let hexPrefix: String; let hex: String; let receivedAt: String; let monotonicNs: UInt64 }
struct WriteRec: Codable { let index: Int; let label: String; let characteristic: String; let length: Int; let sha256_16: String; let type: String }
struct ResultObj: Codable {
    let startedAt: String
    var endedAt: String?
    var centralState: String? = "iobluetooth"
    var scanFound = true
    var connected = false
    var targetName: String?
    var peripheralIdentifier: String?
    var writeUUID: String = "RFCOMM5"
    var notifyState: [String:String] = ["RFCOMM5":"open_requested"]
    var writes: [WriteRec] = []
    var events: [Event] = []
    var helperInvoked = false
    var authStep3Queued = false
    var error: String?
    var notes: [String] = []
}
struct PayloadItem { let label: String; let data: Data }

final class RFCOMMProbe: NSObject, IOBluetoothRFCOMMChannelDelegate {
    let address: String
    let channelID: BluetoothRFCOMMChannelID
    let payloads: [PayloadItem]
    let authTar: String
    let outDir: String
    let listenSeconds: TimeInterval
    let interWriteDelay: TimeInterval
    let pythonPath: String
    let helperPath: String
    let postAuthActions: String
    let sportxmsStopDelay: TimeInterval
    let helperExtraArgs: [String]
    var result = ResultObj(startedAt: ISO8601DateFormatter().string(from: Date()))
    var channel: IOBluetoothRFCOMMChannel?
    var nextWriteIndex = 0
    var extraWriteIndex = 100
    var rxBuffer = Data()
    var ackedDataSequences = Set<Int>()
    var tryingHelper = false
    var pendingPostAuthFrames: [(label:String,data:Data)] = []
    var postAuthFramesQueued = false
    let iso = ISO8601DateFormatter()

    init(address: String, channelID: BluetoothRFCOMMChannelID, payloads: [PayloadItem], authTar: String, outDir: String, listenSeconds: TimeInterval, interWriteDelay: TimeInterval, pythonPath: String, helperPath: String, postAuthActions: String, sportxmsStopDelay: TimeInterval, helperExtraArgs: [String]) {
        self.address = address; self.channelID = channelID; self.payloads = payloads; self.authTar = authTar; self.outDir = outDir; self.listenSeconds = listenSeconds; self.interWriteDelay = interWriteDelay; self.pythonPath = pythonPath; self.helperPath = helperPath; self.postAuthActions = postAuthActions; self.sportxmsStopDelay = sportxmsStopDelay; self.helperExtraArgs = helperExtraArgs
        super.init()
    }

    func start() {
        guard let dev = IOBluetoothDevice(addressString: address) else { finish("device_nil", error: "device_nil"); return }
        result.targetName = dev.name
        result.peripheralIdentifier = dev.addressString
        result.notes.append("using_iobluetooth_rfcomm_channel_\(channelID)")
        let openBase = dev.openConnection()
        result.notes.append("open_base_result=\(openBase)")
        var ch: IOBluetoothRFCOMMChannel? = nil
        let r = dev.openRFCOMMChannelSync(&ch, withChannelID: channelID, delegate: self)
        result.notes.append("open_rfcomm_result=\(r)")
        guard r == kIOReturnSuccess, let opened = ch else { finish("rfcomm_open_failed", error: "rfcomm_open_failed_\(r)"); return }
        channel = opened
        result.connected = true
        result.notifyState["RFCOMM5"] = "open"
        fputs("rfcomm_open channel=\(channelID) mtu=\(opened.getMTU())\n", stderr)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { self.writeInitialNext() }
        DispatchQueue.main.asyncAfter(deadline: .now() + listenSeconds + interWriteDelay * Double(payloads.count) + 75) { self.finish("timeout") }
    }

    func rfcommChannelData(_ rfcommChannel: IOBluetoothRFCOMMChannel!, data dataPointer: UnsafeMutableRawPointer!, length dataLength: Int) {
        guard dataPointer != nil, dataLength > 0 else { return }
        let d = Data(bytes: dataPointer, count: dataLength)
        let hx = hex(d)
        result.events.append(Event(characteristic: "RFCOMM5", length: dataLength, sha256_16: String(sha256(d).prefix(16)), hexPrefix: String(hx.prefix(32)), hex: hx, receivedAt: iso.string(from: Date()), monotonicNs: DispatchTime.now().uptimeNanoseconds))
        autoAckDataFrames(chunk: d)
        if nextWriteIndex >= payloads.count && !result.authStep3Queued && !tryingHelper { tryBuildAndSendAuthStep3() }
    }

    func rfcommChannelOpenComplete(_ rfcommChannel: IOBluetoothRFCOMMChannel!, status error: IOReturn) { result.notes.append("rfcomm_open_complete=\(error)") }
    func rfcommChannelClosed(_ rfcommChannel: IOBluetoothRFCOMMChannel!) { result.notes.append("rfcomm_closed") }
    func rfcommChannelWriteComplete(_ rfcommChannel: IOBluetoothRFCOMMChannel!, refcon: UnsafeMutableRawPointer!, status error: IOReturn) { result.notes.append("write_complete=\(error)") }

    func writeInitialNext() {
        guard nextWriteIndex < payloads.count else { return }
        let item = payloads[nextWriteIndex]
        writeFrame(label: item.label, data: item.data, index: nextWriteIndex)
        nextWriteIndex += 1
        if nextWriteIndex < payloads.count { DispatchQueue.main.asyncAfter(deadline: .now() + interWriteDelay) { self.writeInitialNext() } }
    }

    func writeFrame(label: String, data: Data, index: Int) {
        guard let ch = channel else { return }
        var bytes = [UInt8](data)
        let byteCount = UInt16(bytes.count)
        let res: IOReturn = bytes.withUnsafeMutableBytes { ptr in
            guard let base = ptr.baseAddress else { return IOReturn(kIOReturnBadArgument) }
            return ch.writeSync(base, length: byteCount)
        }
        let dg = sha256(data)
        result.writes.append(WriteRec(index: index, label: label, characteristic: "RFCOMM5", length: data.count, sha256_16: String(dg.prefix(16)), type: "rfcomm_writeSync_\(res)"))
        fputs("wrote index=\(index) label=\(label) len=\(data.count) result=\(res)\n", stderr)
    }

    func autoAckDataFrames(chunk: Data) {
        rxBuffer.append(chunk)
        while true {
            guard rxBuffer.count >= 8 else { return }
            if rxBuffer[rxBuffer.startIndex] != 0xA5 || rxBuffer[rxBuffer.index(after: rxBuffer.startIndex)] != 0xA5 {
                if let idx = rxBuffer.firstIndex(of: 0xA5), idx != rxBuffer.startIndex { rxBuffer.removeSubrange(rxBuffer.startIndex..<idx) } else { rxBuffer.removeAll(keepingCapacity: true) }
                continue
            }
            let b2 = rxBuffer[rxBuffer.index(rxBuffer.startIndex, offsetBy: 2)]
            let seq = Int(rxBuffer[rxBuffer.index(rxBuffer.startIndex, offsetBy: 3)])
            let lenLo = Int(rxBuffer[rxBuffer.index(rxBuffer.startIndex, offsetBy: 4)])
            let lenHi = Int(rxBuffer[rxBuffer.index(rxBuffer.startIndex, offsetBy: 5)])
            let total = 8 + lenLo + (lenHi << 8)
            guard rxBuffer.count >= total else { return }
            let packetType = Int(b2 & 0x0f)
            let frameEnd = rxBuffer.index(rxBuffer.startIndex, offsetBy: total)
            let packet = Data(rxBuffer[rxBuffer.startIndex..<frameEnd])
            if packetType == 3 && !ackedDataSequences.contains(seq) {
                let ack = Data([0xA5,0xA5,0x01,UInt8(seq & 0xff),0,0,0,0])
                writeFrame(label: "ack_rx_data_\(seq)", data: ack, index: extraWriteIndex); extraWriteIndex += 1; ackedDataSequences.insert(seq)
            }
            maybeQueuePostAuth(packet: packet)
            rxBuffer.removeSubrange(rxBuffer.startIndex..<frameEnd)
        }
    }

    func maybeQueuePostAuth(packet: Data) {
        guard !postAuthFramesQueued, packet.count >= 14 else { return }
        let packetType = Int(packet[packet.index(packet.startIndex, offsetBy: 2)] & 0x0f)
        guard packetType == 3 else { return }
        let payload = packet[packet.index(packet.startIndex, offsetBy: 8)..<packet.endIndex]
        guard payload.count >= 6 else { return }
        let bytes = Array(payload.prefix(6))
        if bytes[0] == 0x01 && bytes[1] == 0x01 && bytes[2] == 0x08 && bytes[3] == 0x01 && bytes[4] == 0x10 && bytes[5] == 0x1b {
            postAuthFramesQueued = true
            sendPostAuthFrame(index: 0)
        }
    }

    func sendPostAuthFrame(index: Int) {
        guard index < pendingPostAuthFrames.count else { return }
        let item = pendingPostAuthFrames[index]
        writeFrame(label: item.label, data: item.data, index: extraWriteIndex); extraWriteIndex += 1
        result.notes.append("post_auth_queued=\(item.label)")
        let next = index + 1
        if next < pendingPostAuthFrames.count {
            let delay: TimeInterval = (item.label == "encrypted_sportxms_start" && pendingPostAuthFrames[next].label == "encrypted_sportxms_stop") ? sportxmsStopDelay : 1.5
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) { self.sendPostAuthFrame(index: next) }
        } else {
            let tail: TimeInterval = item.label == "encrypted_sportxms_stop" ? 8.0 : listenSeconds
            DispatchQueue.main.asyncAfter(deadline: .now() + tail) { self.finish("post_auth_complete") }
        }
    }

    func tryBuildAndSendAuthStep3() {
        tryingHelper = true; result.helperInvoked = true
        let statePath = outDir + "/auth_live_state.json"
        let helperOutPath = outDir + "/auth_step3_helper.local.json"
        writeSnapshot(path: statePath)
        let proc = Process(); proc.executableURL = URL(fileURLWithPath: pythonPath)
        var args = [helperPath, "--state-json", statePath, "--payloads", outDir + "/payloads.txt", "--auth-tar", authTar, "--data-seq", "1"]
        for action in postAuthActions.split(separator: ",").map({ $0.trimmingCharacters(in: .whitespacesAndNewlines) }).filter({ !$0.isEmpty }) { args += ["--post-auth-action", action] }
        args += helperExtraArgs
        proc.arguments = args
        let out = Pipe(); let err = Pipe(); proc.standardOutput = out; proc.standardError = err
        do { try proc.run(); proc.waitUntilExit() } catch { result.notes.append("helper_run_error=\(error.localizedDescription)"); tryingHelper=false; return }
        let outData = out.fileHandleForReading.readDataToEndOfFile(); let errData = err.fileHandleForReading.readDataToEndOfFile()
        try? outData.write(to: URL(fileURLWithPath: helperOutPath)); if !errData.isEmpty { try? errData.write(to: URL(fileURLWithPath: outDir + "/auth_step3_helper.stderr")) }
        guard let obj = try? JSONSerialization.jsonObject(with: outData) as? [String:Any] else { result.notes.append("helper_invalid_json"); tryingHelper=false; return }
        if let ok = obj["ok"] as? Bool, ok, let stepHex = obj["auth_step3_frame_hex"] as? String, let step = decodeHex(stepHex) {
            result.notes.append("auth_step3_helper_file=\(helperOutPath)")
            if let red = obj["redacted"] as? [String:Any], let rd = try? JSONSerialization.data(withJSONObject: red, options: [.sortedKeys]), let rs = String(data: rd, encoding: .utf8) { result.notes.append("auth_step3_redacted=\(rs)") }
            if let postFrames = obj["post_auth_frames"] as? [[String:Any]] {
                pendingPostAuthFrames = postFrames.compactMap { fo in
                    guard let label = fo["label"] as? String, let hx = fo["frame_hex"] as? String, let d = decodeHex(hx) else { return nil }
                    return (label: label, data: d)
                }
            }
            writeFrame(label: "auth_step3", data: step, index: extraWriteIndex); extraWriteIndex += 1; result.authStep3Queued = true
        } else { result.notes.append("helper_not_ready=\(obj["error"] ?? "unknown")"); tryingHelper=false }
    }

    func writeSnapshot(path: String) { let enc = JSONEncoder(); enc.outputFormatting = [.prettyPrinted,.sortedKeys]; if let d = try? enc.encode(result) { try? d.write(to: URL(fileURLWithPath: path)) } }
    func finish(_ reason: String, error: String? = nil) { result.endedAt = iso.string(from: Date()); result.notes.append("finish_reason=\(reason)"); if let e = error { result.error = e }; channel?.close(); let enc = JSONEncoder(); enc.outputFormatting = [.prettyPrinted,.sortedKeys]; if let d = try? enc.encode(result) { FileHandle.standardOutput.write(d); FileHandle.standardOutput.write("\n".data(using:.utf8)!)}; exit(result.error == nil ? 0 : 1) }
}

func sha256(_ data: Data) -> String { SHA256.hash(data:data).map{String(format:"%02x",$0)}.joined() }
func hex(_ data: Data) -> String { data.map{String(format:"%02x",$0)}.joined() }
func decodeHex(_ s: String) -> Data? { let h=s.filter{!$0.isWhitespace}; guard h.count%2==0 else{return nil}; var d=Data(); var i=h.startIndex; while i<h.endIndex { let j=h.index(i,offsetBy:2); guard let b=UInt8(h[i..<j],radix:16) else {return nil}; d.append(b); i=j }; return d }
func loadPayloads(_ path: String) -> [PayloadItem] { guard let text=try? String(contentsOfFile:path, encoding:.utf8) else { fputs("payload_read_failed\n", stderr); exit(64) }; var out:[PayloadItem]=[]; for raw in text.split(separator:"\n",omittingEmptySubsequences:false) { let line=raw.split(separator:"#",maxSplits:1,omittingEmptySubsequences:false).first.map(String.init)?.trimmingCharacters(in:.whitespacesAndNewlines) ?? ""; if line.isEmpty {continue}; let parts=line.split(separator:" ",maxSplits:1); let label=parts.count==2 ? String(parts[0]) : "payload_\(out.count)"; let hx=parts.count==2 ? String(parts[1]) : line; guard let d=decodeHex(hx) else { fputs("bad_hex\n", stderr); exit(64) }; out.append(PayloadItem(label: label, data: d)) }; return out }

let args = Array(CommandLine.arguments.dropFirst())
if args.count < 4 { fputs("usage: rfcomm_auth_probe <address> <payload-file> <auth-tar> <out-dir> [listen] [channel] [delay] [python] [helper] [post-actions] [sportxms-stop-delay] [helper-extra-args]\n", stderr); exit(64) }
let address=args[0], payloadPath=args[1], authTar=args[2], outDir=args[3]
let listen=args.count>=5 ? (Double(args[4]) ?? 85.0) : 85.0
let channelID=BluetoothRFCOMMChannelID(args.count>=6 ? (UInt8(args[5]) ?? 5) : 5)
let delay=args.count>=7 ? (Double(args[6]) ?? 1.2) : 1.2
let python=args.count>=8 ? args[7] : "/tmp/miband9_crypto_venv/bin/python"
let helper=args.count>=9 ? args[8] : "tools/mac_direct/build_auth_step3_from_events.py"
let actions=args.count>=10 ? args[9] : "sportxms_start,sportxms_stop"
let stopDelay=args.count>=11 ? (Double(args[10]) ?? 12.0) : 12.0
let helperExtraArgs=args.count>=12 ? args[11].split(separator:" ").map(String.init) : []
let probe = RFCOMMProbe(address: address, channelID: channelID, payloads: loadPayloads(payloadPath), authTar: authTar, outDir: outDir, listenSeconds: listen, interWriteDelay: delay, pythonPath: python, helperPath: helper, postAuthActions: actions, sportxmsStopDelay: stopDelay, helperExtraArgs: helperExtraArgs)
probe.start()
withExtendedLifetime(probe) { RunLoop.main.run() }
