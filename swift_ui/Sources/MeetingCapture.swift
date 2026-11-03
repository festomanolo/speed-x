import Foundation

/// Meeting copilot's ears: transcribes the microphone on-device and sends each finished sentence to the
/// engine, which keeps the notes and writes the summary when the meeting ends ("end meeting").
/// (Microphone only: other people on a call are heard if they come out of your speakers.)
final class MeetingCapture {
    static let shared = MeetingCapture()
    private let recognizer = ContinuousRecognizer()
    private var silence: Timer?
    private(set) var active = false
    var onSentence: ((String) -> Void)?

    init() {
        recognizer.onPartial = { [weak self] _ in
            // A pause of about 1.4 s closes the sentence.
            self?.silence?.invalidate()
            self?.silence = Timer.scheduledTimer(withTimeInterval: 1.4, repeats: false) { _ in self?.recognizer.endSegment() }
        }
        recognizer.onSegment = { [weak self] text in
            EngineClient.shared.meetingLine(text)
            self?.onSentence?(text)
        }
    }

    /// False if on-device recognition isn't available.
    @discardableResult
    func start() -> Bool {
        guard !active else { return true }
        WakeWordListener.shared.setBusy(true)
        guard recognizer.start() else {
            WakeWordListener.shared.setBusy(false)
            return false
        }
        active = true
        return true
    }

    func stop() {
        guard active else { return }
        recognizer.endSegment()   // flush the last words
        recognizer.stop()
        silence?.invalidate(); silence = nil
        active = false
        WakeWordListener.shared.setBusy(false)
    }
}
