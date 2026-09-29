import SwiftUI

// MARK: - Hit regions reported to the window (for click-through outside the glass)

struct HitRegionKey: PreferenceKey {
    static var defaultValue: [String: CGRect] = [:]
    static func reduce(value: inout [String: CGRect], nextValue: () -> [String: CGRect]) {
        value.merge(nextValue()) { $1 }
    }
}

extension View {
    func reportRegion(_ name: String) -> some View {
        background(GeometryReader { proxy in
            Color.clear.preference(key: HitRegionKey.self, value: [name: proxy.frame(in: .global)])
        })
    }
}

enum Layout {
    static let cardWidth: CGFloat = 340
    static let pointerLength: CGFloat = 26
    static let notchWidth: CGFloat = 76
    static let notchFlare: CGFloat = 42
    static let notchCorner: CGFloat = 36
    static let notchTop: CGFloat = 64          // distance below the menu bar
    static let notchInset: CGFloat = 16         // padding inside the body, above/below the gauges
    static let moduleHeight: CGFloat = 98
    static let gap: CGFloat = 8                 // pointer tip ↔ notch
    static var notchHeight: CGFloat { notchFlare * 2 + notchInset * 2 + moduleHeight * CGFloat(Module.allCases.count) }
    static let windowSize = CGSize(width: 24 + cardWidth + pointerLength + gap + notchWidth, height: 700)

    /// Centre of a module's ring, in window coordinates (top-left origin).
    static func gaugeCenterY(_ module: Module) -> CGFloat {
        let index = CGFloat(Module.allCases.firstIndex(of: module) ?? 0)
        return notchTop + notchFlare + notchInset + index * moduleHeight + DockModule.ringTop + DockModule.ringSize / 2
    }
}

// MARK: - Root

struct RootView: View {
    @Bindable var model: AppModel
    var onRegions: ([String: CGRect]) -> Void

    @Namespace private var glass
    @State private var cardHeight: CGFloat = 300
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        GlassEffectContainer(spacing: 8) {
            ZStack(alignment: .topTrailing) {
                if model.isShown, let module = model.activeModule {
                    let geometry = cardGeometry(for: module)
                    card(for: module)
                        .padding(.trailing, Layout.pointerLength)
                        .frame(width: Layout.cardWidth + Layout.pointerLength)
                        .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { cardHeight = $0 }
                        .glassEffect(.regular, in: PointerCardShape(pointerY: geometry.pointerY, pointerLength: Layout.pointerLength))
                        .glassEffectID("card", in: glass)
                        .reportRegion("card")
                        .offset(x: -(Layout.notchWidth + Layout.gap), y: geometry.top)
                        .transition(.asymmetric(
                            insertion: .scale(scale: 0.9, anchor: .trailing).combined(with: .opacity),
                            removal: .scale(scale: 0.94, anchor: .trailing).combined(with: .opacity)
                        ))
                }

                if model.isShown {
                    DockView(model: model)
                        .frame(width: Layout.notchWidth, height: Layout.notchHeight)
                        .glassEffect(.regular, in: SideNotchShape(flare: Layout.notchFlare, cornerRadius: Layout.notchCorner))
                        .glassEffectID("notch", in: glass)
                        .glassEffectTransition(.identity) // the bezel transition below drives it, not a glass morph
                        .reportRegion("dock")
                        .transition(reduceMotion ? .opacity : .bezel)
                        .offset(y: Layout.notchTop)
                }
            }
            .frame(width: Layout.windowSize.width, height: Layout.windowSize.height, alignment: .topTrailing)
        }
        .animation(Motion.pick(reduceMotion, model.isShown ? Motion.emerge : Motion.retract), value: model.isShown)
        .animation(Motion.pick(reduceMotion), value: model.activeModule)
        .animation(Motion.pick(reduceMotion), value: cardHeight)
        .onPreferenceChange(HitRegionKey.self) { onRegions($0) }
        .onExitCommand { withAnimation(Motion.pick(reduceMotion)) { model.close() } }
    }

    /// Vertical placement: centre the card on the gauge, keep it on screen, and aim the pointer at the gauge.
    private func cardGeometry(for module: Module) -> (top: CGFloat, pointerY: CGFloat) {
        let gaugeY = Layout.gaugeCenterY(module)
        let maxTop = Layout.windowSize.height - cardHeight - 8
        let top = min(max(8, gaugeY - cardHeight / 2), max(8, maxTop))
        return (top, gaugeY - top)
    }

    @ViewBuilder
    private func card(for module: Module) -> some View {
        Group {
            switch module {
            case .engine: EngineCard(model: model)
            case .system: SystemCard(model: model)
            case .assistant: AssistantCard(model: model)
            }
        }
        .id(module) // cross-fade content while the glass reshapes
        .transition(.opacity)
    }
}

