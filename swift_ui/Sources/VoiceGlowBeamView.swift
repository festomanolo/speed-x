import Cocoa

public class VoiceGlowBeamView: NSView {
    public var isProcessing: Bool = false {
        didSet {
            if oldValue != isProcessing {
                needsDisplay = true
            }
        }
    }
    public var isDarkMode: Bool = true {
        didSet { needsDisplay = true }
    }

    public var sensitivity: Double = 3.2
    public var threshold: Double = 0.012
    public var idle: Double = 0.22
    public var reach: Double = 1.35
    public var spread: Double = 1.10
    public var processingDuration: Double = 1.15

    private var targetLevel: Double = 0.0
    private var currentLevel: Double = 0.0
    private var clockTime: Double = 0.0
    private var lastTimestamp: Double = CACurrentMediaTime()
    private var animationTimer: Timer?

    // 7 lobes as defined in voice-glow (Libraries.dev)
    private struct LobeConfig {
        let xOffsetRatio: Double // fraction of width/2
        let width: Double
        let height: Double
        let color: NSColor
    }

    private let lobes: [LobeConfig] = [
        LobeConfig(xOffsetRatio: -0.75, width: 44, height: 26, color: NSColor(red: 255/255, green: 70/255, blue: 120/255, alpha: 1.0)),  // Rose #FF4678
        LobeConfig(xOffsetRatio: -0.50, width: 50, height: 32, color: NSColor(red: 60/255, green: 190/255, blue: 255/255, alpha: 1.0)),  // Cyan #3CBEFF
        LobeConfig(xOffsetRatio: -0.25, width: 56, height: 40, color: NSColor(red: 175/255, green: 70/255, blue: 255/255, alpha: 1.0)), // Violet #AF46FF
        LobeConfig(xOffsetRatio: 0.0,   width: 78, height: 48, color: NSColor(red: 60/255, green: 222/255, blue: 130/255, alpha: 1.0)), // Emerald #3CDE82
        LobeConfig(xOffsetRatio: 0.25,  width: 56, height: 40, color: NSColor(red: 255/255, green: 150/255, blue: 40/255, alpha: 1.0)),  // Amber #FF9628
        LobeConfig(xOffsetRatio: 0.50,  width: 50, height: 32, color: NSColor(red: 90/255, green: 100/255, blue: 255/255, alpha: 1.0)),  // Indigo #5A64FF
        LobeConfig(xOffsetRatio: 0.75,  width: 44, height: 26, color: NSColor(red: 40/255, green: 200/255, blue: 190/255, alpha: 1.0))   // Aqua #28C8BE
    ]

