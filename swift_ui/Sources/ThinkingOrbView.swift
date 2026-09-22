import Cocoa

public enum OrbState: String, CaseIterable {
    case working     // orbits
    case searching   // globe scan
    case solving     // rubik
    case listening   // wave
    case connecting  // web constellation
    case weaving     // braid
    case composing   // ribbon
    case breathing   // ring
    case shaping     // morph
}

public struct OrbDot {
    public var x: Double
    public var y: Double
    public var z: Double
    public var r: Double
    public var white: Double
    public var a: Double
}

public struct OrbLine {
    public var x1: Double
    public var y1: Double
    public var x2: Double
    public var y2: Double
    public var white: Double
    public var a: Double
    public var w: Double
}

public struct OrbFrame {
    public var dots: [OrbDot]
    public var lines: [OrbLine]
}

public class ThinkingOrbView: NSView {
    public var state: OrbState = .working {
        didSet {
            if oldValue != state {
                needsDisplay = true
            }
        }
    }
    public var speed: Double = 1.0
    public var isPaused: Bool = false
    public var isDarkMode: Bool = true {
        didSet { needsDisplay = true }
    }
    public var tintColor: NSColor? = nil

    private var animationTimer: Timer?
    private var clockTime: Double = 0.0
    private var lastTimestamp: Double = CACurrentMediaTime()

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