// MARK: - Bezel transition: the notch grows out of the right screen edge and sinks back into it

private struct BezelEmergeModifier: ViewModifier {
    /// 0 = tucked inside the bezel, 1 = fully out.
    var progress: CGFloat

    func body(content: Content) -> some View {
        content
            // Starts as a thin sliver hugging the bezel, then widens and stretches to full height.
            .scaleEffect(x: 0.2 + 0.8 * progress, y: 0.45 + 0.55 * progress, anchor: .trailing)
            .offset(x: (1 - progress) * Layout.notchWidth * 0.6)
            .blur(radius: (1 - progress) * 10)
            .opacity(Double(min(1, progress * 1.6)))
    }
}

extension AnyTransition {
    static var bezel: AnyTransition {
        .modifier(active: BezelEmergeModifier(progress: 0), identity: BezelEmergeModifier(progress: 1))
    }
}

// MARK: - Notch contents

struct DockView: View {
    @Bindable var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            ForEach(Module.allCases) { module in
                DockModule(model: model, module: module)
                    .frame(height: Layout.moduleHeight, alignment: .top)
                    .reportRegion("module.\(module.rawValue)")
            }
        }
        .padding(.vertical, Layout.notchFlare + Layout.notchInset)
    }
}

struct DockModule: View {
    static let ringSize: CGFloat = 48
    static let ringTop: CGFloat = 6

    @Bindable var model: AppModel
    let module: Module
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var isActive: Bool { model.activeModule == module }

    var body: some View {
        Button {
            withAnimation(Motion.pick(reduceMotion)) {
                if isActive && model.isPinned {
                    model.close()
                } else {
                    model.open(module, pin: true)
                    if module == .assistant { model.focusInputToken += 1 }
                }
            }
        } label: {
            VStack(spacing: 9) {
                gauge
                    .frame(width: Self.ringSize, height: Self.ringSize)
                    .background(
                        Circle()
                            .fill(module.tint.opacity(isActive ? 0.22 : 0))
                            .blur(radius: 10)
                            .scaleEffect(1.25)
                    )
                Text(caption)
                    .font(.system(size: 16, weight: .medium, design: .rounded))
                    .monospacedDigit()
                    .tracking(-0.2)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
            }
            .padding(.top, Self.ringTop)
            .frame(width: Layout.notchWidth)
            .contentShape(Rectangle())
        }
        .buttonStyle(PressableStyle())
        .help(module.title)
        .accessibilityLabel("\(module.title), \(caption)")
    }

    private var caption: String {
        switch module {
        case .engine: return model.engineCaption
        case .system: return "\(model.snapshot.ramPercentage)%"
        case .assistant: return model.assistantCaption
        }
    }

    private var ringTint: Color {
        switch module {
        case .system: return model.snapshot.ramPercentage > 85 ? .red : module.tint
        case .assistant: return model.phase == .listening ? .red : module.tint
        default: return module.tint
        }
    }

    private var ringValue: Double {
        switch module {
        case .engine: return model.engineGauge
        case .system: return model.systemGauge
        case .assistant: return model.phase == .listening ? 0.15 + model.micLevel * 0.85 : (model.engineReady ? 1 : 0.1)
        }
    }

    private var gauge: some View {
        RingGauge(value: ringValue, tint: ringTint, lineWidth: 4.5) {
            Image(systemName: model.phase == .listening && module == .assistant ? "waveform" : module.symbol)
                .font(.system(size: 18, weight: .medium))
                .foregroundStyle(.primary)
                .symbolEffect(.variableColor.iterative, isActive: module == .assistant && model.phase == .listening)
                .symbolEffect(.pulse, isActive: module == .engine && model.phase == .thinking)
        }
    }
}
