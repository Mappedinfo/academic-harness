import AppKit
import SwiftUI

@main
struct AcademicHarnessMacApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 1180, minHeight: 760)
        }
    }
}

struct ContentView: View {
    @StateObject private var model = WorkbenchModel()

    var body: some View {
        VStack(spacing: 10) {
            header
            statusRow
            controls
            mainSplit
        }
        .padding(14)
        .onAppear { model.reload() }
        .onChange(of: model.selectedTaskID) { _ in model.loadSelectedTaskFiles() }
        .onChange(of: model.selectedRunID) { _ in model.refreshFiles() }
    }

    private var header: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(model.statusColor)
                .frame(width: 12, height: 12)
            Text(model.statusText)
                .font(.headline)
                .frame(width: 92, alignment: .leading)
            TextField("项目路径", text: $model.projectPath)
                .textFieldStyle(.roundedBorder)
            Button("创建项目") { model.createProject() }
            Button("选择") { model.chooseProject() }
            Button("刷新") { model.reload() }
        }
    }

    private var statusRow: some View {
        HStack(spacing: 8) {
            ForEach(model.statusItems) { item in
                StatusPill(item: item)
            }
            Spacer()
        }
    }

    private var controls: some View {
        HStack(spacing: 8) {
            Text("CLI")
                .foregroundStyle(.secondary)
            TextField("academic-harness", text: $model.cliCommand)
                .textFieldStyle(.roundedBorder)
                .frame(minWidth: 240)
            Spacer()
            Button("Run Fake") { model.runSelectedTask(adapter: "fake") }
                .disabled(!model.canRunFake)
            Button("Run Qoder") { model.runSelectedTask(adapter: "qoder") }
                .disabled(!model.canRunQoder)
            Button("取消") { model.cancel() }
                .disabled(!model.isRunning)
            Button("验证") { model.validateSelectedRun() }
                .disabled(model.selectedRun == nil || model.isRunning)
        }
    }

    private var mainSplit: some View {
        HSplitView {
            taskList
            runList
            inspector
        }
    }

    private var taskList: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("任务")
                .font(.headline)
            List(selection: $model.selectedTaskID) {
                ForEach(model.tasks) { task in
                    Text(task.name)
                        .tag(task.id)
                }
            }
        }
        .frame(minWidth: 220)
    }

    private var runList: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("运行历史")
                .font(.headline)
            Table(model.runs, selection: $model.selectedRunID) {
                TableColumn("Run") { run in
                    Text(run.runID)
                        .font(.system(.caption, design: .monospaced))
                }
                TableColumn("状态") { run in
                    Text(run.status)
                }
                TableColumn("任务") { run in
                    Text(run.taskID)
                }
            }
        }
        .frame(minWidth: 360)
    }

    private var inspector: some View {
        VStack(spacing: 8) {
            Picker("检查器", selection: $model.selectedInspectorTab) {
                Text("文件").tag("Files")
                Text("任务").tag("Task")
                Text("Prompt").tag("Prompt")
                Text("设置").tag("Settings")
                Text("日志").tag("Log")
            }
            .pickerStyle(.segmented)

            switch model.selectedInspectorTab {
            case "Task":
                taskEditor
            case "Prompt":
                promptEditor
            case "Settings":
                settingsView
            case "Log":
                logView
            default:
                filesView
            }
        }
        .frame(minWidth: 440)
    }

    private var filesView: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("文件")
                    .font(.headline)
                Spacer()
                Button("打开报告") { model.openReport() }
                    .disabled(model.selectedRun?.reportPath == nil)
                Button("打开总结") { model.openSummary() }
                    .disabled(model.selectedRun?.summaryPath == nil)
                Button("显示文件夹") { model.revealRun() }
                    .disabled(model.selectedRun == nil)
            }
            List(model.files, id: \.path) { file in
                Button(file.lastPathComponent) {
                    NSWorkspace.shared.open(file)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var taskEditor: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(model.selectedTask?.name ?? "未选择任务")
                    .font(.headline)
                Spacer()
                Button("保存任务") { model.saveTask() }
                    .disabled(model.selectedTask == nil)
            }
            TextEditor(text: $model.taskText)
                .font(.system(.body, design: .monospaced))
                .overlay(editorBorder)
        }
    }

    private var promptEditor: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(model.promptPathDisplay.isEmpty ? "未找到 Prompt" : model.promptPathDisplay)
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                Button("保存 Prompt") { model.savePrompt() }
                    .disabled(model.promptURL == nil)
            }
            TextEditor(text: $model.promptText)
                .font(.system(.body, design: .monospaced))
                .overlay(editorBorder)
        }
    }

    private var settingsView: some View {
        VStack(alignment: .leading, spacing: 12) {
            GroupBox("Qoder Cloud Agent") {
                VStack(alignment: .leading, spacing: 8) {
                    labeledField("Runner", text: $model.qoderRunnerCommand)
                    labeledField("Config", text: $model.qoderConfigPath)
                    labeledField("Profile", text: $model.qoderProfile)
                    HStack {
                        Button("自动发现") { model.discoverQoderRunner() }
                            .disabled(!model.hasProject)
                        Button("安装/注册") { model.installQoderRunner() }
                            .disabled(!model.hasProject || model.isRunning)
                        Button("保存 Qoder 配置") { model.saveQoderConfig() }
                            .disabled(!model.hasProject)
                        Spacer()
                    }
                    Text(model.qoderMessage)
                        .font(.caption)
                        .foregroundStyle(model.qoderOK ? .green : .red)
                    Button("打开 project.yaml") { model.openProjectYAML() }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.vertical, 4)
            }

            GroupBox("LAN Worker") {
                VStack(alignment: .leading, spacing: 8) {
                    Toggle("启用", isOn: $model.lanEnabled)
                    labeledField("Server", text: $model.lanServer)
                    labeledField("Project Root", text: $model.lanProjectRoot)
                    labeledField("SSH Alias", text: $model.lanSSHAlias)
                    HStack {
                        Button("保存 LAN 配置") { model.saveLANConfig() }
                            .disabled(!model.hasProject)
                        Button("检查 LAN") { model.checkLAN() }
                            .disabled(!model.hasProject)
                        Spacer()
                    }
                    Text(model.lanMessage)
                        .font(.caption)
                        .foregroundStyle(model.lanOK ? .green : .orange)
                }
                .padding(.vertical, 4)
            }
            Spacer()
        }
        .padding(.top, 4)
    }

    private var logView: some View {
        TextEditor(text: $model.logText)
            .font(.system(.caption, design: .monospaced))
            .overlay(editorBorder)
    }

    private var editorBorder: some View {
        RoundedRectangle(cornerRadius: 6)
            .stroke(Color.secondary.opacity(0.25))
    }

    private func labeledField(_ label: String, text: Binding<String>) -> some View {
        HStack {
            Text(label)
                .frame(width: 96, alignment: .trailing)
                .foregroundStyle(.secondary)
            TextField(label, text: text)
                .textFieldStyle(.roundedBorder)
        }
    }
}

