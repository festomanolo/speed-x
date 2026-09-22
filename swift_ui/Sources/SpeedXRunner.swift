import Foundation

struct SpeedXResponse: Codable {
    let success: Bool
    let message: String
    let domain: String
    let action: String
    let confidence: Double
    let latency_ms: Double
    let source: String
}

typealias LayaResponse = SpeedXResponse

class SpeedXRunner {
    static let shared = SpeedXRunner()

    var lastCommand: String = "ongeza sauti"
    var lastResponse: SpeedXResponse? = SpeedXResponse(
        success: true,
        message: "Speed-X Engine Ready",
        domain: "system",
        action: "ready",
        confidence: 0.94,
        latency_ms: 190.0,
        source: "coreml"
    )
    var isRunning: Bool = false

    private let pythonPath = "/Volumes/MacX/speed-x/.venv/bin/python"
    private let mainScript = "/Volumes/MacX/speed-x/main.py"

    func execute(command: String, completion: @escaping (SpeedXResponse?) -> Void) {
        guard !command.trimmingCharacters(in: .whitespaces).isEmpty else {
            completion(nil)
            return
        }

        self.lastCommand = command
        self.isRunning = true

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }

            let task = Process()
            task.executableURL = URL(fileURLWithPath: self.pythonPath)
            task.arguments = [self.mainScript, "--json", command]

            let pipe = Pipe()
            task.standardOutput = pipe
            task.standardError = Pipe()

            do {
                try task.run()
                task.waitUntilExit()

                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                if let str = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) {
                    let lines = str.components(separatedBy: .newlines)
                    for line in lines.reversed() {
                        if line.starts(with: "{") && line.contains("\"success\"") {
                            if let jsonData = line.data(using: .utf8) {
                                let resp = try? JSONDecoder().decode(SpeedXResponse.self, from: jsonData)
                                DispatchQueue.main.async {
                                    self.lastResponse = resp
                                    self.isRunning = false
                                    completion(resp)
                                }
                                return
                            }
                        }
                    }
                }
            } catch {
                print("Speed-X Execution error:", error)
            }

            DispatchQueue.main.async {
                self.isRunning = false
                completion(nil)
            }
        }
    }
}

typealias LayaRunner = SpeedXRunner
