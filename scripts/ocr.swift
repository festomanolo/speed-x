import Cocoa
import Foundation
import Vision

guard CommandLine.arguments.count > 1 else {
    fputs("Usage: laya-ocr <image_path>\n", stderr)
    exit(1)
}

let imagePath = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: imagePath),
      let tiffData = image.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiffData),
      let cgImage = bitmap.cgImage else {
    fputs("Error: Could not load image at \(imagePath)\n", stderr)
    exit(2)
}

let request = VNRecognizeTextRequest { (request, error) in
    guard error == nil else {
        fputs("OCR Error: \(String(describing: error))\n", stderr)
        return
    }
    guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
    let lines = observations.compactMap { $0.topCandidates(1).first?.string }
    print(lines.joined(separator: "\n"))
}

request.recognitionLevel = .accurate
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    fputs("Failed to perform OCR: \(error)\n", stderr)
    exit(3)
}