struct StatusPill: View {
    let item: StatusItem

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(item.ok ? Color.green : Color.red)
                .frame(width: 8, height: 8)
            Text(item.label)
                .font(.caption)
            Text(item.message)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color(NSColor.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }
}

struct StatusItem: Identifiable, Hashable {
    let id: String
    let label: String
    let ok: Bool
    let message: String
}

struct TaskItem: Identifiable, Hashable {
    let id: String
    let name: String
    let path: URL
}

struct RunItem: Identifiable, Hashable {
    let id: String
    let runID: String
    let status: String
    let taskID: String
    let runDir: URL
    let reportPath: URL?
    let summaryPath: URL?
    let manifestPath: URL
}

@MainActor
final class WorkbenchModel: ObservableObject {
    @Published var projectPath = ""
    @Published var cliCommand = WorkbenchModel.defaultCLICommand()
    @Published var tasks: [TaskItem] = []
    @Published var runs: [RunItem] = []
    @Published var files: [URL] = []
    @Published var selectedTaskID: String?
    @Published var selectedRunID: String?
    @Published var selectedInspectorTab = "Files"
    @Published var statusText = "Idle"
    @Published var statusColor = Color.gray
    @Published var statusItems: [StatusItem] = []
    @Published var taskText = ""
    @Published var promptText = ""
    @Published var promptPathDisplay = ""
    @Published var logText = ""
    @Published var qoderOK = false
    @Published var qoderMessage = "未加载项目"
    @Published var qoderRunnerCommand = "qoder-run"
    @Published var qoderConfigPath = ""
    @Published var qoderProfile = "default"
    @Published var lanOK = true
    @Published var lanEnabled = false
    @Published var lanServer = ""
    @Published var lanProjectRoot = ""
    @Published var lanSSHAlias = ""
    @Published var lanMessage = "LAN 未启用"