    public func startAnimation() {
        guard animationTimer == nil else { return }
        lastTimestamp = CACurrentMediaTime()
        animationTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            let now = CACurrentMediaTime()
            let dt = now - self.lastTimestamp
            self.lastTimestamp = now
            if !self.isPaused {
                self.clockTime += dt * self.speed
                self.needsDisplay = true
            }
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

    // MARK: - Core Math Functions
    private static func lerp(_ a: Double, _ b: Double, _ f: Double) -> Double {
        return a + (b - a) * f
    }

    private static func frac(_ x: Double) -> Double {
        return x - floor(x)
    }

    private static func hashD(_ a: Double, _ b: Double) -> Double {
        let h = sin(a * 12.9898 + b * 78.233) * 43758.5453
        return h - floor(h)
    }

    private static func vnoise(_ x: Double, _ y: Double) -> Double {
        let xi = floor(x)
        let yi = floor(y)
        var fx = x - xi
        var fy = y - yi
        fx = fx * fx * (3.0 - 2.0 * fx)
        fy = fy * fy * (3.0 - 2.0 * fy)
        let a = hashD(xi, yi)
        let b = hashD(xi + 1.0, yi)
        let c = hashD(xi, yi + 1.0)
        let d = hashD(xi + 1.0, yi + 1.0)
        return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy
    }

    private static func fibDir(_ i: Int, _ n: Int) -> (Double, Double, Double) {
        let golden = Double.pi * (3.0 - sqrt(5.0))
        let y = 1.0 - 2.0 * (Double(i) + 0.5) / Double(n)
        let rad = sqrt(max(0.0, 1.0 - y * y))
        let a = Double(i) * golden
        return (rad * cos(a), y, rad * sin(a))
    }

    private static func angleDelta(_ a: Double, _ b: Double) -> Double {
        return atan2(sin(a - b), cos(a - b))
    }

    private static func radiusScale(_ size: Double, _ powVal: Double) -> Double {
        return pow(size / 300.0, powVal)
    }

    private static func makeProj(_ yaw: Double, _ tilt: Double, _ cx: Double, _ cy: Double, _ scale: Double)
        -> (Double, Double, Double) -> (Double, Double, Double) {
        let st = sin(tilt)
        let ct = cos(tilt)
        let sy = sin(yaw)
        let cyw = cos(yaw)
        return { (x: Double, y: Double, z: Double) in
            let x1 = x * cyw + z * sy
            let z1 = -x * sy + z * cyw
            let y1 = y * ct - z1 * st
            let z2 = y * st + z1 * ct
            return (cx + x1 * scale, cy + y1 * scale, z2)
        }
    }

    // MARK: - Frame Generators
    private func generateFrame(size: Double, t: Double) -> OrbFrame {
        switch state {
        case .working:
            return frameOrbits(size: size, t: t * 1.885)
        case .searching:
            return frameGlobe(size: size, t: t * 2.015)
        case .solving:
            return frameRubik(size: size, t: t * 1.82)
        case .listening:
            return frameWave(size: size, t: t * 4.388)
        case .connecting:
            return frameWeb(size: size, t: t * 3.315)
        case .weaving:
            return frameBraid(size: size, t: t * 1.625)
        case .composing:
            return frameRibbon(size: size, t: t * 2.34, faceOn: false)
        case .breathing:
            return frameRibbon(size: size, t: t * 3.24, faceOn: true)
        case .shaping:
            return frameMorph(size: size, t: t * 2.405)
        }
    }

    // MARK: 1. Working (Orbits)
    private func frameOrbits(size: Double, t: Double) -> OrbFrame {
        let cx = size / 2.0
        let cy = size / 2.0
        let R = size / 2.0 * 0.82
        let pt = Self.makeProj(t * 0.12, 0.3, cx, cy, 1.0)
        let rs = Self.radiusScale(size, 0.6)
        var dots: [OrbDot] = []
        let orbitN = 12
        let ghostN = 36
        let particles = 3

        for orb in 0..<orbitN {
            let h1 = Self.hashD(Double(orb), 1.7)
            let h2 = Self.hashD(Double(orb), 5.2)
            let h3 = Self.hashD(Double(orb), 8.9)
            let ro = R * (0.45 + 0.52 * h1)
            let th = h1 * 2.0 * .pi
            let phi = acos(2.0 * h2 - 1.0)
            let nx = sin(phi) * cos(th)
            let ny = cos(phi)
            let nz = sin(phi) * sin(th)
            var ux = -ny
            var uy = nx
            let uz = 0.0
            let ul = max(1e-6, sqrt(ux * ux + uy * uy))
            ux /= ul
            uy /= ul
            let vx = ny * uz - nz * uy
            let vy = nz * ux - nx * uz
            let vz = nx * uy - ny * ux
            let speed = (0.25 + 0.55 * h3) * (h3 > 0.5 ? 1.0 : -1.0)

            for k in 0..<ghostN {
                let a = Double(k) / Double(ghostN) * 2.0 * .pi
                let (px, py, z) = pt(
                    (ux * cos(a) + vx * sin(a)) * ro,
                    (uy * cos(a) + vy * sin(a)) * ro,
                    (uz * cos(a) + vz * sin(a)) * ro
                )
                let depth = (z / ro + 1.0) / 2.0
                dots.append(OrbDot(x: px, y: py, z: z, r: 0.9 * rs, white: 0.72, a: 0.45 * (0.4 + 0.6 * depth)))
            }

            for m in 0..<particles {
                let a = t * speed + Double(m) / Double(particles) * 2.0 * .pi + h2 * 6.0
                let (px, py, z) = pt(
                    (ux * cos(a) + vx * sin(a)) * ro,
                    (uy * cos(a) + vy * sin(a)) * ro,
                    (uz * cos(a) + vz * sin(a)) * ro
                )
                let depth = (z / ro + 1.0) / 2.0
                dots.append(OrbDot(x: px, y: py, z: z, r: (1.2 + 1.6 * depth) * rs, white: 0.3 - 0.22 * depth, a: 1.0))
            }
        }
        return finalize(dots: dots, lines: [])
    }

    // MARK: 2. Searching (Globe Scan)
    private func frameGlobe(size: Double, t: Double) -> OrbFrame {
        let spin = 0.5
        let cx = size / 2.0
        let cy = size / 2.0
        let radius = size / 2.0 * 0.82
        let tilt = 0.4 + 0.06 * sin(t * 0.35)
        let pt = Self.makeProj(t * spin, tilt, cx, cy, radius)
        let scan = t * (spin + (1.7 - spin) * 4.08)
        let rs = Self.radiusScale(size, 0.6)
        let dimBase = 0.45
        var dots: [OrbDot] = []
        let latRings = 15
        let lonDensity = 36

        for li in 0...latRings {
            let lat = -.pi / 2.0 + Double(li) / Double(latRings) * .pi
            let cosLat = cos(lat)
            let sinLat = sin(lat)
            let lonCount = max(1, Int(round(abs(cosLat) * Double(lonDensity))))
            for lj in 0..<lonCount {
                let lon = Double(lj) / Double(lonCount) * 2.0 * .pi
                let (px, py, z) = pt(cosLat * cos(lon), sinLat, cosLat * sin(lon))
                let depth = (z + 1.0) / 2.0
                let d = Self.angleDelta(lon + t * spin, scan)
                let boost = exp(-(d * d) / 0.18) * max(0.0, z)
                dots.append(OrbDot(
                    x: px, y: py, z: z,
                    r: (0.6 + 1.7 * depth + 1.0 * boost) * rs,
                    white: 0.62 - 0.54 * depth,
                    a: dimBase + (1.0 - dimBase) * min(1.0, boost)
                ))
            }
        }
        return finalize(dots: dots, lines: [])
    }

    // MARK: 3. Solving (Rubik)
    private func frameRubik(size: Double, t: Double) -> OrbFrame {
        let cx = size / 2.0
        let cy = size / 2.0
        let R = size / 2.0 * 0.82
        let pt = Self.makeProj(t * 0.55, 0.35 + 0.1 * sin(t * 0.9), cx, cy, R)
        let rs = Self.radiusScale(size, 0.6)
        var dots: [OrbDot] = []
        let latRings = 14
        let lonDensity = 32

        for li in 0...latRings {
            let lat = -.pi / 2.0 + Double(li) / Double(latRings) * .pi
            let cosLat = cos(lat)
            let sinLat = sin(lat)
            let lonCount = max(1, Int(round(abs(cosLat) * Double(lonDensity))))
            for lj in 0..<lonCount {
                let lon = Double(lj) / Double(lonCount) * 2.0 * .pi
                let (px, py, zr) = pt(cosLat * cos(lon), sinLat, cosLat * sin(lon))
                let depth = (zr + 1.0) / 2.0
                dots.append(OrbDot(
                    x: px, y: py, z: zr,
                    r: (0.6 + 1.7 * depth) * rs,
                    white: 0.62 - 0.54 * depth,
                    a: 0.9
                ))
            }
        }
        return finalize(dots: dots, lines: [])
    }

    // MARK: 4. Listening (Wave)
    private func frameWave(size: Double, t: Double) -> OrbFrame {
        let cx = size / 2.0
        let cy = size / 2.0
        let R = size / 2.0 * 0.874
        let pt = Self.makeProj(t * 0.18, 0.38, cx, cy, 1.0)
        let rs = Self.radiusScale(size, 0.6)
        var dots: [OrbDot] = []
        let rings = 14
        let lonDensity = 34

        for ri in 0...rings {
            let lat = -.pi / 2.0 + Double(ri) / Double(rings) * .pi
            let cosLat = cos(lat)
            let sinLat = sin(lat)
            let w = 0.62 * sin(t * 2.1 - Double(ri) * 0.52) + 0.38 * sin(t * 1.27 + Double(ri) * 0.83)
            let rr = R * (0.88 + 0.105 * w)
            let lonCount = max(1, Int(round(abs(cosLat) * Double(lonDensity))))
            for lj in 0..<lonCount {
                let lon = Double(lj) / Double(lonCount) * 2.0 * .pi
                let (px, py, z) = pt(cosLat * cos(lon) * rr, sinLat * rr, cosLat * sin(lon) * rr)
                let depth = (z / R + 1.0) / 2.0
                let crest = max(0.0, w)
                dots.append(OrbDot(
                    x: px, y: py, z: z,
                    r: (0.6 + 1.7 * depth) * (1.0 + 0.4 * crest) * rs,
                    white: 0.66 - 0.56 * depth - 0.1 * crest,
                    a: 0.95
                ))
            }
        }
        return finalize(dots: dots, lines: [])
    }

    // MARK: 5. Connecting (Web Constellation)
    private func frameWeb(size: Double, t: Double) -> OrbFrame {
        let cx = size / 2.0
        let cy = size / 2.0
        let R = size / 2.0 * 0.8
        let pt = Self.makeProj(t * 0.12, 0.32, cx, cy, R)
        let rs = Self.radiusScale(size, 0.6)
        let nodeN = 26
        let thr = 0.72
        var nodes: [(Double, Double, Double)] = []

        for i in 0..<nodeN {
            let d = Self.fibDir(i, nodeN)
            let x = d.0 + 0.3 * (Self.vnoise(Double(i) * 0.31 + 9.0, t * 0.24) - 0.5) * 2.0
            let y = d.1 + 0.3 * (Self.vnoise(Double(i) * 0.53 + 27.0, t * 0.21) - 0.5) * 2.0
            let z = d.2 + 0.3 * (Self.vnoise(Double(i) * 0.77 + 55.0, t * 0.27) - 0.5) * 2.0
            let l = sqrt(x * x + y * y + z * z)
            nodes.append((x / l, y / l, z / l))
        }

        var lines: [OrbLine] = []
        var dots: [OrbDot] = []

        for i in 0..<nodeN {
            for j in (i + 1)..<nodeN {
                let dx = nodes[i].0 - nodes[j].0
                let dy = nodes[i].1 - nodes[j].1
                let dz = nodes[i].2 - nodes[j].2
                let dist = sqrt(dx * dx + dy * dy + dz * dz)
                if dist >= thr { continue }
                let (x1, y1, z1) = pt(nodes[i].0, nodes[i].1, nodes[i].2)
                let (x2, y2, z2) = pt(nodes[j].0, nodes[j].1, nodes[j].2)
                let depth = ((z1 + z2) / 2.0 + 1.0) / 2.0
                lines.append(OrbLine(
                    x1: x1, y1: y1, x2: x2, y2: y2,
                    white: 0.42,
                    a: (1.0 - dist / thr) * (0.3 + 0.55 * depth),
                    w: max(0.6, 0.8 * rs)
                ))
            }
        }

        for i in 0..<nodeN {
            let (px, py, z) = pt(nodes[i].0, nodes[i].1, nodes[i].2)
            let depth = (z + 1.0) / 2.0
            let pulse = 1.0 + 0.25 * sin(t * 1.4 + Double(i) * 2.7)
            dots.append(OrbDot(
                x: px, y: py, z: z,
                r: (1.4 + 1.8 * depth) * pulse * rs,
                white: 0.55 - 0.45 * depth,
                a: 1.0
            ))
        }

        let signals = 4
        for s in 0..<signals {
            let seg = Int(floor(t * 0.55 + Double(s) * 7.31))
            let aIdx = Int(floor(Self.hashD(Double(seg), Double(s) * 3.1 + 1.7) * Double(nodeN))) % nodeN
            let bIdx = Int(floor(Self.hashD(Double(seg), Double(s) * 5.7 + 4.2) * Double(nodeN))) % nodeN
            if aIdx == bIdx { continue }
            let f = Self.frac(t * 0.55 + Double(s) * 7.31)
            let x = Self.lerp(nodes[aIdx].0, nodes[bIdx].0, f)
            let y = Self.lerp(nodes[aIdx].1, nodes[bIdx].1, f)
            let z = Self.lerp(nodes[aIdx].2, nodes[bIdx].2, f)
            let l = max(1e-6, sqrt(x * x + y * y + z * z))
            let (px, py, zr) = pt(x / l, y / l, z / l)
            let depth = (zr + 1.0) / 2.0
            dots.append(OrbDot(
                x: px, y: py, z: zr,
                r: (1.4 * 1.5 + 1.8 * depth) * rs,
                white: 0.05,
                a: 0.5 + 0.5 * depth
            ))
        }
        return finalize(dots: dots, lines: lines)
    }

    // MARK: 6. Weaving (Braid)
    private func frameBraid(size: Double, t: Double) -> OrbFrame {
        let cx = size / 2.0
        let cy = size / 2.0
        let R = size / 2.0 * 0.76
        let pt = Self.makeProj(t * 0.4, 0.3, cx, cy, 1.0)
        let rs = Self.radiusScale(size, 0.6)
        var dots: [OrbDot] = []
        let ghostN = 80

        for i in 0..<ghostN {
            let d = Self.fibDir(i, ghostN)
            let (px, py, z) = pt(d.0 * R, d.1 * R, d.2 * R)
            let depth = (z / R + 1.0) / 2.0
            dots.append(OrbDot(x: px, y: py, z: z, r: 0.8 * rs, white: 0.78, a: 0.1 + 0.22 * depth))
        }

        let strandN = 44
        let turns = 3.0
        for s in 0..<3 {
            let phase = Double(s) / 3.0 * 2.0 * .pi
            for i in 0..<strandN {
                let u = (Self.frac(Double(i) / Double(strandN) + t * 0.045) * 2.0 - 1.0) * 0.96
                let surf = sqrt(max(0.0, 1.0 - u * u))
                let endFade = min(1.0, (1.0 - abs(u)) / 0.1)
                let a = u * .pi * turns + phase
                let weave = 1.0 + 0.075 * sin(u * .pi * turns * 2.0 + phase * 2.0 + t * 0.8)
                let rr = surf * R * weave
                let (px, py, zr) = pt(cos(a) * rr, u * R * weave, sin(a) * rr)
                let depth = (zr / R + 1.0) / 2.0
                dots.append(OrbDot(
                    x: px, y: py, z: zr,
                    r: (1.2 + 1.8 * depth) * rs,
                    white: 0.55 - 0.45 * depth,
                    a: endFade * (0.45 + 0.55 * depth)
                ))
            }
        }
        return finalize(dots: dots, lines: [])
    }

    // MARK: 7. Composing & Breathing (Ribbon / Ring)
    private func frameRibbon(size: Double, t: Double, faceOn: Bool) -> OrbFrame {
        let cx = size / 2.0
        let cy = size / 2.0
        let R = size / 2.0 * 0.78
        let camTilt = 0.3
        let pt = Self.makeProj(t * 0.1, camTilt, cx, cy, 1.0)
        let rs = Self.radiusScale(size, 0.6)
        var dots: [OrbDot] = []

        if !faceOn {
            let ghostN = 80
            for i in 0..<ghostN {
                let d = Self.fibDir(i, ghostN)
                let (px, py, z) = pt(d.0 * R, d.1 * R, d.2 * R)
                let depth = (z / R + 1.0) / 2.0
                dots.append(OrbDot(x: px, y: py, z: z, r: 0.8 * rs, white: 0.78, a: 0.1 + 0.22 * depth))
            }
        }

        let ya = t * 0.24
        let ta = faceOn ? -camTilt : 0.55 + 0.3 * sin(t * 0.18)
        let ux = cos(ya)
        let uy = 0.0
        let uz = sin(ya)
        let vx = -uz * sin(ta)
        let vy = cos(ta)
        let vz = ux * sin(ta)
        let nx = uy * vz - uz * vy
        let ny = uz * vx - ux * vz
        let nz = ux * vy - uy * vx
        let wobAmp = 0.23 * (faceOn ? 0.368 : 1.0)
        let baseR = faceOn ? R / (1.0 + 0.85 * wobAmp) : R
        let lanes = faceOn ? 4 : 5
        let segs = 70

        for w in 0..<lanes {
            let laneOff = (Double(w) - Double(lanes - 1) / 2.0) * 0.075
            let edge = abs(Double(w) - Double(lanes - 1) / 2.0) / max(1.0, Double(lanes - 1) / 2.0)
            for k in 0..<segs {
                let a = Double(k) / Double(segs) * 2.0 * .pi
                let wob = (0.16 * sin(a * 3.0 - t * 1.7 + Double(w) * 0.22) + 0.07 * sin(a * 5.0 + t * 1.1)) * (faceOn ? 0.368 : 1.0)
                let radial = faceOn ? (1.0 + wob) : 1.0
                let off = faceOn ? laneOff : (laneOff + wob)
                let x = ux * cos(a) + vx * sin(a) + nx * off
                let y = uy * cos(a) + vy * sin(a) + ny * off
                let z = uz * cos(a) + vz * sin(a) + nz * off
                let l = sqrt(x * x + y * y + z * z)
                let rr = baseR * radial
                let (px, py, zr) = pt(x / l * rr, y / l * rr, z / l * rr)
                let depth = (zr / R + 1.0) / 2.0
                dots.append(OrbDot(
                    x: px, y: py, z: zr,
                    r: ((1.1 + 1.7 * depth) * (1.0 - 0.25 * edge)) * rs,
                    white: 0.52 - 0.44 * depth + 0.18 * edge,
                    a: 0.4 + 0.6 * depth
                ))
            }
        }
        return finalize(dots: dots, lines: [])
    }

    // MARK: 8. Shaping (Morphing Outline)
    private func frameMorph(size: Double, t: Double) -> OrbFrame {
        let cx = size / 2.0
        let cy = size / 2.0
        let R = size / 2.0 * 0.72
        var dots: [OrbDot] = []
        let n = 28
        let cycle = t * 0.8
        let shapeMorph = (sin(cycle) + 1.0) / 2.0

        for i in 0..<n {
            let a = Double(i) / Double(n) * 2.0 * .pi
            // Circle coords
            let cx1 = cos(a) * R
            let cy1 = sin(a) * R
            // Square/Rounded-box coords
            let maxCoord = max(abs(cos(a)), abs(sin(a)))
            let cx2 = (cos(a) / maxCoord) * (R * 0.9)
            let cy2 = (sin(a) / maxCoord) * (R * 0.9)

            let x = cx + Self.lerp(cx1, cx2, shapeMorph)
            let y = cy + Self.lerp(cy1, cy2, shapeMorph)
            dots.append(OrbDot(x: x, y: y, z: 0.0, r: 1.8, white: 0.15, a: 0.85))
        }
        return finalize(dots: dots, lines: [])
    }

    private func finalize(dots: [OrbDot], lines: [OrbLine]) -> OrbFrame {
        var visibleDots = dots.filter { $0.a >= 0.02 }
        visibleDots.sort { $0.z < $1.z }
        let visibleLines = lines.filter { $0.a >= 0.02 }
        return OrbFrame(dots: visibleDots, lines: visibleLines)
    }

    // MARK: - Drawing
    public override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }

