import AVFoundation
import Foundation
import Speech

/// Always-on, on-device-only speech recognition that restarts itself before Apple's ~1 minute task limit.
/// Used by the wake word and the meeting copilot. It refuses to run if the recognizer can't work fully
/// on this Mac, so audio never goes to a server.
final class ContinuousRecognizer {
    var onPartial: ((String) -> Void)?
    /// A finished segment (rotation or endSegment): the last text heard.
    var onSegment: ((String) -> Void)?
    private(set) var running = false

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var engine: AVAudioEngine?
    private var task: SFSpeechRecognitionTask?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private let lock = NSLock()
    private var live: SFSpeechAudioBufferRecognitionRequest?
    private var lastText = ""
    private var rotateTimer: Timer?
    private var configObserver: NSObjectProtocol?
    private var generation = 0
    var contextualStrings: [String] = []
    private var taskStart = Date.distantPast
    private var retryPending = false

    static var available: Bool {
        guard SFSpeechRecognizer.authorizationStatus() == .authorized,
              AVCaptureDevice.authorizationStatus(for: .audio) == .authorized,
              let r = SFSpeechRecognizer(locale: Locale(identifier: "en-US")) else { return false }
        return r.isAvailable && r.supportsOnDeviceRecognition
    }

    @discardableResult
    func start() -> Bool {
        guard !running, Self.available, recognizer != nil else { return false }
        let engine = AVAudioEngine()
        let input = engine.inputNode
        if let device = AudioDevices.shared.selectedDevice(), let unit = input.audioUnit {
            var id = device.id
            AudioUnitSetProperty(unit, kAudioOutputUnitProperty_CurrentDevice, kAudioUnitScope_Global, 0, &id, UInt32(MemoryLayout<AudioDeviceID>.size))
        }
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else { return false }
        input.installTap(onBus: 0, bufferSize: 2048, format: format) { [weak self] buffer, _ in
            guard let self else { return }
            self.lock.lock(); let request = self.live; self.lock.unlock()
            request?.append(buffer)
        }
        do { engine.prepare(); try engine.start() } catch {
            input.removeTap(onBus: 0)
            return false
        }
        self.engine = engine
        running = true
        beginTask()
        rotateTimer = Timer.scheduledTimer(withTimeInterval: 45, repeats: true) { [weak self] _ in self?.endSegment() }
        configObserver = NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main) { [weak self] _ in
            guard let self, self.running else { return }
            self.stop()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { _ = self.start() }
        }
        return true
    }

    func stop() {
        guard running else { return }
        running = false
        rotateTimer?.invalidate(); rotateTimer = nil
        if let configObserver { NotificationCenter.default.removeObserver(configObserver) }
        configObserver = nil
        engine?.stop()
        engine?.inputNode.removeTap(onBus: 0)
        engine = nil
        lock.lock(); live?.endAudio(); live = nil; lock.unlock()
        task?.cancel(); task = nil; request = nil
        lastText = ""
    }

    /// Close the current phrase (reporting it) and start listening for the next one.
    func endSegment() {
        guard running else { return }
        let text = lastText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.isEmpty { onSegment?(text) }
        beginTask()
    }

    private func beginTask() {
        guard let recognizer else { return }
        generation += 1
        let id = generation
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.requiresOnDeviceRecognition = true
        request.addsPunctuation = true
        request.contextualStrings = contextualStrings
        lock.lock(); let old = live; live = request; lock.unlock()
        old?.endAudio()
        task?.cancel()
        lastText = ""
        taskStart = Date()
        self.request = request
        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            DispatchQueue.main.async {
                guard let self, self.running, self.generation == id else { return }
                if let result {
                    let text = result.bestTranscription.formattedString
                    if text != self.lastText { self.lastText = text; self.onPartial?(text) }
                }
                if error != nil || result?.isFinal == true {
                    // Silence timeouts end tasks; keep listening with a fresh one. A task that dies at
                    // once (recognizer busy/unavailable) backs off instead of spinning.
                    if Date().timeIntervalSince(self.taskStart) < 1 {
                        guard !self.retryPending else { return }
                        self.retryPending = true
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                            self.retryPending = false
                            if self.running { self.beginTask() }
                        }
                    } else {
                        self.endSegment()
                    }
                }
            }
        }
    }
}
