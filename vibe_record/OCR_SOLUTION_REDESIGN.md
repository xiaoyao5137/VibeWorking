# 记忆面包 OCR 方案重新设计

## 当前问题总结

### Apple Vision (macOS 原生)
- ❌ Swift 内联脚本每次编译超时 60 秒
- ❌ 可能导致系统死机
- ✅ 理论上性能最好（如果能正常工作）

### PaddleOCR
- ❌ 处理 670KB 图片需要 2+ 分钟
- ❌ 内存占用 9.7GB（使用 server 模型）
- ❌ 不适合实时采集场景

## 新方案：三层降级策略

### 方案 A：预编译 Swift OCR 工具（推荐）

**原理**：
- 将 Swift 脚本预编译成独立可执行文件
- 避免每次运行时重新编译
- 保留 Apple Vision 的性能优势

**优点**：
- 首次编译后，后续调用只需 50-200ms
- 内存占用低（<100MB）
- macOS 原生，无需安装依赖

**实施步骤**：
1. 创建独立的 Swift 项目
2. 编译成可执行文件
3. Python 通过 subprocess 调用编译后的二进制

**预期性能**：
- 首次编译：10-30 秒（一次性）
- 后续调用：50-200ms/张
- 内存占用：50-100MB

---

### 方案 B：使用 PyObjC 直接调用 Vision Framework

**原理**：
- Python 通过 PyObjC 桥接直接调用 macOS Vision API
- 无需 subprocess，无需编译

**优点**：
- 无编译开销
- 性能接近原生
- 代码更简洁

**缺点**：
- 需要安装 pyobjc-framework-Vision（约 50MB）
- 代码复杂度稍高

**实施步骤**：
1. `pip install pyobjc-framework-Vision`
2. 重写 AppleVisionBackend 使用 PyObjC

**预期性能**：
- 调用延迟：30-100ms/张
- 内存占用：50-100MB

---

### 方案 C：使用轻量级 PaddleOCR 模型

**原理**：
- 使用 PP-OCRv4 mobile 模型替代 server 模型
- 牺牲一些准确率换取速度

**优点**：
- 跨平台
- 无需编译

**缺点**：
- 仍然比 Apple Vision 慢
- 内存占用仍然较高（2-3GB）

**实施步骤**：
1. 修改 PaddleBackend 使用 mobile 模型
2. 调整参数优化性能

**预期性能**：
- 调用延迟：500-1000ms/张
- 内存占用：2-3GB

---

## 推荐方案：A + C 组合

**策略**：
1. **macOS**：使用预编译 Swift OCR（方案 A）
2. **其他平台**：使用 PaddleOCR mobile（方案 C）
3. **降级**：如果 Swift 失败，降级到 PaddleOCR

**优势**：
- macOS 用户获得最佳性能
- 跨平台兼容
- 有降级保障

---

## 立即实施：方案 A（预编译 Swift OCR）

### 步骤 1：创建独立 Swift 项目

```bash
# 创建项目目录
mkdir -p ai-sidecar/ocr/swift-ocr
cd ai-sidecar/ocr/swift-ocr

# 创建 Swift 源文件
cat > main.swift << 'EOF'
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
EOF

# 编译
swiftc -O -o memory-bread-ocr main.swift \
    -framework Foundation \
    -framework Vision \
    -framework AppKit

# 测试
./memory-bread-ocr /path/to/test.jpg
```

### 步骤 2：修改 AppleVisionBackend

使用预编译的二进制文件替代内联脚本。

### 步骤 3：性能对比测试

对比三种方案的实际性能。

---

## 时间估算

- **方案 A 实施**：30-45 分钟
- **方案 B 实施**：60-90 分钟
- **方案 C 实施**：15-20 分钟

**建议**：先实施方案 A（预编译 Swift），如果效果好就不需要其他方案。
