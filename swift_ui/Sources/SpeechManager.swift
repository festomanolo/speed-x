import AVFoundation
import AudioToolbox
import Foundation
import Speech

/// Streams the selected microphone (any mic; see AudioDevices for the automatic order) into on-device
/// speech recognition and decides when the user has finished speaking.
///
/// Endpointing: once speech has been heard, the command is committed after
/// `silenceWindow` seconds without new words *and* with a quiet mic. That is ~3x faster
/// than the previous fixed 2.2s timer while not cutting people off mid-sentence.
final class SpeechManager: NSObject {
    static let shared = SpeechManager()

    enum StopReason { case endOfSpeech, manual, cancelled, error(String) }

    // Callbacks (always delivered on the main thread)
    var onPartial: ((String) -> Void)?
    var onFinal: ((String) -> Void)?
    var onStateChange: ((Bool) -> Void)?
    var onLevel: ((Float) -> Void)?
    var onError: ((String) -> Void)?

    private(set) var isRecording = false
    private(set) var activeDeviceName: String?

    /// Seconds of silence after speech that ends the command.
    var silenceWindow: TimeInterval = 0.8
    private let noSpeechTimeout: TimeInterval = 7.0
    private let maxDuration: TimeInterval = 20.0

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var engine: AVAudioEngine?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var endpointTimer: Timer?
    private var configObserver: NSObjectProtocol?

    private var transcript = ""
    private var lastPartialAt = Date.distantPast
    private var startedAt = Date()
    private var heardSpeech = false
    private var recentLevel: Float = 0
    private var peakRMS: Float = 0
    private var delivered = false
    private var lastToggle = Date.distantPast
    private var isWarming = false
    private var lastWarm = Date.distantPast
    private var warmTask: SFSpeechRecognitionTask?
    /// Bumped on every start so late callbacks from an earlier session (or its recognition
    /// task finishing after stop) can't end the session that is running now.
    private var session = 0
    private var audioStartedAt = Date()
    private var audioRestarts = 0
    private var usedOnDevice = false
    private var retriedServer = false
    /// The tap runs on the audio thread; the request can be swapped from main (retry).
    private let requestLock = NSLock()
    private var liveRequest: SFSpeechAudioBufferRecognitionRequest?

    /// Vocabulary hints: app names, bilingual command words.
    var contextualStrings: [String] = [
        "Speed X", "Safari", "Spotify", "WhatsApp", "Visual Studio Code", "Xcode", "Telegram", "YouTube", "GitHub",
        "cheza muziki", "simamisha", "ongeza sauti", "punguza sauti", "nyamazisha", "fungua", "funga kioo",
        "andika note", "tuma email", "tafuta", "nikumbushe", "saa ngapi", "dakika", "weka timer", "anza coding",
        "volume up", "volume down", "set a timer", "remind me", "take a screenshot", "read my screen", "clipboard",
    ]

    func requestPermissions(completion: @escaping (Bool) -> Void) {
        SFSpeechRecognizer.requestAuthorization { status in
            AVCaptureDevice.requestAccess(for: .audio) { mic in
                DispatchQueue.main.async { completion(status == .authorized && mic) }
            }
        }
    }

