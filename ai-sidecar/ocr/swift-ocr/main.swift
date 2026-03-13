import Foundation
import Vision
import AppKit

// 命令行参数：图片路径
guard CommandLine.arguments.count > 1 else {
    print(#"{"error": "缺少图片路径参数"}"#)
    exit(1)
}

let imagePath = CommandLine.arguments[1]
let imageURL  = URL(fileURLWithPath: imagePath)

guard let nsImage = NSImage(contentsOf: imageURL),
      let cgImage = nsImage.cgImage(forProposedRect: nil, context: nil, hints: nil)
else {
    print(#"{"error": "无法加载图片"}"#)
    exit(1)
}

var results: [[String: Any]] = []
let semaphore = DispatchSemaphore(value: 0)

let request = VNRecognizeTextRequest { req, err in
    defer { semaphore.signal() }
    guard err == nil, let obs = req.results as? [VNRecognizedTextObservation] else { return }
    for ob in obs {
        if let candidate = ob.topCandidates(1).first, !candidate.string.isEmpty {
            results.append(["text": candidate.string, "confidence": Double(candidate.confidence)])
        }
    }
}

request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US", "ja-JP"]

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try? handler.perform([request])
semaphore.wait()

let output = try! JSONSerialization.data(withJSONObject: ["results": results])
print(String(data: output, encoding: .utf8)!)
