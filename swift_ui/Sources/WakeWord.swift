import Foundation

/// "Speed X" hands-free trigger. Listens only on-device (never streams audio anywhere), pauses while a
/// command, dictation or meeting is using the microphone, and is off until you turn it on.
final class WakeWordListener {
    static let shared = WakeWordListener()
    static let enabledKey = "SpeedXWakeWord"

    var onWake: (() -> Void)?
    private let recognizer = ContinuousRecognizer()
    private var busyCount = 0
    private var lastWake = Date.distantPast
    private(set) var enabled: Bool

    /// What the recognizer tends to write for "Speed X".
    private static let phrases = ["speed x", "speedx", "speed ex", "speed ten", "speed 10", "speed's x", "hey speed", "ok speed", "okay speed"]

    init() {
        enabled = UserDefaults.standard.bool(forKey: Self.enabledKey)
        recognizer.onPartial = { [weak self] text in self?.heard(text) }
    }

    /// Returns false (and stays off) if on-device recognition isn't possible.
    @discardableResult
    func setEnabled(_ on: Bool) -> Bool {
        if on, !ContinuousRecognizer.available { return false }
        enabled = on
        UserDefaults.standard.set(on, forKey: Self.enabledKey)
        refresh()
        return true
    }

    func restoreOnLaunch() { if enabled { refresh() } }

    /// Something else needs the microphone (true) / is done with it (false).
    func setBusy(_ busy: Bool) {
        busyCount = max(0, busyCount + (busy ? 1 : -1))
        refresh()
    }

    private func refresh() {
        if enabled, busyCount == 0 {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [self] in
                if enabled, busyCount == 0, !recognizer.running { recognizer.start() }
            }
        } else {
            recognizer.stop()
        }
    }

    private func heard(_ text: String) {
        let tail = text.lowercased().split(separator: " ").suffix(5).joined(separator: " ")
        guard Self.phrases.contains(where: { tail.contains($0) }), Date().timeIntervalSince(lastWake) > 3 else { return }
        lastWake = Date()
        recognizer.stop()   // the command session takes the mic; setBusy(false) brings us back
        onWake?()
    }
}
