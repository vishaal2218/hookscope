// Hookscope.app: a Dock + menu-bar wrapper that runs the local Hookscope engine and opens it in the browser.
// Build with mac/build-app.sh. The engine itself lives in the project folder named by HookscopeRoot in Info.plist.

import AppKit

let portStart = 8777
let portTries = 15
let readyTimeout: TimeInterval = 60
let maxLogBytes = 5_000_000
let extraPath = ["/opt/homebrew/bin", "/usr/local/bin", "\(NSHomeDirectory())/.local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var server: Process?
    private var statusItem: NSStatusItem?
    private var port: Int?
    private var root = URL(fileURLWithPath: "/")
    private var logURL = URL(fileURLWithPath: "/dev/null")
    private var quitting = false
    private let statusLine = NSMenuItem(title: "Starting…", action: nil, keyEquivalent: "")
    private let work = DispatchQueue(label: "hookscope.app")

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard let path = Bundle.main.object(forInfoDictionaryKey: "HookscopeRoot") as? String,
              FileManager.default.isExecutableFile(atPath: path + "/.venv/bin/python") else {
            let path = Bundle.main.object(forInfoDictionaryKey: "HookscopeRoot") as? String ?? "(not set)"
            fail("Hookscope's folder isn't where it used to be",
                 "The app looks for it at:\n\(path)\n\nMove the folder back, or rebuild the app from its new place by running mac/build-app.sh.")
            return
        }
        root = URL(fileURLWithPath: path)
        logURL = root.appendingPathComponent("data/hookscope.log")
        buildMenus()
        ensureRunning(openBrowser: true)
        checkBrowserAccess()
    }

    // MARK: Browser login access

    private static let browserFolders = [
        "chrome": "Library/Application Support/Google/Chrome",
        "brave": "Library/Application Support/BraveSoftware/Brave-Browser",
        "edge": "Library/Application Support/Microsoft Edge",
        "firefox": "Library/Application Support/Firefox/Profiles",
        "safari": "Library/Containers/com.apple.Safari/Data/Library/Cookies",
    ]
    private static let skipAccessKey = "skipBrowserAccessPrompt"
    private static let fullDiskAccessPane = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"

    private func configuredBrowser() -> String {
        let url = root.appendingPathComponent("data/settings.json")
        guard let data = try? Data(contentsOf: url),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let browser = json["cookies_browser"] as? String else { return "chrome" }
        return browser
    }

    /// Instagram downloads borrow the browser's login; macOS blocks apps (not Terminal) from reading it
    /// until the user switches the app on under Full Disk Access. Explain that once, with a direct button.
    private func checkBrowserAccess() {
        let browser = configuredBrowser()
        guard let relative = Self.browserFolders[browser],
              !UserDefaults.standard.bool(forKey: Self.skipAccessKey) else { return }
        let folder = URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent(relative)
        guard FileManager.default.fileExists(atPath: folder.path) else { return }
        do {
            _ = try FileManager.default.contentsOfDirectory(atPath: folder.path)
        } catch {
            let alert = NSAlert()
            alert.messageText = "Let Hookscope read your \(browser.capitalized) login?"
            alert.informativeText = "Instagram only lets logged-in browsers download reels and carousels. macOS is blocking Hookscope from reading your \(browser.capitalized) login.\n\nClick Open Settings, switch on Hookscope under Full Disk Access, then choose Quit & Reopen. Everything else works without this."
            alert.addButton(withTitle: "Open Settings")
            alert.addButton(withTitle: "Not now")
            alert.showsSuppressionButton = true
            alert.suppressionButton?.title = "Don't ask again"
            NSApp.activate(ignoringOtherApps: true)
            let answer = alert.runModal()
            if alert.suppressionButton?.state == .on { UserDefaults.standard.set(true, forKey: Self.skipAccessKey) }
            if answer == .alertFirstButtonReturn, let url = URL(string: Self.fullDiskAccessPane) {
                NSWorkspace.shared.open(url)
            }
        }
    }

    // Clicking the Dock icon again opens the page again.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        ensureRunning(openBrowser: true)
        return true
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        quitting = true
        stopServer()
        return .terminateNow
    }

    // MARK: Menus

    private func buildMenus() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        item.button?.image = NSImage(systemSymbolName: "scope", accessibilityDescription: "Hookscope")
        item.button?.image?.isTemplate = true
        item.menu = makeMenu()
        statusItem = item

        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Open Hookscope", action: #selector(openPage), keyEquivalent: "o")
        appMenu.addItem(withTitle: "Show Log", action: #selector(showLog), keyEquivalent: "l")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit Hookscope", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let appItem = NSMenuItem()
        appItem.submenu = appMenu
        let main = NSMenu()
        main.addItem(appItem)
        NSApp.mainMenu = main
    }

    private func makeMenu() -> NSMenu {
        let menu = NSMenu()
        statusLine.isEnabled = false
        menu.addItem(statusLine)
        menu.addItem(.separator())
        menu.addItem(withTitle: "Open Hookscope", action: #selector(openPage), keyEquivalent: "o")
        menu.addItem(withTitle: "Show Log", action: #selector(showLog), keyEquivalent: "")
        menu.addItem(withTitle: "Show Hookscope Folder", action: #selector(showFolder), keyEquivalent: "")
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit Hookscope", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        return menu
    }

    private func setStatus(_ text: String) {
        DispatchQueue.main.async { self.statusLine.title = text }
    }

    @objc private func openPage() { ensureRunning(openBrowser: true) }

    @objc private func showLog() {
        if !FileManager.default.fileExists(atPath: logURL.path) {
            FileManager.default.createFile(atPath: logURL.path, contents: Data())
        }
        NSWorkspace.shared.open(logURL)
    }

    @objc private func showFolder() { NSWorkspace.shared.activateFileViewerSelecting([root]) }

    // MARK: Engine

    private func ensureRunning(openBrowser: Bool) {
        work.async {
            if let found = self.findRunning() {
                self.ready(on: found, openBrowser: openBrowser)
                return
            }
            self.setStatus("Starting…")
            do {
                try self.startServer()
            } catch {
                self.fail("Hookscope couldn't start", "\(error.localizedDescription)\n\nShow Log has the details.")
                return
            }
            let deadline = Date().addingTimeInterval(readyTimeout)
            while Date() < deadline {
                if let found = self.findRunning() {
                    self.ready(on: found, openBrowser: openBrowser)
                    return
                }
                if self.server?.isRunning == false { break }
                Thread.sleep(forTimeInterval: 0.5)
            }
            self.setStatus("Not running")
            self.fail("Hookscope didn't start", "The engine stopped or took too long. Show Log has the details.", showLogButton: true)
        }
    }

    private func ready(on found: Int, openBrowser: Bool) {
        port = found
        setStatus("Running on port \(found)")
        if openBrowser, let url = URL(string: "http://127.0.0.1:\(found)/") {
            DispatchQueue.main.async { NSWorkspace.shared.open(url) }
        }
    }

    /// The first port answering /api/ping as Hookscope (another app may own 8777, so we check what answers).
    private func findRunning() -> Int? {
        for candidate in portStart..<(portStart + portTries) where ping(candidate) {
            return candidate
        }
        return nil
    }

    private func ping(_ candidate: Int) -> Bool {
        guard let url = URL(string: "http://127.0.0.1:\(candidate)/api/ping") else { return false }
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 0.8)
        request.httpMethod = "GET"
        let done = DispatchSemaphore(value: 0)
        var isHookscope = false
        URLSession.shared.dataTask(with: request) { data, _, _ in
            isHookscope = data.flatMap { String(data: $0, encoding: .utf8) }?.contains("\"hookscope\"") ?? false
            done.signal()
        }.resume()
        _ = done.wait(timeout: .now() + 1.5)
        return isHookscope
    }

    private func openLog() throws -> FileHandle {
        try FileManager.default.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        let size = (try? FileManager.default.attributesOfItem(atPath: logURL.path)[.size] as? Int) ?? 0
        if size > maxLogBytes || !FileManager.default.fileExists(atPath: logURL.path) {
            FileManager.default.createFile(atPath: logURL.path, contents: Data())
        }
        let handle = try FileHandle(forWritingTo: logURL)
        handle.seekToEndOfFile()
        handle.write("\n--- Hookscope.app started \(Date()) ---\n".data(using: .utf8)!)
        return handle
    }

    private func startServer() throws {
        let process = Process()
        process.executableURL = root.appendingPathComponent(".venv/bin/python")
        process.arguments = ["-m", "hookscope", "--no-browser"]
        process.currentDirectoryURL = root
        var env = ProcessInfo.processInfo.environment
        let current = env["PATH"].map { [$0] } ?? []
        env["PATH"] = (extraPath + current).joined(separator: ":")
        env["PYTHONUNBUFFERED"] = "1"
        process.environment = env
        let log = try openLog()
        process.standardOutput = log
        process.standardError = log
        process.terminationHandler = { [weak self] proc in
            guard let self, !self.quitting else { return }
            self.setStatus("Stopped (exit \(proc.terminationStatus)). Open Hookscope restarts it.")
        }
        try process.run()
        server = process
    }

    /// Stops only the engine this app started; one started from Terminal is left alone.
    private func stopServer() {
        guard let process = server, process.isRunning else { return }
        process.terminate()
        let deadline = Date().addingTimeInterval(4)
        while process.isRunning && Date() < deadline { Thread.sleep(forTimeInterval: 0.1) }
        if process.isRunning { kill(process.processIdentifier, SIGKILL) }
    }

    private func fail(_ title: String, _ detail: String, showLogButton: Bool = false) {
        DispatchQueue.main.async {
            let alert = NSAlert()
            alert.messageText = title
            alert.informativeText = detail
            alert.alertStyle = .warning
            alert.addButton(withTitle: "OK")
            if showLogButton { alert.addButton(withTitle: "Show Log") }
            NSApp.activate(ignoringOtherApps: true)
            if alert.runModal() == .alertSecondButtonReturn { self.showLog() }
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)

// A plain `kill` (SIGTERM) goes through the normal quit path too, so the engine is stopped, not orphaned.
signal(SIGTERM, SIG_IGN)
let terminateSignal = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
terminateSignal.setEventHandler { NSApp.terminate(nil) }
terminateSignal.resume()

app.run()