        let size = min(bounds.width, bounds.height)
        guard size > 4 else { return }

        ctx.saveGState()
        // Center drawing in view
        let offsetX = (bounds.width - size) / 2.0
        let offsetY = (bounds.height - size) / 2.0
        ctx.translateBy(x: offsetX, y: offsetY)

        let frame = generateFrame(size: size, t: clockTime)

        // Draw Lines
        for l in frame.lines {
            let color = computeColor(w: l.white, a: l.a)
            ctx.setStrokeColor(color)
            ctx.setLineWidth(CGFloat(l.w))
            ctx.beginPath()
            ctx.move(to: CGPoint(x: l.x1, y: l.y1))
            ctx.addLine(to: CGPoint(x: l.x2, y: l.y2))
            ctx.strokePath()
        }

        // Draw Dots
        for d in frame.dots {
            let color = computeColor(w: d.white, a: d.a)
            ctx.setFillColor(color)
            let r = CGFloat(max(0.4, d.r))
            let rect = CGRect(x: CGFloat(d.x) - r, y: CGFloat(d.y) - r, width: r * 2.0, height: r * 2.0)
            ctx.fillEllipse(in: rect)
        }

        ctx.restoreGState()
    }

    private func computeColor(w: Double, a: Double) -> CGColor {
        let clampedW = min(1.0, max(0.0, w))
        let clampedA = min(1.0, max(0.0, a))

        if let tint = tintColor {
            var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, alpha: CGFloat = 0
            tint.usingColorSpace(.sRGB)?.getRed(&r, green: &g, blue: &b, alpha: &alpha)
            let ramp = { (c: CGFloat) -> CGFloat in
                return self.isDarkMode ? c * CGFloat(1.0 - clampedW) : c + (1.0 - c) * CGFloat(clampedW)
            }
            return CGColor(srgbRed: ramp(r), green: ramp(g), blue: ramp(b), alpha: CGFloat(clampedA))
        }

        let gray = isDarkMode ? CGFloat(1.0 - clampedW) : CGFloat(clampedW)
        return CGColor(gray: gray, alpha: CGFloat(clampedA))
    }
}
