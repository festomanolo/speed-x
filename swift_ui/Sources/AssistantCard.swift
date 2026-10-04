import SwiftUI

struct AssistantCard: View {
    @Bindable var model: AppModel
    @FocusState private var fieldFocused: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private let quickActions: [(String, String, String)] = [
        ("play.fill", "Play music", "play music"),
        ("speaker.wave.2.fill", "Volume up", "volume up"),
        ("timer", "5-min timer", "set a timer for 5 minutes"),
        ("text.viewfinder", "Read screen", "read screen"),
    ]

    private var isLive: Bool { model.phase == .listening || model.phase == .thinking }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            CardHeader(module: .assistant, subtitle: status) {
                if isLive {
                    OrbView(state: model.phase == .listening ? .listening : .working, tint: nil)
                        .frame(width: 24, height: 24)
                        .transition(.opacity)
                }
                IconButton(symbol: "xmark", help: "Close (esc)") { model.close() }
            }

            prompt
                .frame(maxWidth: .infinity, minHeight: 56, alignment: .topLeading)

            if !model.preview.isEmpty && (isLive || !model.inputText.isEmpty) {
                IntentPreview(steps: model.preview)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }

            if model.phase == .thinking && !model.streamText.isEmpty {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Image(systemName: "sparkles").foregroundStyle(Module.assistant.tint)
                    Text(model.streamText)
                        .font(.system(size: 13.5))
                        .fixedSize(horizontal: false, vertical: true)
                        .contentTransition(.opacity)
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.primary.opacity(0.055), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .transition(.opacity)
            }

            if model.awaitingPermission {
                Label("macOS is asking for permission — click “Allow” in the dialog so Speed-X can control that app.", systemImage: "lock.shield.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(Module.assistant.tint)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let error = model.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
                if let pane = privacyPane(for: error) {
                    Button {
                        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?\(pane)")!)
                    } label: {
                        Label("Open Privacy Settings", systemImage: "gearshape")
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .buttonStyle(.glass)
                }
            }

            if let resp = model.response, !isLive {
                ResultView(model: model, resp: resp)
                    .transition(.opacity)
            } else if !isLive && model.inputText.isEmpty && model.errorMessage == nil {
                quickGrid.transition(.opacity)
            }

            controlBar
                .padding(.top, 6)
        }
        .padding(16)
        .background(alignment: .bottom) {
            VoiceAurora(level: model.micLevel, phase: model.phase)
                .frame(height: 150)
                .offset(y: 40)
        }
        .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
        .animation(Motion.pick(reduceMotion), value: model.phase)
        .animation(Motion.pick(reduceMotion), value: model.preview)
        .onAppear {
            fieldFocused = true
            SpeechManager.shared.prewarm()
        }
        .onChange(of: model.focusInputToken) { fieldFocused = true }
        .onChange(of: model.inputText) { _, text in model.schedulePreview(text) }
    }

    private var status: String {
        switch model.phase {
        case .listening: return "Listening · \(model.selectedDevice?.name ?? "microphone")"
        case .thinking: return model.streamText.isEmpty ? "Deciding…" : "Answering…"
        case .confirming: return "Waiting for your OK"
        default: return model.engineReady ? "Ready · ⌥ Space to talk" : "Starting engine…"
        }
    }

    // MARK: - Prompt / transcript

    @ViewBuilder
    private var prompt: some View {
        if isLive {
            Text(model.transcript.isEmpty ? "Listening…" : model.transcript)
                .font(.system(size: 20, weight: .medium))
                .tracking(-0.3)
                .lineSpacing(2)
                .foregroundStyle(model.transcript.isEmpty ? AnyShapeStyle(.secondary) : AnyShapeStyle(.primary))
                .contentTransition(.opacity)
                .fixedSize(horizontal: false, vertical: true)
        } else {
            TextField("Ask Speed-X to do something…", text: $model.inputText, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 20, weight: .medium))
                .tracking(-0.3)
                .lineLimit(1...4)
                .focused($fieldFocused)
                .onSubmit { model.submitTyped() }
        }
    }

    // MARK: - Quick actions

    private var quickGrid: some View {
        LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
            ForEach(quickActions, id: \.2) { symbol, title, command in
                Button {
                    model.lastCommandWasVoice = false
                    model.submit(command)
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: symbol)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(Module.assistant.tint)
                            .frame(width: 16)
                        Text(title)
                            .font(.system(size: 12.5, weight: .medium))
                            .lineLimit(1)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 11)
                    .padding(.vertical, 9)
                    .background(Color.primary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .contentShape(Rectangle())
                }
                .buttonStyle(PressableStyle())
            }
        }
    }

    // MARK: - Bottom controls

    private var controlBar: some View {
        HStack(spacing: 10) {
            Menu {
                Button("Automatic (any mic)") { model.chooseDevice(uid: nil) }
                Divider()
                ForEach(model.inputDevices) { device in
                    Button(device.name) { model.chooseDevice(uid: device.uid) }
                }
            } label: {
                Label(shortDeviceName, systemImage: model.selectedDevice?.symbol ?? "mic.slash")
                    .font(.system(size: 12, weight: .medium))
            }
            .menuStyle(.button)
            .buttonStyle(.glass)
            .controlSize(.regular)
            .fixedSize()
            .help("Microphone")

            Spacer(minLength: 0)

            if !model.inputText.trimmingCharacters(in: .whitespaces).isEmpty {
                Button { model.submitTyped() } label: {
                    Image(systemName: "arrow.up")
                        .font(.system(size: 15, weight: .bold))
                        .frame(width: 34, height: 34)
                }
                .buttonStyle(.glassProminent)
                .buttonBorderShape(.circle)
                .tint(Module.assistant.tint)
                .keyboardShortcut(.return, modifiers: [])
                .transition(.scale.combined(with: .opacity))
            }

            MicButton(model: model)
        }
    }

    private func privacyPane(for error: String) -> String? {
        if error.contains("Speech Recognition") { return "Privacy_SpeechRecognition" }
        if error.contains("Microphone access") { return "Privacy_Microphone" }
        return nil
    }

    private var shortDeviceName: String {
        guard let name = model.selectedDevice?.name else { return "No mic" }
        return name.count > 16 ? String(name.prefix(15)) + "…" : name
    }
}

