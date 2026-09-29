import Foundation

/// One executed (or proposed) step of a command plan.
struct EngineStep: Codable, Hashable {
    let domain: String
    let action: String
    let label: String
    let confidence: Double
    let source: String
    var success: Bool?
    var message: String?
}

struct EngineResponse: Codable {
    let id: Int?
    let command: String?
    let success: Bool?
    let message: String?
    let domain: String?
    let action: String?
    let confidence: Double?
    let source: String?
    let latency_ms: Double?
    let needs_confirmation: Bool?
    let suggestion: String?
    let steps: [EngineStep]?
    let preview: [EngineStep]?
    // status fields / events
    let event: String?
    let coreml: String?
    let coreml_enabled: Bool?
    let compute_units: String?
    let llm: String?
    let llm_model: String?
    let llm_kind: String?
    let cloud_llm: String?
    let label: String?
    let seconds: Int?
    let text: String?
    // AppleScript requests from the engine
    let osa_id: Int?
    let script: String?
    let timeout: Double?
}

/// Talks to the warm `python -m speed_x.server` daemon over JSON lines.
final class EngineClient {
    static let shared = EngineClient()

    var onEvent: ((EngineResponse) -> Void)?
    /// Called with true when an AppleScript has been running long enough that macOS is
    /// probably showing an Automation permission dialog, and false when it finishes.
    var onPermissionWait: ((Bool) -> Void)?

    /// All AppleScript runs on this one thread (NSAppleScript is not thread-safe). Running it
    /// in the app means macOS asks "SpeedX wants to control Music" once, and remembers it.
    private let osaThread = OSAThread()
    private(set) var isReady = false

    private var process: Process?
    private var stdinHandle: FileHandle?
    private var buffer = Data()
    private var nextID = 1
    private var pending: [Int: (EngineResponse) -> Void] = [:]
    private var restartCount = 0
    private let queue = DispatchQueue(label: "speedx.engine")
    private let debug = ProcessInfo.processInfo.environment["SPEEDX_DEBUG"] == "1"

    private func log(_ message: @autoclosure () -> String) {
        if debug { FileHandle.standardError.write(Data(("[EngineClient] " + message() + "\n").utf8)) }
    }

    static var projectRoot: String {
        if let env = ProcessInfo.processInfo.environment["SPEEDX_HOME"] { return env }
        if let plist = Bundle.main.object(forInfoDictionaryKey: "SpeedXProjectRoot") as? String { return plist }
        return "/Volumes/MacX/speed-x"
    }

    func start() {
        queue.async { self.launch() }
    }

    private func launch() {
        let root = Self.projectRoot
        let python = "\(root)/.venv/bin/python"
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: FileManager.default.fileExists(atPath: python) ? python : "/usr/bin/python3")
        proc.arguments = ["-u", "-m", "speed_x.server"]
        proc.currentDirectoryURL = URL(fileURLWithPath: root)
        var env = ProcessInfo.processInfo.environment
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = root
        env["SPEEDX_HOSTED"] = "1"
        proc.environment = env

        let inPipe = Pipe(), outPipe = Pipe(), errPipe = Pipe()
        proc.standardInput = inPipe
        proc.standardOutput = outPipe
        proc.standardError = errPipe

        outPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            self?.queue.async { self?.consume(data) }
        }
        errPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if !data.isEmpty, let s = String(data: data, encoding: .utf8) { FileHandle.standardError.write(Data(("[engine] " + s).utf8)) }
        }
        proc.terminationHandler = { [weak self] _ in
            self?.queue.async { self?.handleExit() }
        }

        do {
            try proc.run()
            process = proc
            stdinHandle = inPipe.fileHandleForWriting
        } catch {
            print("EngineClient: failed to launch engine:", error)
        }
    }

    private func handleExit() {
        isReady = false
        let callbacks = pending
        pending.removeAll()
        let failure = EngineResponse(id: nil, command: nil, success: false, message: "Engine restarted — please try again.", domain: nil, action: nil, confidence: nil, source: nil, latency_ms: nil, needs_confirmation: nil, suggestion: nil, steps: nil, preview: nil, event: nil, coreml: nil, coreml_enabled: nil, compute_units: nil, llm: nil, llm_model: nil, llm_kind: nil, cloud_llm: nil, label: nil, seconds: nil, text: nil, osa_id: nil, script: nil, timeout: nil)
        DispatchQueue.main.async { callbacks.values.forEach { $0(failure) } }
        restartCount += 1
        guard restartCount < 20 else { return }
        queue.asyncAfter(deadline: .now() + min(5, Double(restartCount) * 0.5)) { self.launch() }
    }

    private func consume(_ data: Data) {
        buffer.append(data)
        while let newline = buffer.firstIndex(of: 0x0A) {
            let line = buffer.subdata(in: buffer.startIndex..<newline)
            buffer.removeSubrange(buffer.startIndex...newline)
            log("<- " + (String(data: line, encoding: .utf8) ?? "?").prefix(160))
            guard !line.isEmpty else { continue }
            let resp: EngineResponse
            do { resp = try JSONDecoder().decode(EngineResponse.self, from: line) } catch { log("decode failed: \(error)"); continue }
            if let id = resp.id, let callback = pending.removeValue(forKey: id) {
                DispatchQueue.main.async { callback(resp) }
            } else if resp.event == "osa", let oid = resp.osa_id, let script = resp.script {
                runAppleScript(id: oid, script: script)
            } else if resp.event != nil {
                if resp.event == "ready" { isReady = true; restartCount = 0 }
                DispatchQueue.main.async { self.onEvent?(resp) }
            }
        }
    }

    private func send(_ payload: [String: Any], completion: ((EngineResponse) -> Void)?) {
        queue.async {
            var body = payload
            let id = self.nextID
            self.nextID += 1
            body["id"] = id
            if let completion { self.pending[id] = completion }
            guard let data = try? JSONSerialization.data(withJSONObject: body), let handle = self.stdinHandle else {
                self.log("send dropped (engine not running): \(body)")
                return
            }
            self.log("-> \(String(data: data, encoding: .utf8) ?? "")")
            handle.write(data + Data([0x0A]))
        }
    }

    private func runAppleScript(id: Int, script: String) {
        let slow = DispatchWorkItem { [weak self] in self?.onPermissionWait?(true) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5, execute: slow)
        osaThread.run(script) { [weak self] result, error in
            slow.cancel()
            DispatchQueue.main.async { self?.onPermissionWait?(false) }
            var reply: [String: Any] = ["osa_reply": id, "ok": error == nil]
            if let result { reply["result"] = result }
            if let error { reply["error"] = error }
            self?.queue.async { self?.write(reply) }
        }
    }

    private func write(_ body: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: body), let handle = stdinHandle else { return }
        handle.write(data + Data([0x0A]))
    }

    // MARK: - API

    func run(_ command: String, frontApp: String?, completion: @escaping (EngineResponse) -> Void) {
        var payload: [String: Any] = ["op": "run", "cmd": command]
        if let frontApp { payload["front_app"] = frontApp }
        send(payload, completion: completion)
    }

    func preview(_ command: String, completion: @escaping (EngineResponse) -> Void) {
        send(["op": "preview", "cmd": command], completion: completion)
    }

    func confirm(completion: @escaping (EngineResponse) -> Void) { send(["op": "confirm"], completion: completion) }
    func cancel(completion: @escaping (EngineResponse) -> Void) { send(["op": "cancel"], completion: completion) }
    func setCloudKey(_ key: String, completion: @escaping (EngineResponse) -> Void) {
        send(["op": "set_cloud_key", "key": key], completion: completion)
    }

    func setCoreML(_ enabled: Bool, completion: @escaping (EngineResponse) -> Void) {
        send(["op": "set_coreml", "enabled": enabled], completion: completion)
    }

    func shutdown() {
        process?.terminationHandler = nil
        process?.terminate()
    }
}

/// A long-lived thread with its own run loop that executes compiled AppleScripts.
final class OSAThread: Thread {
    private var cache: [String: NSAppleScript] = [:]
    private let ready = DispatchSemaphore(value: 0)
    private var runLoop: RunLoop?

    override init() {
        super.init()
        name = "speedx.applescript"
        qualityOfService = .userInitiated
        start()
        ready.wait()
    }

    override func main() {
        runLoop = RunLoop.current
        runLoop?.add(NSMachPort(), forMode: .default)
        ready.signal()
        while !isCancelled { runLoop?.run(mode: .default, before: .distantFuture) }
    }

    func run(_ source: String, completion: @escaping (String?, String?) -> Void) {
        runLoop?.perform {
            let script: NSAppleScript
            if let cached = self.cache[source] {
                script = cached
            } else if let compiled = NSAppleScript(source: source) {
                script = compiled
                if self.cache.count < 256 { self.cache[source] = compiled }
            } else {
                completion(nil, "Could not compile AppleScript")
                return
            }
            var error: NSDictionary?
            let output = script.executeAndReturnError(&error)
            if let error {
                completion(nil, (error[NSAppleScript.errorMessage] as? String) ?? "AppleScript error \(error[NSAppleScript.errorNumber] ?? "")")
            } else {
                completion(output.stringValue ?? "", nil)
            }
        }
    }
}