    var promptURL: URL?
    private var process: Process?

    init() {
        projectPath = FileManager.default.currentDirectoryPath
    }

    var isRunning: Bool {
        process != nil
    }

    var hasProject: Bool {
        FileManager.default.fileExists(atPath: projectURL.appendingPathComponent("project.yaml").path)
    }

    var canRunFake: Bool {
        !isRunning && selectedTask != nil && hasProject
    }

    var canRunQoder: Bool {
        canRunFake && qoderOK
    }

    var selectedTask: TaskItem? {
        tasks.first { $0.id == selectedTaskID }
    }

    var selectedRun: RunItem? {
        runs.first { $0.id == selectedRunID }
    }

    func createProject() {
        let panel = NSSavePanel()
        panel.title = "Create Academic Harness Project"
        panel.nameFieldStringValue = "academic-project"
        panel.canCreateDirectories = true
        guard panel.runModal() == .OK, let url = panel.url else { return }

        runCLI(
            arguments: ["init", url.path],
            currentDirectory: url.deletingLastPathComponent(),
            clearLog: true
        ) { [weak self] exitCode in
            guard let self else { return }
            if exitCode == 0 {
                self.projectPath = url.path
                self.reload()
            }
        }
    }

    func chooseProject() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            projectPath = url.path
            reload()
        }
    }

    func reload() {
        refreshTasks()
        refreshRuns()
        refreshFiles()
        loadSelectedTaskFiles()
        refreshProjectStatus(checkLAN: false)
    }

    func runSelectedTask(adapter: String) {
        guard let task = selectedTask else { return }
        runCLI(arguments: [
            "task", "run", task.path.path,
            "--project", projectURL.path,
            "--adapter", adapter
        ]) { [weak self] _ in
            self?.refreshRuns()
            self?.refreshFiles()
            self?.refreshProjectStatus(checkLAN: false)
        }
    }

    func validateSelectedRun() {
        guard let run = selectedRun else { return }
        runCLI(arguments: ["validate", run.runID, "--project", projectURL.path]) { [weak self] _ in
            self?.refreshRuns()
            self?.refreshFiles()
        }
    }

    func cancel() {
        process?.terminate()
        process = nil
        statusText = "Cancelled"
        statusColor = .orange
        appendLog("cancelled local process")
        reload()
    }

    func openReport() {
        guard let url = selectedRun?.reportPath else { return }
        NSWorkspace.shared.open(url)
    }

    func openSummary() {
        guard let url = selectedRun?.summaryPath else { return }
        NSWorkspace.shared.open(url)
    }

    func revealRun() {
        guard let run = selectedRun else { return }
        NSWorkspace.shared.activateFileViewerSelecting([run.runDir])
    }

    func openProjectYAML() {
        let url = projectURL.appendingPathComponent("project.yaml")
        if FileManager.default.fileExists(atPath: url.path) {
            NSWorkspace.shared.open(url)
        }
    }

    func discoverQoderRunner() {
        runShortCLI(arguments: ["qoder", "discover", "--project", projectURL.path, "--json"]) { [weak self] output, exitCode in
            guard let self else { return }
            if exitCode != 0 {
                self.qoderOK = false
                self.qoderMessage = output.isEmpty ? "未发现 qoder-run" : output
                return
            }
            self.applyQoderDiscovery(output)
            self.refreshProjectStatus(checkLAN: false)
        }
    }

    func installQoderRunner() {
        runCLI(arguments: ["qoder", "install", "--project", projectURL.path]) { [weak self] _ in
            self?.refreshProjectStatus(checkLAN: false)
        }
    }

    func saveQoderConfig() {
        var args = [
            "project", "set-qoder",
            "--project", projectURL.path
        ]
        let runner = qoderRunnerCommand.trimmingCharacters(in: .whitespacesAndNewlines)
        let config = qoderConfigPath.trimmingCharacters(in: .whitespacesAndNewlines)
        let profile = qoderProfile.trimmingCharacters(in: .whitespacesAndNewlines)
        if !runner.isEmpty {
            args.append(contentsOf: ["--runner-command", runner])
        }
        if !config.isEmpty {
            args.append(contentsOf: ["--config", config])
        }
        if !profile.isEmpty {
            args.append(contentsOf: ["--profile", profile])
        }
        runCLI(arguments: args) { [weak self] _ in
            self?.refreshProjectStatus(checkLAN: false)
        }
    }

    func saveTask() {
        guard let task = selectedTask else { return }
        do {
            try taskText.write(to: task.path, atomically: true, encoding: .utf8)
            appendLog("saved task: \(task.path.path)")
            refreshTasks()
            loadSelectedTaskFiles()
            refreshProjectStatus(checkLAN: false)
        } catch {
            statusText = "Failed"
            statusColor = .red
            appendLog("save task failed: \(error.localizedDescription)")
        }
    }

    func savePrompt() {
        guard let promptURL else { return }
        do {
            try promptText.write(to: promptURL, atomically: true, encoding: .utf8)
            appendLog("saved prompt: \(promptURL.path)")
        } catch {
            statusText = "Failed"
            statusColor = .red
            appendLog("save prompt failed: \(error.localizedDescription)")
        }
    }

    func saveLANConfig() {
        var args = [
            "project", "set-lan",
            "--project", projectURL.path,
            "--enabled", lanEnabled ? "true" : "false"
        ]
        args.append(contentsOf: ["--server", lanServer])
        args.append(contentsOf: ["--project-root", lanProjectRoot])
        args.append(contentsOf: ["--ssh-alias", lanSSHAlias])
        runCLI(arguments: args) { [weak self] _ in
            self?.refreshProjectStatus(checkLAN: false)
        }
    }

    func checkLAN() {
        refreshProjectStatus(checkLAN: true)
    }

    func refreshFiles() {
        guard let run = selectedRun else {
            files = []
            return
        }
        var found: [URL] = []
        if let enumerator = FileManager.default.enumerator(at: run.runDir, includingPropertiesForKeys: nil) {
            for case let url as URL in enumerator where !url.hasDirectoryPath {
                found.append(url)
            }
        }
        files = found.sorted { $0.path < $1.path }
    }

    func loadSelectedTaskFiles() {
        guard let task = selectedTask else {
            taskText = ""
            promptText = ""
            promptPathDisplay = ""
            promptURL = nil
            return
        }
        taskText = (try? String(contentsOf: task.path, encoding: .utf8)) ?? ""
        promptURL = resolvePromptURL(from: taskText)
        if let promptURL {
            promptPathDisplay = promptURL.path
            promptText = (try? String(contentsOf: promptURL, encoding: .utf8)) ?? ""
        } else {
            promptPathDisplay = ""
            promptText = ""
        }
    }

    private var projectURL: URL {
        URL(fileURLWithPath: projectPath, isDirectory: true)
    }

    private func refreshTasks() {
        let tasksURL = projectURL.appendingPathComponent("tasks", isDirectory: true)
        let contents = (try? FileManager.default.contentsOfDirectory(at: tasksURL, includingPropertiesForKeys: nil)) ?? []
        tasks = contents
            .filter { ["yaml", "yml"].contains($0.pathExtension.lowercased()) }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
            .map { TaskItem(id: $0.path, name: $0.lastPathComponent, path: $0) }
        if selectedTaskID == nil || !tasks.contains(where: { $0.id == selectedTaskID }) {
            selectedTaskID = tasks.first?.id
        }
    }

    private func refreshRuns() {
        let runsURL = projectURL
            .appendingPathComponent(".workbench", isDirectory: true)
            .appendingPathComponent("runs", isDirectory: true)
        let runDirs = (try? FileManager.default.contentsOfDirectory(at: runsURL, includingPropertiesForKeys: nil)) ?? []
        runs = runDirs.compactMap(loadRun).sorted { $0.runID > $1.runID }
        if selectedRunID == nil || !runs.contains(where: { $0.id == selectedRunID }) {
            selectedRunID = runs.first?.id
        }
    }

    private func loadRun(from url: URL) -> RunItem? {
        let manifest = url.appendingPathComponent("manifest.json")
        guard
            let data = try? Data(contentsOf: manifest),
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let runID = object["run_id"] as? String,
            let status = object["status"] as? String,
            let taskID = object["task_id"] as? String
        else {
            return nil
        }
        let report = (object["report_path"] as? String).map { URL(fileURLWithPath: $0) }
        let summary = (object["summary_path"] as? String).map { URL(fileURLWithPath: $0) }
        return RunItem(
            id: runID,
            runID: runID,
            status: status,
            taskID: taskID,
            runDir: url,
            reportPath: report,
            summaryPath: summary,
            manifestPath: manifest
        )
    }

    private func refreshProjectStatus(checkLAN: Bool) {
        let args = [
            "project", "status",
            "--project", projectURL.path,
            "--json"
        ] + (checkLAN ? ["--check-lan"] : [])
        runShortCLI(arguments: args) { [weak self] output, exitCode in
            guard let self else { return }
            if exitCode != 0 {
                self.qoderOK = false
                self.qoderMessage = output.isEmpty ? "状态检查失败" : output
                self.statusItems = [
                    StatusItem(id: "project", label: "项目", ok: false, message: "状态失败")
                ]
                return
            }
            self.applyProjectStatus(output)
        }
    }

    private func applyProjectStatus(_ jsonText: String) {
        guard
            let data = jsonText.data(using: .utf8),
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let checks = object["checks"] as? [String: Any]
        else {
            qoderOK = false
            qoderMessage = "无法解析项目状态"
            return
        }

        let project = checkValue("project", in: checks)
        let tasks = checkValue("tasks", in: checks)
        let runs = checkValue("runs", in: checks)
        let qoder = checkValue("qoder", in: checks)
        let lan = checkValue("lan", in: checks)
        qoderOK = qoder.ok
        qoderMessage = qoder.message
        lanOK = lan.ok
        lanMessage = lan.message
        statusItems = [
            StatusItem(id: "project", label: "项目", ok: project.ok, message: project.message),
            StatusItem(id: "qoder", label: "Qoder", ok: qoder.ok, message: qoder.message),
            StatusItem(id: "tasks", label: "任务", ok: tasks.ok, message: tasks.message),
            StatusItem(id: "runs", label: "Runs", ok: runs.ok, message: runs.message),
            StatusItem(id: "lan", label: "LAN", ok: lan.ok, message: lan.message)
        ]

        if let qoderObject = checks["qoder"] as? [String: Any] {
            qoderRunnerCommand = qoderObject["runner_command"] as? String ?? qoderRunnerCommand
            if let config = qoderObject["config"] as? String, !config.isEmpty {
                qoderConfigPath = config
            } else if let configPath = qoderObject["config_path"] as? String, !configPath.isEmpty {
                qoderConfigPath = configPath
            }
            qoderProfile = qoderObject["profile"] as? String ?? qoderProfile
        }

        if let lanObject = checks["lan"] as? [String: Any] {
            lanEnabled = lanObject["enabled"] as? Bool ?? false
            lanServer = lanObject["server"] as? String ?? ""
            lanProjectRoot = lanObject["project_root"] as? String ?? ""
            lanSSHAlias = lanObject["ssh_alias"] as? String ?? ""
        }
    }

    private func applyQoderDiscovery(_ jsonText: String) {
        guard
            let data = jsonText.data(using: .utf8),
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            qoderOK = false
            qoderMessage = "无法解析 Qoder 发现结果"
            return
        }
        qoderOK = object["ok"] as? Bool ?? false
        qoderMessage = object["message"] as? String ?? ""
        if let runner = object["runner_path"] as? String, !runner.isEmpty {
            qoderRunnerCommand = runner
        }
        if let config = object["config_path"] as? String, !config.isEmpty {
            qoderConfigPath = config
        }
        qoderProfile = object["profile"] as? String ?? qoderProfile
    }

    private func checkValue(_ name: String, in checks: [String: Any]) -> (ok: Bool, message: String) {
        guard let object = checks[name] as? [String: Any] else {
            return (false, "missing")
        }
        return (
            object["ok"] as? Bool ?? false,
            object["message"] as? String ?? ""
        )
    }

    private func resolvePromptURL(from taskYAML: String) -> URL? {
        for line in taskYAML.split(separator: "\n", omittingEmptySubsequences: false) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard trimmed.hasPrefix("prompt_file:") else { continue }
            let raw = trimmed
                .dropFirst("prompt_file:".count)
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
            guard !raw.isEmpty else { return nil }
            let path = String(raw)
            if path.hasPrefix("/") {
                return URL(fileURLWithPath: path)
            }
            return projectURL.appendingPathComponent(path)
        }
        return nil
    }

    private func runCLI(
        arguments: [String],
        currentDirectory: URL? = nil,
        clearLog: Bool = true,
        completion: ((Int32) -> Void)? = nil
    ) {
        guard process == nil else { return }

        let process = Process()
        let output = Pipe()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = [cliCommand] + arguments
        process.standardOutput = output
        process.standardError = output
        process.currentDirectoryURL = currentDirectory ?? projectURL

        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor in self?.appendLog(text.trimmingCharacters(in: .newlines)) }
        }

        process.terminationHandler = { [weak self] completed in
            Task { @MainActor in
                guard let self else { return }
                output.fileHandleForReading.readabilityHandler = nil
                self.process = nil
                self.statusText = completed.terminationStatus == 0 ? "Finished" : "Failed"
                self.statusColor = completed.terminationStatus == 0 ? .green : .red
                self.appendLog("exit=\(completed.terminationStatus)")
                completion?(completed.terminationStatus)
            }
        }

        do {
            statusText = "Running"
            statusColor = .yellow
            if clearLog {
                logText = ""
            }
            try process.run()
            self.process = process
            appendLog(([cliCommand] + arguments).joined(separator: " "))
        } catch {
            self.process = nil
            statusText = "Failed"
            statusColor = .red
            appendLog(error.localizedDescription)
            completion?(-1)
        }
    }

    private func runShortCLI(arguments: [String], completion: @escaping (String, Int32) -> Void) {
        let command = cliCommand
        let currentDirectory = projectURL
        Task.detached {
            let process = Process()
            let output = Pipe()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = [command] + arguments
            process.standardOutput = output
            process.standardError = output
            process.currentDirectoryURL = currentDirectory
            do {
                try process.run()
                process.waitUntilExit()
                let data = output.fileHandleForReading.readDataToEndOfFile()
                let text = String(data: data, encoding: .utf8) ?? ""
                await MainActor.run {
                    completion(text.trimmingCharacters(in: .whitespacesAndNewlines), process.terminationStatus)
                }
            } catch {
                await MainActor.run {
                    completion(error.localizedDescription, -1)
                }
            }
        }
    }

    private func appendLog(_ message: String) {
        guard !message.isEmpty else { return }
        if !logText.isEmpty {
            logText += "\n"
        }
        logText += message
        if logText.count > 16000 {
            logText = String(logText.suffix(16000))
        }
    }

    private static func defaultCLICommand() -> String {
        guard
            let resourceURL = Bundle.main.resourceURL,
            let bundledCLI = resourceURL
                .appendingPathComponent("bin", isDirectory: true)
                .appendingPathComponent("academic-harness")
                .path.removingPercentEncoding,
            FileManager.default.isExecutableFile(atPath: bundledCLI)
        else {
            return "academic-harness"
        }
        return bundledCLI
    }
}