// MARK: - Mic button

struct MicButton: View {
    @Bindable var model: AppModel

    private var listening: Bool { model.phase == .listening }

    var body: some View {
        Button { model.toggleListening() } label: {
            ZStack {
                Circle()
                    .stroke((listening ? Color.red : Module.assistant.tint).opacity(0.35), lineWidth: 3)
                    .scaleEffect(listening ? 1.12 + model.micLevel * 0.35 : 1)
                    .opacity(listening ? 1 : 0)
                    .animation(.spring(response: 0.18, dampingFraction: 0.9), value: model.micLevel)
                Circle()
                    .fill(listening ? Color.red : Module.assistant.tint)
                    .shadow(color: (listening ? Color.red : Module.assistant.tint).opacity(0.45), radius: 10, y: 3)
                Image(systemName: listening ? "stop.fill" : "mic.fill")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(.white)
                    .contentTransition(.symbolEffect(.replace))
            }
            .frame(width: 46, height: 46)
            .contentShape(Circle())
        }
        .buttonStyle(PressableStyle())
        .help(listening ? "Stop listening" : "Talk (⌥ Space)")
        .accessibilityLabel(listening ? "Stop listening" : "Start listening")
    }
}

// MARK: - Live intent preview

struct IntentPreview: View {
    let steps: [EngineStep]

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "sparkles")
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(Module.engine.tint)
            ForEach(Array(steps.enumerated()), id: \.offset) { index, step in
                if index > 0 {
                    Image(systemName: "arrow.right").font(.system(size: 9, weight: .bold)).foregroundStyle(.tertiary)
                }
                Text(step.label)
                    .font(.system(size: 11.5, weight: .semibold))
                    .lineLimit(1)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Module.engine.tint.opacity(0.16), in: Capsule())
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Will do: " + steps.map(\.label).joined(separator: ", then "))
    }
}

// MARK: - Result

struct ResultView: View {
    @Bindable var model: AppModel
    let resp: EngineResponse

    private var ok: Bool { resp.success ?? false }
    private var confirming: Bool { resp.needs_confirmation == true }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let steps = resp.steps, steps.count > 1, !confirming {
                VStack(alignment: .leading, spacing: 7) {
                    ForEach(Array(steps.enumerated()), id: \.offset) { i, step in
                        StepRow(index: i + 1, step: step)
                    }
                }
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Image(systemName: confirming ? "hand.raised.fill" : (ok ? "checkmark.circle.fill" : "questionmark.circle.fill"))
                        .foregroundStyle(confirming ? Color.red : (ok ? Color.green : Color.orange))
                    Text(resp.message ?? "")
                        .font(.system(size: 13.5))
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                }
            }

            if confirming {
                HStack(spacing: 8) {
                    Button("Cancel") { model.cancelPending() }
                        .buttonStyle(.glass)
                        .keyboardShortcut(.cancelAction)
                    Button("Confirm") { model.confirmPending() }
                        .buttonStyle(.glassProminent)
                        .tint(.red)
                        .keyboardShortcut(.defaultAction)
                    Spacer()
                    Text("or say “yes”")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                }
                .controlSize(.regular)
            } else if let suggestion = resp.suggestion {
                Button {
                    model.submit(suggestion)
                } label: {
                    Label("Run “\(suggestion)”", systemImage: "arrow.turn.down.right")
                        .font(.system(size: 12, weight: .semibold))
                }
                .buttonStyle(.glass)
            }

            if let latency = resp.latency_ms, !confirming, latency > 0 {
                Text("\(latency < 1000 ? "\(Int(latency)) ms" : String(format: "%.1f s", latency / 1000)) · \(sourceName)")
                    .font(.system(size: 10.5).monospacedDigit())
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.primary.opacity(0.055), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private var sourceName: String {
        switch resp.source {
        case "rules", "heuristic": return "rules"
        case "semantic": return "semantic match"
        case "coreml": return "Core ML"
        case "llm": return "local AI"
        default: return "no match"
        }
    }
}