    /// The on-device model takes 5-13s to load on Intel Macs. Feeding it half a second of
    /// silence at launch (and when the assistant opens) keeps the first real command instant.
    func prewarm() {
        guard !isRecording, !isWarming,
              SFSpeechRecognizer.authorizationStatus() == .authorized,
              let recognizer, recognizer.isAvailable,
              Date().timeIntervalSince(lastWarm) > 120,
              let format = AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 8_000) else { return }
        isWarming = true
        buffer.frameLength = 8_000 // zero-filled = silence
        let request = SFSpeechAudioBufferRecognitionRequest()
        if recognizer.supportsOnDeviceRecognition { request.requiresOnDeviceRecognition = true }
        request.contextualStrings = contextualStrings
        request.append(buffer)
        request.endAudio()
        warmTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
            guard result?.isFinal == true || error != nil else { return }
            DispatchQueue.main.async {
                self?.isWarming = false
                self?.lastWarm = Date()
                self?.warmTask = nil
            }
        }
    }

    func toggle() {
        guard Date().timeIntervalSince(lastToggle) > 0.3 else { return }
        lastToggle = Date()
        if isRecording { stop(.manual) } else { start() }
    }

    // MARK: - Start

    func start() {
        guard !isRecording else { return }
        switch SFSpeechRecognizer.authorizationStatus() {
        case .authorized: break
        case .notDetermined:
            requestPermissions { [weak self] ok in if ok { self?.start() } }
            return
        default:
            fail("Speech recognition is off. Enable Speed-X in System Settings › Privacy & Security › Speech Recognition.")
            return
        }
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: break
        case .notDetermined:
            requestPermissions { [weak self] ok in if ok { self?.start() } }
            return
        default:
            fail("Microphone access is off. Enable Speed-X in System Settings › Privacy & Security › Microphone.")
            return
        }
        guard let recognizer, recognizer.isAvailable else {
            fail("Speech recognizer is unavailable right now.")
            return
        }

        let engine = AVAudioEngine()
        let input = engine.inputNode

        // Route the engine to the chosen device (AirPods) instead of the broken built-in mic.
        let device = AudioDevices.shared.selectedDevice()
        if let device, let unit = input.audioUnit {
            var id = device.id
            let status = AudioUnitSetProperty(
                unit, kAudioOutputUnitProperty_CurrentDevice, kAudioUnitScope_Global, 0,
                &id, UInt32(MemoryLayout<AudioDeviceID>.size)
            )
            if status != noErr { print("SpeechManager: couldn't select \(device.name) (\(status))") }
        }
        activeDeviceName = device?.name

        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            fail("No usable microphone. Connect your AirPods or choose an input in System ▸ Microphone.")
            return
        }

        // A prewarm still running would compete with this session's recognition task.
        warmTask?.cancel()
        warmTask = nil
        isWarming = false

        session += 1
        transcript = ""
        heardSpeech = false
        delivered = false
        peakRMS = 0
        recentLevel = 0
        audioRestarts = 0
        retriedServer = false
        startedAt = Date()
        audioStartedAt = Date()
        lastPartialAt = Date()

        installTap(on: input, format: format)
        do {
            engine.prepare()
            try engine.start()
        } catch {
            input.removeTap(onBus: 0)
            fail("Microphone failed to start: \(error.localizedDescription)")
            return
        }

        self.engine = engine
        beginRecognition(onDevice: recognizer.supportsOnDeviceRecognition)

        // Starting the mic on AirPods switches them to the headset profile, which reconfigures
        // the engine right away. Re-attach to the new format instead of ending the command.
        configObserver = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main
        ) { [weak self] _ in
            self?.restartAudio()
        }

        isRecording = true
        onStateChange?(true)
        endpointTimer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in self?.tick() }
        RunLoop.main.add(endpointTimer!, forMode: .common)
    }

    private func installTap(on input: AVAudioInputNode, format: AVAudioFormat) {
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            guard let self else { return }
            self.requestLock.lock()
            let request = self.liveRequest
            self.requestLock.unlock()
            request?.append(buffer)
            self.measure(buffer)
        }
    }

    private func beginRecognition(onDevice: Bool) {
        guard let recognizer else { return }
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.taskHint = .search
        request.addsPunctuation = false
        request.contextualStrings = contextualStrings
        request.requiresOnDeviceRecognition = onDevice
        usedOnDevice = onDevice

        requestLock.lock()
        let old = liveRequest
        liveRequest = request
        requestLock.unlock()
        old?.endAudio()
        task?.cancel()

        self.request = request
        let id = session
        self.task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            DispatchQueue.main.async {
                guard let self, self.session == id, self.request === request else { return }
                self.handle(result: result, error: error)
            }
        }
    }

    private func restartAudio() {
        guard isRecording, let engine else { return }
        guard audioRestarts < 4 else {
            stop(heardSpeech ? .endOfSpeech : .error("The microphone keeps changing. Try again, or pick another input in System ▸ Microphone."))
            return
        }
        audioRestarts += 1
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        let format = engine.inputNode.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            stop(heardSpeech ? .endOfSpeech : .error("The microphone disconnected."))
            return
        }
        installTap(on: engine.inputNode, format: format)
        do {
            engine.prepare()
            try engine.start()
        } catch {
            stop(heardSpeech ? .endOfSpeech : .error("Microphone failed to restart: \(error.localizedDescription)"))
            return
        }
        // Give the new route a moment before deciding it's silent.
        audioStartedAt = Date()
        peakRMS = 0
    }

    // MARK: - Audio metering

    private func measure(_ buffer: AVAudioPCMBuffer) {
        guard let channel = buffer.floatChannelData?[0] else { return }
        let frames = Int(buffer.frameLength)
        guard frames > 0 else { return }
        var sum: Float = 0
        var i = 0
        while i < frames { let s = channel[i]; sum += s * s; i += 2 }
        let rms = sqrt(sum / Float(max(1, frames / 2)))
        let db = 20 * log10(max(rms, 0.000_01))
        let level = max(0, min(1, (db + 50) / 42))
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.peakRMS = max(self.peakRMS, rms)
            self.recentLevel = self.recentLevel * 0.6 + level * 0.4
            self.onLevel?(level)
        }
    }

    // MARK: - Recognition + endpointing

    private func handle(result: SFSpeechRecognitionResult?, error: Error?) {
        guard isRecording else { return }
        if let result {
            let text = result.bestTranscription.formattedString
            if !text.isEmpty, text != transcript {
                transcript = text
                heardSpeech = true
                lastPartialAt = Date()
                onPartial?(text)
            }
            if result.isFinal { stop(.endOfSpeech); return }
        }
        if let error {
            // "No speech detected" arrives as an error; treat as end of speech when we have text.
            if !transcript.isEmpty { stop(.endOfSpeech); return }
            let ns = error as NSError
            let noSpeech = ns.code == 1110 || ns.code == 203
            let cancelled = ns.code == 216 || ns.code == 301 || ns.domain == NSCocoaErrorDomain && ns.code == NSUserCancelledError
            if cancelled { return } // our own restart/retry; a newer task is running
            if noSpeech, Date().timeIntervalSince(startedAt) > 2 { stop(.cancelled); return }
            // The on-device model can fail to load (missing asset, busy daemon): retry once on the
            // regular recognizer rather than ending the command the moment it started.
            if usedOnDevice, !retriedServer {
                retriedServer = true
                beginRecognition(onDevice: false)
                return
            }
            stop(.error("Speech recognition stopped: \(error.localizedDescription)"))
        }
    }

    private func tick() {
        guard isRecording else { return }
        let now = Date()
        let elapsed = now.timeIntervalSince(startedAt)

        if heardSpeech {
            let quietFor = now.timeIntervalSince(lastPartialAt)
            // Quiet mic ends it quickly; if there's still sound but no new words, give it a bit longer.
            if (quietFor >= silenceWindow && recentLevel < 0.35) || quietFor >= silenceWindow * 2.2 {
                stop(.endOfSpeech)
                return
            }
        } else {
            if now.timeIntervalSince(audioStartedAt) > 3.0 && peakRMS < 0.000_05 {
                let name = activeDeviceName ?? "the microphone"
                stop(.error("No audio coming from \(name). Connect your AirPods or pick another input."))
                return
            }
            if elapsed > noSpeechTimeout { stop(.cancelled); return }
        }
        if elapsed > maxDuration { stop(.endOfSpeech) }
    }

    // MARK: - Stop

    func stop(_ reason: StopReason) {
        guard isRecording else { return }
        isRecording = false
        endpointTimer?.invalidate()
        endpointTimer = nil
        if let configObserver { NotificationCenter.default.removeObserver(configObserver) }
        configObserver = nil

        engine?.stop()
        engine?.inputNode.removeTap(onBus: 0)
        requestLock.lock()
        liveRequest = nil
        requestLock.unlock()
        request?.endAudio()
        task?.finish()
        engine = nil
        request = nil
        task = nil

        onLevel?(0)
        onStateChange?(false)

        let text = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        switch reason {
        case .endOfSpeech, .manual:
            if !text.isEmpty, !delivered {
                delivered = true
                onFinal?(text)
            }
        case .cancelled:
            break
        case .error(let message):
            onError?(message)
        }
    }

    func cancel() { stop(.cancelled) }

    private func fail(_ message: String) {
        DispatchQueue.main.async { self.onError?(message) }
    }
}
