import Foundation
import Speech
import AVFoundation

class SpeechManager: NSObject, SFSpeechRecognizerDelegate {
    static let shared = SpeechManager()

    private let speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let audioEngine = AVAudioEngine()

    private(set) var isRecording: Bool = false
    private var silenceTimer: Timer?

    var onSpeechPartial: ((String) -> Void)?
    var onSpeechFinished: ((String) -> Void)?
    var onStateChange: ((Bool) -> Void)?
    var onAudioLevel: ((Float) -> Void)?
    private(set) var currentAudioLevel: Float = 0.0

    override init() {
        super.init()
        speechRecognizer?.delegate = self
    }

    func requestPermissions(completion: @escaping (Bool) -> Void) {
        SFSpeechRecognizer.requestAuthorization { authStatus in
            AVCaptureDevice.requestAccess(for: .audio) { micGranted in
                DispatchQueue.main.async {
                    let speechGranted = (authStatus == .authorized)
                    completion(speechGranted && micGranted)
                }
            }
        }
    }

    private var lastToggleTime: Date = Date.distantPast

    func toggleRecording() {
        let now = Date()
        guard now.timeIntervalSince(lastToggleTime) > 0.4 else { return }
        lastToggleTime = now

        if isRecording {
            stopRecording(shouldExecute: true)
        } else {
            startRecording()
        }
    }

    func startRecording() {
        guard !isRecording else { return }

        if SFSpeechRecognizer.authorizationStatus() != .authorized {
            SFSpeechRecognizer.requestAuthorization { [weak self] status in
                if status == .authorized {
                    DispatchQueue.main.async {
                        self?.startRecording()
                    }
                }
            }
            return
        }

        // Cancel any lingering tasks
        recognitionTask?.cancel()
        recognitionTask = nil

        let inputNode = audioEngine.inputNode
        let recordingFormat = inputNode.outputFormat(forBus: 0)

        // Make sure audio format is valid
        guard recordingFormat.sampleRate > 0 else {
            print("SpeechManager: Invalid microphone format")
            return
        }

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true

        // Enforce on-device recognition if supported for 100% offline privacy
        if let recognizer = speechRecognizer, recognizer.supportsOnDeviceRecognition {
            request.requiresOnDeviceRecognition = true
        }

        self.recognitionRequest = request

        recognitionTask = speechRecognizer?.recognitionTask(with: request) { [weak self] result, error in
            guard let self = self else { return }

            if let result = result {
                let text = result.bestTranscription.formattedString
                DispatchQueue.main.async {
                    self.onSpeechPartial?(text)
                }

                // Reset silence timer on every new speech piece
                self.resetSilenceTimer(text: text)

                if result.isFinal {
                    self.stopRecording(shouldExecute: true)
                }
            }

            if error != nil {
                self.stopRecording(shouldExecute: false)
            }
        }

        inputNode.removeTap(onBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { [weak self] buffer, _ in
            guard let self = self else { return }
            self.recognitionRequest?.append(buffer)

            // Live audio power computation for Gemini Live spectrometer
            if let channelData = buffer.floatChannelData?[0] {
                let frames = Int(buffer.frameLength)
                var sum: Float = 0
                let strideStep = 4
                var count = 0
                for i in stride(from: 0, to: frames, by: strideStep) {
                    let s = channelData[i]
                    sum += s * s
                    count += 1
                }
                let rms = sqrt(sum / Float(max(1, count)))
                let db = 20 * log10(max(rms, 0.0001))
                // Scale voice decibels (-45 dB to -5 dB) into 0.0 ... 1.0
                let normalized = max(0.0, min(1.0, (db + 45.0) / 40.0))
                DispatchQueue.main.async {
                    self.currentAudioLevel = normalized
                    self.onAudioLevel?(normalized)
                }
            }
        }

        audioEngine.prepare()
        do {
            try audioEngine.start()
            isRecording = true
            DispatchQueue.main.async {
                self.onStateChange?(true)
            }
        } catch {
            print("SpeechManager: AudioEngine start failed:", error)
            DispatchQueue.main.async {
                self.stopRecording(shouldExecute: false)
            }
        }
    }

    func stopRecording(shouldExecute: Bool) {
        guard isRecording else { return }

        silenceTimer?.invalidate()
        silenceTimer = nil

        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionRequest?.endAudio()

        let finalText = recognitionTask?.error == nil ? (recognitionRequest != nil ? "" : "") : ""

        recognitionRequest = nil
        recognitionTask = nil
        isRecording = false
        currentAudioLevel = 0.0

        DispatchQueue.main.async { [weak self] in
            self?.onAudioLevel?(0.0)
            self?.onStateChange?(false)
            if shouldExecute {
                self?.onSpeechFinished?(finalText)
            }
        }
    }

    private func resetSilenceTimer(text: String) {
        silenceTimer?.invalidate()
        // If user pauses speaking for 2.2 seconds, automatically conclude recording and dispatch
        silenceTimer = Timer.scheduledTimer(withTimeInterval: 2.2, repeats: false) { [weak self] _ in
            guard let self = self, self.isRecording else { return }
            self.stopRecording(shouldExecute: true)
        }
    }
}
