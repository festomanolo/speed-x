import AppKit
import Observation
import SwiftUI

enum Module: String, CaseIterable, Identifiable {
    case engine, system, assistant
    var id: String { rawValue }

    var title: String {
        switch self {
        case .engine: return "Decision Engine"
        case .system: return "System"
        case .assistant: return "Assistant"
        }
    }

    /// Each module has its own glyph and hue so they never read as the same thing.
    var symbol: String {
        switch self {
        case .engine: return "brain"
        case .system: return "gauge.with.dots.needle.50percent"
        case .assistant: return "waveform"
        }
    }

    var tint: Color {
        switch self {
        case .engine: return Color(red: 1.00, green: 0.58, blue: 0.20)   // amber
        case .system: return Color(red: 0.20, green: 0.84, blue: 0.62)   // mint
        case .assistant: return Color(red: 0.42, green: 0.55, blue: 1.00) // indigo
        }
    }
}

enum AssistantPhase: Equatable {
    case idle, listening, thinking, done(success: Bool), confirming
}

struct HistoryItem: Identifiable {
    let id = UUID()
    let command: String
    let success: Bool
    let summary: String
    let latencyMs: Double
    let date = Date()
}

@Observable
final class AppModel {
    // Presentation
    /// Whether the side notch is on screen at all (⌘⌥P slides it in and out of the bezel).
    var isShown = true
    var activeModule: Module?
    var isPinned = false
    var focusInputToken = 0

    // Assistant
    var phase: AssistantPhase = .idle
    var inputText = ""
    var transcript = ""
    var preview: [EngineStep] = []
    var response: EngineResponse?
    var errorMessage: String?
    var micLevel: Double = 0
    var lastCommandWasVoice = false
    var awaitingPermission = false
    /// Tokens of an AI answer as they stream in.
    var streamText = ""

    // Engine
    var engineReady = false
    var coreMLState = "off"
    var coreMLEnabled = false
    var computeUnits = "cpu"
    var llmState = "cold"
    var llmModel = ""
    var llmKind = "local"
    var cloudState = "off"
    var history: [HistoryItem] = []

    // System
    var snapshot = SystemStats.shared.getSnapshot()
    var inputDevices: [AudioInputDevice] = []
    var selectedDevice: AudioInputDevice?
    var preferredDeviceUID: String? = AudioDevices.shared.preferredUID
    var launchAtLogin = LaunchAtLoginManager.shared.isEnabled

    /// Last app the user was in before Speed-X (for "close it").
    var lastExternalApp: String?

    @ObservationIgnored private var previewWork: DispatchWorkItem?

    init() {
        refreshDevices()
        AudioDevices.shared.onChange = { [weak self] in self?.refreshDevices() }
        wireSpeech()
        wireEngine()
    }

    // MARK: - Derived values for the dock gauges

    var engineGauge: Double { (response?.confidence ?? 0) }
    var engineCaption: String {
        guard let c = response?.confidence, c > 0 else { return engineReady ? "Ready" : "…" }
        return "\(Int(c * 100))%"
    }
    var systemGauge: Double { Double(snapshot.ramPercentage) / 100 }
    var assistantCaption: String {
        switch phase {
        case .listening: return "Listening"
        case .thinking: return "Thinking"
        case .confirming: return "Confirm"
        default: return selectedDevice?.isBluetooth == true ? "AirPods" : "Ready"
        }
    }

    // MARK: - Presentation

    func open(_ module: Module, pin: Bool) {
        activeModule = module
        if pin { isPinned = true }
    }

    func close() {
        if phase == .listening { SpeechManager.shared.cancel() }
        if phase == .confirming { cancelPending() }
        activeModule = nil
        isPinned = false
    }

    func show() {
        isShown = true
    }

    /// Retract the notch into the bezel, closing any open card first.
    func hide() {
        close()
        isShown = false
    }

    // MARK: - Devices

    func refreshDevices() {
        inputDevices = AudioDevices.shared.inputDevices()
        selectedDevice = AudioDevices.shared.selectedDevice()
    }

    func chooseDevice(uid: String?) {
        AudioDevices.shared.preferredUID = uid
        preferredDeviceUID = uid
        refreshDevices()
    }

    // MARK: - Voice

    func toggleListening() {
        if phase == .listening {
            SpeechManager.shared.stop(.manual)
        } else {
            startListening()
        }
    }

    func startListening() {
        errorMessage = nil
        transcript = ""
        preview = []
        refreshDevices()
        NSSound(named: "Tink")?.play()
        SpeechManager.shared.start()
    }

