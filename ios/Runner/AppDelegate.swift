import Flutter
import UIKit
import UniformTypeIdentifiers
import UserNotifications

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate, UIDocumentPickerDelegate {
  private var pendingResult: FlutterResult?
  private var selectedURL: URL?
  private var exporting = false

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    UNUserNotificationCenter.current().delegate = self
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    let channel = FlutterMethodChannel(
      name: "app.offlinevault/security",
      binaryMessenger: engineBridge.applicationRegistrar.messenger()
    )
    channel.setMethodCallHandler { [weak self] call, result in
      guard let self = self else {
        result(FlutterError(code: "unavailable", message: "应用状态不可用。", details: nil))
        return
      }
      let args = call.arguments as? [String: Any] ?? [:]
      switch call.method {
      case "protectDirectory":
        guard let path = args["path"] as? String else {
          result(FlutterError(code: "invalid_path", message: "资料库路径无效。", details: nil))
          return
        }
        do {
          var url = URL(fileURLWithPath: path, isDirectory: true)
          var values = URLResourceValues()
          values.isExcludedFromBackup = true
          try url.setResourceValues(values)
          try FileManager.default.setAttributes(
            [.protectionKey: FileProtectionType.complete], ofItemAtPath: path)
          result(nil)
        } catch {
          result(FlutterError(code: "protection_failed", message: "无法排除系统备份或设置文件保护。", details: nil))
        }
      case "pickFile", "exportBackup":
        guard self.pendingResult == nil else {
          result(FlutterError(code: "busy", message: "系统文件对话框正在进行。", details: nil))
          return
        }
        let picker: UIDocumentPickerViewController
        self.exporting = call.method == "exportBackup"
        if self.exporting {
          let cacheRoot = FileManager.default.urls(
            for: .cachesDirectory, in: .userDomainMask).first?.path
          guard let path = args["path"] as? String,
                let cacheRoot = cacheRoot,
                URL(fileURLWithPath: path).standardizedFileURL.path.hasPrefix(cacheRoot + "/"),
                path.hasSuffix(".ovault") else {
            result(FlutterError(code: "invalid_export", message: "加密备份路径无效。", details: nil))
            return
          }
          picker = UIDocumentPickerViewController(
            forExporting: [URL(fileURLWithPath: path)], asCopy: true)
        } else {
          let kind = args["kind"] as? String
          let types: [UTType] = kind == "backup" ? [.data] :
            kind == "image" ? [.jpeg, .png] : [.jpeg, .png, .pdf]
          picker = UIDocumentPickerViewController(forOpeningContentTypes: types, asCopy: false)
        }
        picker.delegate = self
        picker.allowsMultipleSelection = false
        guard var presenter = UIApplication.shared.connectedScenes
          .compactMap({ $0 as? UIWindowScene })
          .flatMap({ $0.windows })
          .first(where: { $0.isKeyWindow })?.rootViewController else {
          result(FlutterError(code: "no_window", message: "无法显示文件选择器。", details: nil))
          return
        }
        while let presented = presenter.presentedViewController { presenter = presented }
        self.pendingResult = result
        presenter.present(picker, animated: true)
      case "readSelectedFile":
        guard let uri = args["uri"] as? String,
              let url = self.selectedURL, url.absoluteString == uri,
              let maximum = args["maximum"] as? Int, maximum > 0, maximum <= 268435456 else {
          result(FlutterError(code: "invalid_selection", message: "文件授权已失效，请重新选择。", details: nil))
          return
        }
        DispatchQueue.global(qos: .userInitiated).async {
          let scoped = url.startAccessingSecurityScopedResource()
          defer { if scoped { url.stopAccessingSecurityScopedResource() } }
          var coordinationError: NSError?
          var readError: Error?
          var output: Data?
          NSFileCoordinator().coordinate(readingItemAt: url, options: [], error: &coordinationError) { coordinated in
            do {
              let handle = try FileHandle(forReadingFrom: coordinated)
              defer { handle.closeFile() }
              var bytes = Data()
              while let chunk = try handle.read(upToCount: 65536), !chunk.isEmpty {
                if bytes.count + chunk.count > maximum {
                  throw NSError(domain: "OfflineVault.SizeLimit", code: 1)
                }
                bytes.append(chunk)
              }
              output = bytes
            } catch {
              readError = error
            }
          }
          DispatchQueue.main.async {
            if coordinationError != nil || readError != nil || output == nil {
              result(FlutterError(code: "read_failed", message: "读取失败：文件过大、授权失效或文件不可用。", details: nil))
            } else {
              result(FlutterStandardTypedData(bytes: output!))
            }
          }
        }
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
    guard let result = pendingResult else { return }
    pendingResult = nil
    guard let url = urls.first else {
      result(FlutterError(code: "no_selection", message: "系统没有返回文件。", details: nil))
      return
    }
    if exporting {
      result(true)
    } else {
      selectedURL = url
      result(["uri": url.absoluteString, "name": url.lastPathComponent])
    }
  }

  func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
    let result = pendingResult
    pendingResult = nil
    result?(exporting ? false : nil)
  }
}