    public override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setup()
    }

    public required init?(coder: NSCoder) {
        super.init(coder: coder)
        setup()
    }

    private func setup() {
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
        startAnimation()
    }

    public func setAudioLevel(_ level: Double) {
        let gated = level < threshold ? 0.0 : level * sensitivity
        targetLevel = min(1.0, max(0.0, gated))
    }

    public func setAudioLevel(_ level: Float) {
        setAudioLevel(Double(level))
    }

    public func startAnimation() {
        guard animationTimer == nil else { return }
        lastTimestamp = CACurrentMediaTime()
        animationTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            let now = CACurrentMediaTime()
            let dt = min(0.05, now - self.lastTimestamp)
            self.lastTimestamp = now
            self.clockTime += dt

            // Envelope follower (fast attack for voice transients, smooth natural release)
            if self.targetLevel > self.currentLevel {
                let attackSpeed = dt / 0.16
                self.currentLevel += (self.targetLevel - self.currentLevel) * min(1.0, attackSpeed * 2.8)
            } else {
                let releaseSpeed = dt / 0.55
                self.currentLevel += (self.targetLevel - self.currentLevel) * min(1.0, releaseSpeed * 1.8)
            }

            self.needsDisplay = true
        }
        RunLoop.main.add(animationTimer!, forMode: .common)
    }

    public func stopAnimation() {
        animationTimer?.invalidate()
        animationTimer = nil
    }

    deinit {
        stopAnimation()
    }

    public override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        let isDark = effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        if isDarkMode != isDark {
            isDarkMode = isDark
        }
    }

    // MARK: - Drawing
    public override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }

        let width = bounds.width
        let height = bounds.height
        guard width > 20 && height > 4 else { return }

        // Breathing idle presence: 5.2s sine wave
        let breathe = (sin(clockTime * (2.0 * .pi / 5.2)) + 1.0) / 2.0
        let effectiveIdle = idle * (0.8 + 0.2 * breathe)

        ctx.saveGState()

        // 1. Sleek Liquid Glass Capsule Track
        let trackRect = bounds.insetBy(dx: 1, dy: 1)
        let cornerR = min(trackRect.height / 2.0, 11.0)
        let trackPath = NSBezierPath(roundedRect: trackRect, xRadius: cornerR, yRadius: cornerR)

        let trackFill = isDarkMode ? NSColor(calibratedWhite: 1.0, alpha: 0.08) : NSColor(calibratedWhite: 1.0, alpha: 0.25)
        trackFill.setFill()
        trackPath.fill()

        let trackBorder = isDarkMode ? NSColor(calibratedWhite: 1.0, alpha: 0.20) : NSColor(calibratedWhite: 1.0, alpha: 0.60)
        trackBorder.setStroke()
        trackPath.lineWidth = 1.0
        trackPath.stroke()

        // Clip all visual reactions within track capsule
        trackPath.addClip()

        if isProcessing {
            drawProcessingBeam(ctx: ctx, width: width, height: height)
        } else {
            drawSoundReactiveBeam(ctx: ctx, width: width, height: height, idlePresence: effectiveIdle)
        }

        ctx.restoreGState()
    }

    // MARK: - Sound Reactive VoiceBeam with Alternating Intensity Waves
    private func drawSoundReactiveBeam(ctx: CGContext, width: Double, height: Double, idlePresence: Double) {
        let activeLevel = max(idlePresence, currentLevel)
        let midX = width / 2.0
        let baselineY = 2.0 // bottom of view in unflipped AppKit coords

        ctx.saveGState()

        // 1. Ambient Bloom Halos (7 Chromatic Lobes)
        let flowShift = sin(clockTime * 0.9) * 10.0
        for lobe in lobes {
            let lobeX = midX + (lobe.xOffsetRatio * (width * 0.44) * spread) + flowShift
            let lobeH = lobe.height * (0.9 + reach * activeLevel)
            let lobeW = lobe.width * (0.95 + 0.35 * activeLevel)
            let alpha = (0.28 + 0.62 * activeLevel) * (isDarkMode ? 0.85 : 0.65)

            let lobeRect = CGRect(x: lobeX - lobeW / 2.0, y: baselineY - 4.0, width: lobeW, height: min(height * 1.5, lobeH))
            drawRadialLobe(ctx: ctx, rect: lobeRect, color: lobe.color.withAlphaComponent(CGFloat(alpha)))
        }

        // 2. Alternating Audio-Reactive Waves ("Spectro Waves")
        // Three alternating harmonic wave ribbons that undulate dynamically based on voice intensity
        let waveY = baselineY + 4.0
        let baseAmp = 2.0 + (height * 0.36) * activeLevel

        // Wave 1: Cyan/Emerald forward wave
        let wavePath1 = CGMutablePath()
        let wavePath2 = CGMutablePath()
        let wavePath3 = CGMutablePath()

        let phase1 = clockTime * (4.2 + activeLevel * 6.5)
        let phase2 = -clockTime * (5.0 + activeLevel * 7.5) + 1.4 // Alternates in reverse direction!
        let phase3 = clockTime * (6.8 + activeLevel * 9.0) + 2.8 // Higher frequency harmonic

        var started = false
        for x in stride(from: 0.0, through: width, by: 2.0) {
            // Hanning / Bell envelope: zero at left/right edges, 1.0 at center
            let normX = x / width
            let env = sin(normX * .pi)

            // Wave 1 (Primary harmonic)
            let y1 = waveY + sin(x * 0.055 + phase1) * baseAmp * env
            // Wave 2 (Alternating secondary harmonic)
            let y2 = waveY + sin(x * 0.075 + phase2) * (baseAmp * 0.80) * env
            // Wave 3 (Fast shimmer harmonic)
            let y3 = waveY + cos(x * 0.095 + phase3) * (baseAmp * 0.60) * env

            let pt1 = CGPoint(x: x, y: y1)
            let pt2 = CGPoint(x: x, y: y2)
            let pt3 = CGPoint(x: x, y: y3)

            if !started {
                wavePath1.move(to: pt1)
                wavePath2.move(to: pt2)
                wavePath3.move(to: pt3)
                started = true
            } else {
                wavePath1.addLine(to: pt1)
                wavePath2.addLine(to: pt2)
                wavePath3.addLine(to: pt3)
            }
        }

        // Render Wave 2 (Rose/Violet reverse alternating wave)
        ctx.saveGState()
        ctx.setLineWidth(1.6)
        let color2 = NSColor(red: 255/255, green: 70/255, blue: 180/255, alpha: CGFloat(0.40 + 0.55 * activeLevel))
        ctx.setStrokeColor(color2.cgColor)
        ctx.addPath(wavePath2)
        ctx.strokePath()
        ctx.restoreGState()

        // Render Wave 3 (Amber/Gold high shimmer wave)
        ctx.saveGState()
        ctx.setLineWidth(1.4)
        let color3 = NSColor(red: 255/255, green: 170/255, blue: 50/255, alpha: CGFloat(0.35 + 0.55 * activeLevel))
        ctx.setStrokeColor(color3.cgColor)
        ctx.addPath(wavePath3)
        ctx.strokePath()
        ctx.restoreGState()

        // Render Wave 1 (Electric Cyan/Emerald primary forward wave)
        ctx.saveGState()
        ctx.setLineWidth(2.0)
        let color1 = NSColor(red: 60/255, green: 220/255, blue: 230/255, alpha: CGFloat(0.55 + 0.45 * activeLevel))
        ctx.setStrokeColor(color1.cgColor)
        ctx.addPath(wavePath1)
        ctx.strokePath()
        ctx.restoreGState()

        // 3. Crisp Baseline Core Beam
        let strokeAlpha = min(1.0, 0.45 + 0.55 * activeLevel)
        let beamY = baselineY + 1.0
        let baselinePath = CGMutablePath()
        baselinePath.move(to: CGPoint(x: width * 0.08, y: beamY))
        baselinePath.addLine(to: CGPoint(x: width * 0.92, y: beamY))

        ctx.saveGState()
        ctx.setLineWidth(1.8)
        ctx.setStrokeColor(NSColor.white.withAlphaComponent(CGFloat(strokeAlpha)).cgColor)
        ctx.addPath(baselinePath)
        ctx.strokePath()
        ctx.restoreGState()

        // 4. White-Hot Epicenter Core
        let coreW = 70.0 * (1.0 + 0.5 * activeLevel)
        let coreH = 14.0 * (1.0 + reach * activeLevel)
        let coreRect = CGRect(x: midX - coreW / 2.0, y: baselineY - 2.0, width: coreW, height: coreH)
        let coreColor = isDarkMode ? NSColor.white.withAlphaComponent(CGFloat(0.40 + 0.55 * activeLevel))
                                   : NSColor.white.withAlphaComponent(CGFloat(0.60 + 0.40 * activeLevel))
        drawRadialLobe(ctx: ctx, rect: coreRect, color: coreColor)

        ctx.restoreGState()
    }

    // MARK: - Processing Mode: Traveling sweep beam with eased turnaround
    private func drawProcessingBeam(ctx: CGContext, width: Double, height: Double) {
        let midX = width / 2.0
        let sweepPeriod = processingDuration * 2.0
        let sweepPhase = fmod(clockTime, sweepPeriod) / sweepPeriod
        let rawSweep = sin(sweepPhase * 2.0 * .pi)
        let sweepEased = rawSweep * abs(rawSweep) // Smooth curved turnaround
        let travelRange = width * 0.38
        let beamX = midX + sweepEased * travelRange
        let baselineY = 2.0

        ctx.saveGState()

        // Lit base glow across track
        let baseRect = CGRect(x: width * 0.12, y: baselineY, width: width * 0.76, height: height * 0.8)
        drawRadialLobe(ctx: ctx, rect: baseRect, color: NSColor(red: 175/255, green: 70/255, blue: 255/255, alpha: 0.22))

        // Traveling iridescent beam lobes
        let beamColors: [NSColor] = [
            NSColor(red: 255/255, green: 70/255, blue: 120/255, alpha: 0.85), // Rose
            NSColor(red: 60/255, green: 190/255, blue: 255/255, alpha: 0.90),  // Cyan
            NSColor(red: 175/255, green: 70/255, blue: 255/255, alpha: 0.90), // Purple
            NSColor(red: 60/255, green: 222/255, blue: 130/255, alpha: 0.85)  // Green
        ]

        for (idx, color) in beamColors.enumerated() {
            let offset = (Double(idx) - 1.5) * 14.0
            let lobeRect = CGRect(x: beamX + offset - 22, y: baselineY - 4.0, width: 44, height: height * 0.95)
            drawRadialLobe(ctx: ctx, rect: lobeRect, color: color)
        }

        // White-hot traveling core center
        let coreRect = CGRect(x: beamX - 22, y: baselineY - 2.0, width: 44, height: height * 0.6)
        drawRadialLobe(ctx: ctx, rect: coreRect, color: NSColor.white.withAlphaComponent(0.95))

        // Glowing bottom track line around traveling beam
        ctx.setLineWidth(2.2)
        ctx.setStrokeColor(NSColor.white.withAlphaComponent(0.90).cgColor)
        ctx.beginPath()
        ctx.move(to: CGPoint(x: max(10, beamX - 34), y: baselineY + 1.0))
        ctx.addLine(to: CGPoint(x: min(width - 10, beamX + 34), y: baselineY + 1.0))
        ctx.strokePath()

        ctx.restoreGState()
    }

    private func drawRadialLobe(ctx: CGContext, rect: CGRect, color: NSColor) {
        ctx.saveGState()
        let colors = [color.cgColor, color.withAlphaComponent(0.0).cgColor] as CFArray
        let locations: [CGFloat] = [0.0, 1.0]
        guard let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors, locations: locations) else {
            ctx.restoreGState()
            return
        }

        let center = CGPoint(x: rect.midX, y: rect.minY + 2.0)
        let radius = max(rect.width, rect.height) / 2.0

        ctx.saveGState()
        let scaleY = rect.height / rect.width
        ctx.translateBy(x: center.x, y: center.y)
        ctx.scaleBy(x: 1.0, y: scaleY)
        ctx.drawRadialGradient(gradient, startCenter: .zero, startRadius: 0.0, endCenter: .zero, endRadius: radius, options: .drawsAfterEndLocation)
        ctx.restoreGState()

        ctx.restoreGState()
    }
}