    private func wireSpeech() {
        let speech = SpeechManager.shared
        speech.onStateChange = { [weak self] recording in
            guard let self else { return }
            if recording {
                self.phase = .listening
            } else if self.phase == .listening {
                self.phase = self.response?.needs_confirmation == true ? .confirming : .idle
            }
        }
        speech.onLevel = { [weak self] level in self?.micLevel = Double(level) }
        speech.onPartial = { [weak self] text in
            self?.transcript = text
            self?.schedulePreview(text)
        }
        speech.onFinal = { [weak self] text in
            self?.lastCommandWasVoice = true
            self?.submit(text)
        }
        speech.onError = { [weak self] message in
            self?.errorMessage = message
            self?.phase = .idle
        }
    }

    // MARK: - Live intent preview (runs the brain on every partial transcript)

    func schedulePreview(_ text: String) {
        previewWork?.cancel()
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        guard trimmed.count > 2 else { preview = []; return }
        let work = DispatchWorkItem { [weak self] in
            EngineClient.shared.preview(trimmed) { resp in
                guard let self, self.phase == .listening || !self.inputText.isEmpty else { return }
                withAnimation(.spring(response: 0.3, dampingFraction: 1)) { self.preview = resp.preview ?? [] }
            }
        }
        previewWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.08, execute: work)
    }

    // MARK: - Commands

    func submitTyped() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        lastCommandWasVoice = false
        inputText = ""
        submit(text)
    }

    func submit(_ command: String) {
        transcript = command
        streamText = ""
        errorMessage = nil
        phase = .thinking
        previewWork?.cancel()
        EngineClient.shared.run(command, frontApp: lastExternalApp) { [weak self] resp in
            self?.receive(resp, command: command)
        }
    }

    func confirmPending() {
        phase = .thinking
        EngineClient.shared.confirm { [weak self] resp in self?.receive(resp, command: self?.transcript ?? "") }
    }

    func cancelPending() {
        EngineClient.shared.cancel { [weak self] _ in
            guard let self else { return }
            withAnimation(.spring(response: 0.35, dampingFraction: 1)) {
                self.response = nil
                self.phase = .idle
                self.preview = []
            }
        }
    }

    private func receive(_ resp: EngineResponse, command: String) {
        streamText = ""
        withAnimation(.spring(response: 0.35, dampingFraction: 1)) {
            response = resp
            preview = []
            if resp.needs_confirmation == true {
                phase = .confirming
            } else {
                phase = .done(success: resp.success ?? false)
            }
        }
        if resp.action != "cancel", resp.needs_confirmation != true {
            let summary = (resp.steps ?? []).map(\.label).joined(separator: " → ")
            history.insert(HistoryItem(command: command, success: resp.success ?? false, summary: summary, latencyMs: resp.latency_ms ?? 0), at: 0)
            if history.count > 12 { history.removeLast() }
        }
        // A spoken sensitive command can be confirmed by voice ("yes" / "ndiyo").
        if resp.needs_confirmation == true, lastCommandWasVoice {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in
                guard self?.phase == .confirming else { return }
                self?.startListening()
            }
        }
    }

    // MARK: - Engine status

    func setCloudKey(_ key: String) {
        EngineClient.shared.setCloudKey(key) { [weak self] resp in self?.applyStatus(resp) }
    }

    func setCoreML(_ enabled: Bool) {
        coreMLEnabled = enabled
        EngineClient.shared.setCoreML(enabled) { [weak self] resp in self?.applyStatus(resp) }
    }

    private func applyStatus(_ resp: EngineResponse) {
        if let s = resp.coreml { coreMLState = s }
        if let e = resp.coreml_enabled { coreMLEnabled = e }
        if let c = resp.compute_units { computeUnits = c }
        if let l = resp.llm { llmState = l }
        if let m = resp.llm_model { llmModel = m }
        if let k = resp.llm_kind { llmKind = k }
        if let c = resp.cloud_llm { cloudState = c }
    }

    private func wireEngine() {
        EngineClient.shared.onPermissionWait = { [weak self] waiting in self?.awaitingPermission = waiting }
        EngineClient.shared.onEvent = { [weak self] event in
            guard let self else { return }
            switch event.event {
            case "ready":
                self.engineReady = true
                self.applyStatus(event)
            case "status":
                self.applyStatus(event)
            case "stream":
                if self.phase == .thinking, let text = event.text { self.streamText = text }
            case "timer_done":
                NSSound(named: "Glass")?.play()
                self.history.insert(HistoryItem(command: "⏰ \(event.label ?? "Timer")", success: true, summary: "Timer finished", latencyMs: 0), at: 0)
            default:
                break
            }
        }
    }

    func refreshStats() {
        snapshot = SystemStats.shared.getSnapshot()
    }
}
