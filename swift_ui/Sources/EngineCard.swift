import SwiftUI

struct EngineCard: View {
    @Bindable var model: AppModel
    @State private var keyDraft = ""
    @State private var editingKey = false

    private var resp: EngineResponse? { model.response }
    private let layers = [("Normalize", "text.badge.checkmark"), ("Rules", "list.bullet.rectangle"), ("Semantic", "point.3.connected.trianglepath.dotted"), ("Local AI", "sparkles")]

    private var usedLayer: String? {
        switch resp?.source {
        case "rules", "heuristic": return "Rules"
        case "semantic": return "Semantic"
        case "coreml": return nil
        case "llm": return "Local AI"
        default: return nil
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            CardHeader(module: .engine, subtitle: model.engineReady ? "On-device · warm" : "Starting engine…") {
                IconButton(symbol: "xmark", help: "Close") { model.close() }
            }

            // Last decision
            CardSection(title: "Last decision") {
                if let resp, let steps = resp.steps, !steps.isEmpty {
                    if let cmd = resp.command {
                        Text("“\(cmd)”")
                            .font(.system(size: 13, weight: .medium))
                            .lineLimit(2)
                    }
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array(steps.enumerated()), id: \.offset) { index, step in
                            StepRow(index: steps.count > 1 ? index + 1 : nil, step: step)
                        }
                    }
                } else {
                    Text("No commands yet. Press ⌥ Space and speak.")
                        .font(.system(size: 12.5))
                        .foregroundStyle(.secondary)
                }
            }

            HStack(spacing: 8) {
                StatTile(title: "Latency", value: resp?.latency_ms.map { $0 < 1000 ? "\(Int($0)) ms" : String(format: "%.1f s", $0 / 1000) } ?? "—")
                StatTile(title: "Confidence", value: resp?.confidence.map { $0 > 0 ? "\(Int($0 * 100))%" : "—" } ?? "—", tint: Module.engine.tint)
                StatTile(title: "Steps", value: "\(resp?.steps?.count ?? 0)")
            }

            // Decision pipeline
            CardSection(title: "Pipeline") {
                HStack(spacing: 4) {
                    ForEach(Array(layers.enumerated()), id: \.offset) { index, layer in
                        let used = layer.0 == usedLayer || (layer.0 == "Normalize" && usedLayer != nil)
                        let disabled = layer.0 == "Local AI" && model.llmState != "ready" && model.llmState != "warming"
                        VStack(spacing: 4) {
                            Image(systemName: layer.1)
                                .font(.system(size: 12, weight: .semibold))
                            Text(layer.0)
                                .font(.system(size: 9.5, weight: .semibold))
                                .lineLimit(1)
                                .minimumScaleFactor(0.8)
                        }
                        .foregroundStyle(used ? Module.engine.tint : Color.secondary.opacity(disabled ? 0.45 : 1))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 7)
                        .background(used ? Module.engine.tint.opacity(0.16) : Color.clear, in: RoundedRectangle(cornerRadius: 9, style: .continuous))
                        if index < layers.count - 1 {
                            Image(systemName: "chevron.compact.right")
                                .font(.system(size: 10))
                                .foregroundStyle(.tertiary)
                        }
                    }
                }
                HStack(spacing: 8) {
                    Circle().fill(llmColor).frame(width: 7, height: 7)
                    VStack(alignment: .leading, spacing: 1) {
                        Text("\(model.llmKind == "cloud" ? "Claude" : "Local AI") · \(model.llmModel.isEmpty ? "Ollama" : model.llmModel)").font(.system(size: 12.5, weight: .medium))
                        Text(llmDescription).font(.system(size: 10.5)).foregroundStyle(.secondary)
                    }
                }
                cloudKeyRow
                Toggle(isOn: Binding(get: { model.coreMLEnabled }, set: { model.setCoreML($0) })) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Core ML fallback").font(.system(size: 12.5, weight: .medium))
                        Text(coreMLDescription).font(.system(size: 10.5)).foregroundStyle(.secondary)
                    }
                }
                .toggleStyle(.switch)
                .controlSize(.small)
                .tint(Module.engine.tint)
            }

            if !model.history.isEmpty {
                CardSection(title: "Recent") {
                    VStack(alignment: .leading, spacing: 5) {
                        ForEach(model.history.prefix(4)) { item in
                            HStack(spacing: 7) {
                                Circle().fill(item.success ? Color.green : Color.orange).frame(width: 6, height: 6)
                                Text(item.command).font(.system(size: 12)).lineLimit(1)
                                Spacer(minLength: 4)
                                if item.latencyMs > 0 {
                                    Text("\(Int(item.latencyMs)) ms").font(.system(size: 10.5).monospacedDigit()).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
        }
        .padding(16)
    }

    @ViewBuilder
    private var cloudKeyRow: some View {
        if editingKey {
            HStack(spacing: 6) {
                SecureField("sk-ant-…", text: $keyDraft)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 11.5))
                    .onSubmit(saveKey)
                Button("Save", action: saveKey).controlSize(.small)
                Button("Cancel") { editingKey = false; keyDraft = "" }.controlSize(.small)
            }
        } else {
            HStack {
                Text(cloudDescription).font(.system(size: 10.5)).foregroundStyle(.secondary)
                Spacer()
                Button(model.cloudState == "off" ? "Add Claude key" : "Change") { editingKey = true }
                    .controlSize(.small)
                if model.cloudState != "off" {
                    Button("Remove") { model.setCloudKey("") }.controlSize(.small)
                }
            }
        }
    }

    private func saveKey() {
        model.setCloudKey(keyDraft)
        keyDraft = ""
        editingKey = false
    }

    private var cloudDescription: String {
        switch model.cloudState {
        case "ready": return "Claude answers first; local model if offline"
        case "bad_key": return "Claude key was rejected — check it"
        case "offline": return "Claude unreachable — using local model"
        default: return "Optional: Claude for fast, accurate answers online"
        }
    }

    private var llmColor: Color {
        switch model.llmState {
        case "ready": return .green
        case "warming", "cold": return .yellow
        default: return .orange
        }
    }

    private var llmDescription: String {
        switch model.llmState {
        case "ready": return model.llmKind == "cloud" ? "Plans and answers anything the rules don't know" : "Plans anything the rules don't know · offline"
        case "warming": return "Loading model…"
        case "missing": return "Run: ollama pull \(model.llmModel)"
        case "off": return "Disabled"
        default: return "Ollama isn't running — open Ollama.app"
        }
    }

    private var coreMLDescription: String {
        switch model.coreMLState {
        case "ready": return "Loaded · \(model.computeUnits) · used when unsure"
        case "warming", "cold": return "Loading model in background…"
        case "missing": return "Model weights not downloaded"
        case "error": return "Model failed to load on this Mac"
        default: return "Off — slow on Intel CPUs (2–8 s)"
        }
    }
}

struct StepRow: View {
    let index: Int?
    let step: EngineStep

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 7) {
            Image(systemName: step.success == false ? "xmark.circle.fill" : "checkmark.circle.fill")
                .font(.system(size: 11))
                .foregroundStyle(step.success == false ? Color.orange : Color.green)
            VStack(alignment: .leading, spacing: 2) {
                Text(index.map { "\($0). \(step.label)" } ?? step.label)
                    .font(.system(size: 12.5, weight: .semibold))
                if let message = step.message, !message.isEmpty {
                    Text(message)
                        .font(.system(size: 11.5))
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                }
            }
            Spacer(minLength: 4)
            Pill(text: "\(Int(step.confidence * 100))%", tint: Module.engine.tint)
        }
    }
}
