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

    public var sensitivity: Double = 3.4
    public var threshold: Double = 0.010
    public var cornerRadius: CGFloat = 18.0

    private var targetLevel: Double = 0.0
    private var currentLevel: Double = 0.0
    private var clockTime: Double = 0.0
    private var lastTimestamp: Double = CACurrentMediaTime()
    private var animationTimer: Timer?

    public override var isFlipped: Bool { true }

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

            // Responsive envelope follower for natural blooming and dimming
            if self.targetLevel > self.currentLevel {
                let attackSpeed = dt * 14.0 // rapid attack on speech transients
                self.currentLevel += (self.targetLevel - self.currentLevel) * min(1.0, attackSpeed)
            } else {
                let releaseSpeed = dt * 2.6 // smooth, natural dimming decay
                self.currentLevel += (self.targetLevel - self.currentLevel) * min(1.0, releaseSpeed)
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

    // MARK: - Drawing: Volumetric Bottom-Edge Aurora VoiceBeam
    public override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }

        let width = bounds.width
        let height = bounds.height
        guard width > 30 && height > 10 else { return }

        ctx.saveGState()

        // 1. Clip strictly to the card's bottom rounded boundary
        let clipPath = NSBezierPath()
        clipPath.move(to: NSPoint(x: 0, y: 0))
        clipPath.line(to: NSPoint(x: width, y: 0))
        clipPath.line(to: NSPoint(x: width, y: height - cornerRadius))
        clipPath.appendArc(from: NSPoint(x: width, y: height), to: NSPoint(x: width - cornerRadius, y: height), radius: cornerRadius)
        clipPath.line(to: NSPoint(x: cornerRadius, y: height))
        clipPath.appendArc(from: NSPoint(x: 0, y: height), to: NSPoint(x: 0, y: height - cornerRadius), radius: cornerRadius)
        clipPath.close()
        clipPath.addClip()

        if isProcessing {
            drawProcessingStage(ctx: ctx, width: width, height: height)
        } else {
            drawSoundReactiveAuroraStage(ctx: ctx, width: width, height: height)
        }

        ctx.restoreGState()
    }

    // MARK: - Sound Reactive Aurora: Blooming and Dimming with live vocal intensity
    private func drawSoundReactiveAuroraStage(ctx: CGContext, width: Double, height: Double) {
        // Natural organic breathing cycle when idle
        let breathe = (sin(clockTime * 1.6) + 1.0) / 2.0
        let idlePresence = 0.12 + 0.05 * breathe
        let activeLevel = max(idlePresence, currentLevel)

        let bottomY = height + 2.0 // Anchor light source right at the bottom edge

        ctx.saveGState()

        // --- LAYER 1: Deep Volumetric Colored Light Clouds ---

        // Far-Left Warm Amber/Olive Haze (Soft & muted, matching reference)
        let amberAlpha = (0.10 + 0.26 * activeLevel) * (isDarkMode ? 1.0 : 0.75)
        let amberColor = NSColor(red: 180/255, green: 130/255, blue: 40/255, alpha: CGFloat(amberAlpha))
        drawEllipticalGlow(ctx: ctx, center: CGPoint(x: width * 0.16, y: bottomY), radiusX: width * 0.24, radiusY: height * (0.35 + 0.28 * activeLevel), color: amberColor)

        // Mid-Left Electric Teal / Sage Wash
        let tealAlpha = (0.16 + 0.35 * activeLevel) * (isDarkMode ? 1.0 : 0.8)
        let tealColor = NSColor(red: 20/255, green: 140/255, blue: 120/255, alpha: CGFloat(tealAlpha))
        drawEllipticalGlow(ctx: ctx, center: CGPoint(x: width * 0.34, y: bottomY), radiusX: width * 0.26, radiusY: height * (0.45 + 0.35 * activeLevel), color: tealColor)

        // Mid-Right Deep Violet / Plum Cloud (Under mic & close buttons)
        let violetAlpha = (0.20 + 0.40 * activeLevel) * (isDarkMode ? 1.0 : 0.8)
        let violetColor = NSColor(red: 110/255, green: 45/255, blue: 130/255, alpha: CGFloat(violetAlpha))
        drawEllipticalGlow(ctx: ctx, center: CGPoint(x: width * 0.68, y: bottomY), radiusX: width * 0.28, radiusY: height * (0.50 + 0.38 * activeLevel), color: violetColor)

        // Far-Right Rich Berry / Magenta Cloud
        let magentaAlpha = (0.18 + 0.42 * activeLevel) * (isDarkMode ? 1.0 : 0.8)
        let magentaColor = NSColor(red: 155/255, green: 45/255, blue: 100/255, alpha: CGFloat(magentaAlpha))
        drawEllipticalGlow(ctx: ctx, center: CGPoint(x: width * 0.84, y: bottomY), radiusX: width * 0.26, radiusY: height * (0.44 + 0.34 * activeLevel), color: magentaColor)

        // Center Hero Emerald Green Aurora Pillar (Tallest volumetric bloom rising between buttons)
        let emeraldAlpha = (0.35 + 0.58 * activeLevel) * (isDarkMode ? 1.0 : 0.85)
        let emeraldColor = NSColor(red: 24/255, green: 185/255, blue: 105/255, alpha: CGFloat(emeraldAlpha))
        let emeraldHeight = height * (0.60 + 0.38 * activeLevel)
        drawEllipticalGlow(ctx: ctx, center: CGPoint(x: width * 0.50, y: bottomY), radiusX: width * 0.25, radiusY: emeraldHeight, color: emeraldColor)

        // Inner Saturated Mint / Cyan Radiance
        let innerMintAlpha = (0.42 + 0.52 * activeLevel)
        let innerMintColor = NSColor(red: 35/255, green: 215/255, blue: 170/255, alpha: CGFloat(innerMintAlpha))
        drawEllipticalGlow(ctx: ctx, center: CGPoint(x: width * 0.50, y: bottomY), radiusX: width * 0.20, radiusY: height * (0.40 + 0.30 * activeLevel), color: innerMintColor)

        // --- LAYER 2: Radiant Center-Bottom Bloom & Hot White Core ---
        // Saturated cyan/mint floor flare at bottom center
        let flareAlpha = (0.45 + 0.55 * activeLevel)
        let flareColor = NSColor(red: 45/255, green: 230/255, blue: 185/255, alpha: CGFloat(flareAlpha))
        drawEllipticalGlow(ctx: ctx, center: CGPoint(x: width * 0.50, y: height + 1.0), radiusX: width * 0.30, radiusY: 26.0 * (1.0 + 0.35 * activeLevel), color: flareColor)

        // Hot white core glint at bottom center
        let specularAlpha = (0.50 + 0.50 * activeLevel)
        let specularColor = NSColor.white.withAlphaComponent(CGFloat(specularAlpha))
        drawEllipticalGlow(ctx: ctx, center: CGPoint(x: width * 0.50, y: height), radiusX: width * 0.16, radiusY: 9.0 * (1.0 + 0.25 * activeLevel), color: specularColor)

        // --- LAYER 3: Chromatic Refraction Rim Along the Bottom Fillet Curve ---
        let rimPath = CGMutablePath()
        rimPath.move(to: CGPoint(x: 1.0, y: height - cornerRadius))
        rimPath.addArc(tangent1End: CGPoint(x: 1.0, y: height - 1.0), tangent2End: CGPoint(x: cornerRadius, y: height - 1.0), radius: cornerRadius - 1.0)
        rimPath.addLine(to: CGPoint(x: width - cornerRadius, y: height - 1.0))
        rimPath.addArc(tangent1End: CGPoint(x: width - 1.0, y: height - 1.0), tangent2End: CGPoint(x: width - 1.0, y: height - cornerRadius), radius: cornerRadius - 1.0)

        // Stroke rim with multi-stop chromatic gradient
        ctx.saveGState()
        ctx.setLineWidth(1.6)
        ctx.setLineCap(.round)
        ctx.addPath(rimPath)
        ctx.replacePathWithStrokedPath()
        ctx.clip()

        let rimGradientColors = [
            NSColor(red: 140/255, green: 110/255, blue: 50/255, alpha: CGFloat(0.20 + 0.25 * activeLevel)).cgColor,
            NSColor(red: 30/255, green: 170/255, blue: 150/255, alpha: CGFloat(0.40 + 0.35 * activeLevel)).cgColor,
            NSColor(red: 80/255, green: 235/255, blue: 195/255, alpha: CGFloat(0.70 + 0.30 * activeLevel)).cgColor,
            NSColor(white: 1.0, alpha: CGFloat(0.85 + 0.15 * activeLevel)).cgColor,
            NSColor(red: 80/255, green: 235/255, blue: 195/255, alpha: CGFloat(0.70 + 0.30 * activeLevel)).cgColor,
            NSColor(red: 70/255, green: 130/255, blue: 215/255, alpha: CGFloat(0.45 + 0.35 * activeLevel)).cgColor,
            NSColor(red: 175/255, green: 75/255, blue: 130/255, alpha: CGFloat(0.35 + 0.35 * activeLevel)).cgColor
        ] as CFArray
        let rimLocations: [CGFloat] = [0.0, 0.22, 0.44, 0.50, 0.56, 0.76, 1.0]

        if let rimGrad = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: rimGradientColors, locations: rimLocations) {
            ctx.drawLinearGradient(rimGrad, start: CGPoint(x: 0, y: height), end: CGPoint(x: width, y: height), options: [])
        }
        ctx.restoreGState()

        ctx.restoreGState()
    }

    // MARK: - Processing Stage: Traveling Sweep Beam
    private func drawProcessingStage(ctx: CGContext, width: Double, height: Double) {
        let sweepPeriod = 2.2
        let sweepPhase = fmod(clockTime, sweepPeriod) / sweepPeriod
        let rawSweep = sin(sweepPhase * 2.0 * .pi)
        let sweepEased = rawSweep * abs(rawSweep) // Smooth turnaround
        let travelRange = width * 0.35
        let beamX = (width / 2.0) + sweepEased * travelRange
        let bottomY = height + 4.0

        ctx.saveGState()

        // Background ambient glow across the card floor
        let ambientColor = NSColor(red: 139/255, green: 92/255, blue: 246/255, alpha: 0.25)
        drawEllipticalGlow(ctx: ctx, center: CGPoint(x: width * 0.50, y: bottomY), radiusX: width * 0.45, radiusY: height * 0.70, color: ambientColor)

        // Traveling iridescent beam lobes
        let lobes: [(Double, NSColor)] = [
            (-20.0, NSColor(red: 236/255, green: 72/255, blue: 153/255, alpha: 0.85)), // Rose
            (-8.0,  NSColor(red: 6/255, green: 182/255, blue: 212/255, alpha: 0.90)),   // Cyan
            (0.0,   NSColor(red: 34/255, green: 197/255, blue: 94/255, alpha: 0.95)),   // Emerald
            (10.0,  NSColor(red: 139/255, green: 92/255, blue: 246/255, alpha: 0.90))   // Violet
        ]

        for (offset, color) in lobes {
            drawEllipticalGlow(ctx: ctx, center: CGPoint(x: beamX + offset, y: bottomY), radiusX: 38.0, radiusY: height * 0.85, color: color)
        }

        // White-hot traveling core center
        drawEllipticalGlow(ctx: ctx, center: CGPoint(x: beamX, y: bottomY - 1.0), radiusX: 22.0, radiusY: height * 0.45, color: NSColor.white.withAlphaComponent(0.95))

        // Sweeping bottom light track
        let rimY = height - 1.2
        ctx.saveGState()
        ctx.setLineWidth(2.5)
        ctx.setLineCap(.round)
        ctx.setStrokeColor(NSColor.white.withAlphaComponent(0.92).cgColor)
        ctx.beginPath()
        ctx.move(to: CGPoint(x: max(cornerRadius, beamX - 32), y: rimY))
        ctx.addLine(to: CGPoint(x: min(width - cornerRadius, beamX + 32), y: rimY))
        ctx.strokePath()
        ctx.restoreGState()

        ctx.restoreGState()
    }

    // Helper to render high-order Gaussian-style elliptical glows
    private func drawEllipticalGlow(ctx: CGContext, center: CGPoint, radiusX: CGFloat, radiusY: CGFloat, color: NSColor) {
        guard radiusX > 1 && radiusY > 1 else { return }

        ctx.saveGState()
        let colors = [
            color.cgColor,
            color.withAlphaComponent(color.alphaComponent * 0.65).cgColor,
            color.withAlphaComponent(color.alphaComponent * 0.20).cgColor,
            color.withAlphaComponent(0.0).cgColor
        ] as CFArray
        let locations: [CGFloat] = [0.0, 0.35, 0.70, 1.0]

        guard let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors, locations: locations) else {
            ctx.restoreGState()
            return
        }

        let scaleY = radiusY / radiusX
        ctx.translateBy(x: center.x, y: center.y)
        ctx.scaleBy(x: 1.0, y: scaleY)

        ctx.drawRadialGradient(
            gradient,
            startCenter: .zero,
            startRadius: 0.0,
            endCenter: .zero,
            endRadius: radiusX,
            options: .drawsAfterEndLocation
        )

        ctx.restoreGState()
    }
}
