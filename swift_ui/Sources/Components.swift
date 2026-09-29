import AppKit
import SwiftUI

// MARK: - Motion

enum Motion {
    /// Critically damped default: no overshoot for things that simply appear.
    static let standard = Animation.spring(response: 0.36, dampingFraction: 1.0)
    /// Slight give, reserved for direct presses.
    static let press = Animation.spring(response: 0.25, dampingFraction: 0.8)
    /// The notch growing out of the bezel: a little give so it lands like a physical object.
    static let emerge = Animation.spring(response: 0.52, dampingFraction: 0.78)
    /// Retracting into the bezel: quicker and without overshoot.
    static let retract = Animation.spring(response: 0.34, dampingFraction: 1.0)

    static func pick(_ reduceMotion: Bool, _ animation: Animation = standard) -> Animation {
        reduceMotion ? .easeInOut(duration: 0.18) : animation
    }
}

// MARK: - Ring gauge

struct RingGauge<Center: View>: View {
    var value: Double
    var tint: Color
    var lineWidth: CGFloat = 3.5
    @ViewBuilder var center: () -> Center

    var body: some View {
        ZStack {
            Circle().stroke(Color.primary.opacity(0.12), lineWidth: lineWidth)
            Circle()
                .trim(from: 0, to: max(0.001, min(1, value)))
                .stroke(
                    AngularGradient(colors: [tint.opacity(0.65), tint], center: .center, startAngle: .degrees(0), endAngle: .degrees(360 * max(0.05, value))),
                    style: StrokeStyle(lineWidth: lineWidth, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
                .animation(.spring(response: 0.6, dampingFraction: 1), value: value)
            center()
        }
    }
}

// MARK: - Card header

struct CardHeader<Trailing: View>: View {
    let module: Module
    let subtitle: String
    @ViewBuilder var trailing: () -> Trailing

    var body: some View {
        HStack(spacing: 11) {
            ModuleBadge(module: module, size: 32)
            VStack(alignment: .leading, spacing: 1) {
                Text(module.title)
                    .font(.system(size: 15, weight: .semibold))
                    .tracking(-0.2)
                Text(subtitle)
                    .font(.system(size: 11.5))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            trailing()
        }
    }
}

/// Solid colour badge (colour lives on a solid layer, not on the translucent glass).
struct ModuleBadge: View {
    let module: Module
    var size: CGFloat

    var body: some View {
        RoundedRectangle(cornerRadius: size * 0.3, style: .continuous)
            .fill(LinearGradient(colors: [module.tint, module.tint.opacity(0.72)], startPoint: .top, endPoint: .bottom))
            .frame(width: size, height: size)
            .overlay(
                Image(systemName: module.symbol)
                    .font(.system(size: size * 0.46, weight: .semibold))
                    .foregroundStyle(.white)
            )
            .shadow(color: module.tint.opacity(0.35), radius: 6, y: 2)
    }
}

// MARK: - Inner section (a quiet fill, never glass-on-glass)

struct CardSection<Content: View>: View {
    var title: String?
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let title {
                Text(title.uppercased())
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.6)
                    .foregroundStyle(.secondary)
            }
            content()
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.primary.opacity(0.055), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Color.primary.opacity(0.07), lineWidth: 0.5))
    }
}

struct StatTile: View {
    let title: String
    let value: String
    var tint: Color = .primary

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 10.5, weight: .medium))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 17, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 9)
        .padding(.horizontal, 11)
        .background(Color.primary.opacity(0.055), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

struct Pill: View {
    let text: String
    var symbol: String?
    var tint: Color = .secondary

    var body: some View {
        HStack(spacing: 4) {
            if let symbol { Image(systemName: symbol).font(.system(size: 9, weight: .bold)) }
            Text(text).font(.system(size: 10.5, weight: .semibold))
        }
        .foregroundStyle(tint)
        .padding(.horizontal, 7)
        .padding(.vertical, 3)
        .background(tint.opacity(0.14), in: Capsule())
    }
}

/// Small circular icon button with immediate press feedback.
struct IconButton: View {
    let symbol: String
    var size: CGFloat = 26
    var help: String = ""
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: size * 0.42, weight: .semibold))
                .frame(width: size, height: size)
                .background(Color.primary.opacity(0.08), in: Circle())
                .contentShape(Circle())
        }
        .buttonStyle(PressableStyle())
        .help(help)
    }
}

struct PressableStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.93 : 1)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .animation(Motion.press, value: configuration.isPressed)
    }
}

// MARK: - Thinking orb bridge

struct OrbView: NSViewRepresentable {
    var state: OrbState
    var tint: NSColor?

    func makeNSView(context: Context) -> ThinkingOrbView {
        let v = ThinkingOrbView(frame: .zero)
        v.state = state
        v.tintColor = tint
        return v
    }

    func updateNSView(_ view: ThinkingOrbView, context: Context) {
        view.state = state
        view.tintColor = tint
    }
}

// MARK: - Voice aurora

/// Sound-reactive light that blooms up from the bottom of the assistant card.
/// Paused (a single static frame) when nothing is happening to keep the CPU idle.
struct VoiceAurora: View {
    var level: Double
    var phase: AssistantPhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var scheme

    private var active: Bool { phase == .listening || phase == .thinking }

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: !active || reduceMotion)) { timeline in
            let t = timeline.date.timeIntervalSinceReferenceDate
            Canvas { ctx, size in
                let energy: Double
                switch phase {
                case .listening: energy = 0.35 + level * 0.9
                case .thinking: energy = 0.45 + 0.15 * sin(t * 3)
                case .done(let ok): energy = ok ? 0.28 : 0.22
                default: energy = 0.18
                }
                let blobs: [(Color, Double, Double, Double)] = phase == .done(success: false)
                    ? [(.orange, 0.3, 0.9, 0.0), (.red, 0.7, 1.1, 1.3), (.pink, 0.5, 0.8, 2.6)]
                    : [(Color(red: 0.25, green: 0.45, blue: 1.0), 0.22, 0.9, 0.0),
                       (Color(red: 0.0, green: 0.85, blue: 0.95), 0.5, 1.2, 1.7),
                       (Color(red: 0.62, green: 0.32, blue: 1.0), 0.78, 1.0, 3.1),
                       (Color(red: 1.0, green: 0.35, blue: 0.7), 0.62, 0.7, 4.4)]
                for (color, x, speed, offset) in blobs {
                    let drift = reduceMotion ? 0 : sin(t * 0.7 * speed + offset) * 0.12
                    let cx = size.width * (x + drift)
                    let w = size.width * (0.42 + 0.2 * energy)
                    let h = size.height * (0.55 + 1.1 * energy) * (0.85 + 0.15 * sin(t * 2.1 * speed + offset))
                    let rect = CGRect(x: cx - w / 2, y: size.height - h * 0.55, width: w, height: h)
                    ctx.fill(Path(ellipseIn: rect), with: .color(color.opacity(scheme == .dark ? 0.55 : 0.4) .opacity(min(1, 0.45 + energy))))
                }
            }
            .blur(radius: 26)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}
