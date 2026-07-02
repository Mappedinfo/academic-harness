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

    private var mainSplit: some View {
        HSplitView {
            leftSidebar
            promptWorkbench
            rightWorkbench
        }
    }

    private var leftSidebar: some View {
        VStack(spacing: 10) {
            taskList
            Divider()
            runList
        }
        .frame(minWidth: 260)
    }

    private var taskList: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("任务")
                .font(.headline)
            List(selection: $model.selectedTaskID) {
                ForEach(model.tasks) { task in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(task.name)
                        Text("\(task.type) · \(task.mode)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .tag(task.id)
                }
            }
        }
        .frame(minHeight: 240)
    }

    private var runList: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("运行历史")
                .font(.headline)
            Table(model.runs, selection: $model.selectedRunID) {
                TableColumn("运行") { run in
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
        .frame(minHeight: 280)
    }

    private var promptWorkbench: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("任务描述 / 提示词")
                        .font(.headline)
                    Text(model.promptPathDisplay.isEmpty ? "选择左侧任务后编辑提示词" : model.promptPathDisplay)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer()
                Button("保存") { _ = model.savePrompt() }
                    .disabled(!model.canSavePrompt)
            }
            TextEditor(text: $model.promptText)
                .font(.system(.body, design: .monospaced))
                .overlay(editorBorder)
                .frame(minHeight: 520)
        }
        .frame(minWidth: 460)
    }

    private var rightWorkbench: some View {
        VStack(spacing: 10) {
            runOptionsPanel
            qoderStatusPanel
            lanStatusPanel
            Picker("", selection: $model.selectedInspectorTab) {
                Text("文件").tag("Files")
                Text("高级任务").tag("Task")
                Text("设置").tag("Settings")
                Text("日志").tag("Log")
            }
            .pickerStyle(.segmented)
            .labelsHidden()

            switch model.selectedInspectorTab {
            case "Task":
                taskEditor
            case "Settings":
                settingsView
            case "Log":
                logView
            default:
                filesView
            }
        }
        .frame(minWidth: 380)
    }

    private var runOptionsPanel: some View {
        GroupBox("运行") {
            VStack(alignment: .leading, spacing: 10) {
                Picker("运行模式", selection: $model.runMode) {
                    ForEach(RunMode.allCases) { mode in
                        Text(mode.title).tag(mode)
                    }
                }
                .pickerStyle(.segmented)

                Text(model.runModeDetail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                HStack {
                    Button("启动运行") { model.startRun() }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                        .keyboardShortcut(.return, modifiers: [.command])
                        .disabled(!model.canStartRun)
                    Button("取消") { model.cancel() }
                        .disabled(!model.isRunning)
                    Button("验证") { model.validateSelectedRun() }
                        .disabled(model.selectedRun == nil || model.isRunning)
                    Spacer()
                }

                Text(model.startReadinessText)
                    .font(.caption)
                    .foregroundStyle(model.canStartRun ? .green : .orange)
            }
            .padding(.vertical, 4)
        }
    }

    private var qoderStatusPanel: some View {
        GroupBox("Qoder") {
            HStack(alignment: .top, spacing: 8) {
                Circle()
                    .fill(model.qoderOK ? Color.green : Color.red)
                    .frame(width: 10, height: 10)
                    .padding(.top, 4)
                VStack(alignment: .leading, spacing: 4) {
                    Text(model.qoderStatusTitle)
                        .font(.headline)
                    Text(model.qoderStatusDetail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
            }
            .padding(.vertical, 4)
        }
    }

    private var lanStatusPanel: some View {
        GroupBox("LAN") {
            HStack(alignment: .top, spacing: 8) {
                Circle()
                    .fill(model.lanOK ? Color.green : Color.orange)
                    .frame(width: 10, height: 10)
                    .padding(.top, 4)
                VStack(alignment: .leading, spacing: 4) {
                    Text(model.lanEnabled ? "LAN 已启用" : "LAN 未启用")
                        .font(.headline)
                    Text(model.lanMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
            }
            .padding(.vertical, 4)
        }
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

    private var settingsView: some View {
        VStack(alignment: .leading, spacing: 12) {
            qoderSettingsCard

            GroupBox("局域网 Worker") {
                VStack(alignment: .leading, spacing: 8) {
                    Toggle("启用", isOn: $model.lanEnabled)
                    labeledField("服务器", text: $model.lanServer)
                    labeledField("项目根目录", text: $model.lanProjectRoot)
                    labeledField("SSH 别名", text: $model.lanSSHAlias)
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
            DisclosureGroup("应用高级设置", isExpanded: $model.showAdvancedAppSettings) {
                VStack(alignment: .leading, spacing: 8) {
                    labeledField("CLI", text: $model.cliCommand)
                    Text("打包版通常不需要改这里。只有在调试源码版 CLI 时才需要覆盖。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
            }
            Spacer()
        }
        .padding(.top, 4)
    }

    private var qoderSettingsCard: some View {
        GroupBox("Qoder 云端 Agent") {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .center, spacing: 8) {
                    Circle()
                        .fill(model.qoderOK ? Color.green : Color.red)
                        .frame(width: 10, height: 10)
                    Text(model.qoderStatusTitle)
                        .font(.headline)
                    Spacer()
                }
                Text(model.qoderStatusDetail)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                HStack {
                    Button(model.qoderOK ? "重新检查" : "一键配置 Qoder") {
                        if model.qoderOK {
                            model.discoverQoderRunner()
                        } else {
                            model.setupQoderRunner()
                        }
                    }
                    .disabled(!model.hasProject || model.isRunning)
                    Button("使用系统配置") { model.resetQoderToSystem() }
                        .disabled(!model.hasProject || model.isRunning)
                    Spacer()
                }

                DisclosureGroup("高级配置", isExpanded: $model.showAdvancedQoderSettings) {
                    VStack(alignment: .leading, spacing: 8) {
                        labeledField("Runner", text: $model.qoderRunnerCommand)
                        labeledField("Config", text: $model.qoderConfigPath)
                        labeledField("Profile", text: $model.qoderProfile)
                        HStack {
                            Button("保存项目覆盖") { model.saveQoderConfig() }
                                .disabled(!model.hasProject)
                            Button("打开 project.yaml") { model.openProjectYAML() }
                                .disabled(!model.hasProject)
                            Spacer()
                        }
                        Text(model.qoderTechnicalSummary)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.vertical, 4)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 4)
        }
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
    let type: String
    let mode: String
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

enum RunMode: String, CaseIterable, Identifiable {
    case fullCloud
    case localControl
    case fake
    case qoderCLI

    var id: String { rawValue }

    var title: String {
        switch self {
        case .fullCloud:
            return "全云端"
        case .localControl:
            return "本地把控"
        case .fake:
            return "Fake 测试"
        case .qoderCLI:
            return "Qoder CLI"
        }
    }

    var adapter: String {
        switch self {
        case .fullCloud:
            return "qoder_cloud"
        case .localControl:
            return "local_control"
        case .fake:
            return "fake"
        case .qoderCLI:
            return "qoder"
        }
    }

    var requiresQoder: Bool {
        self == .fullCloud || self == .qoderCLI
    }

    var detail: String {
        switch self {
        case .fullCloud:
            return "本地只提交任务和收取 artifacts，实际调研与拆解由 Qoder Cloud Agent 完成。"
        case .localControl:
            return "本地生成控制计划和检查材料，不启动远程云端运行。"
        case .fake:
            return "离线生成 fixture 输出，用于检查项目、UI 和 validator 是否能跑通。"
        case .qoderCLI:
            return "通过已注册的 qoder-run CLI 兼容路径运行。"
        }
    }
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
    @Published var runMode: RunMode = .localControl
    @Published var statusText = "空闲"
    @Published var statusColor = Color.gray
    @Published var statusItems: [StatusItem] = []
    @Published var taskText = ""
    @Published var promptText = ""
    @Published var promptPathDisplay = ""
    @Published var promptUsesTaskObjective = false
    @Published var logText = ""
    @Published var qoderOK = false
    @Published var qoderMessage = "未加载项目"
    @Published var qoderRunnerCommand = "qoder-run"
    @Published var qoderConfigPath = ""
    @Published var qoderProfile = "default"
    @Published var qoderRunnerPath = ""
    @Published var qoderResolvedConfigPath = ""
    @Published var qoderSource = ""
    @Published var qoderRegistryPath = ""
    @Published var showAdvancedQoderSettings = false
    @Published var showAdvancedAppSettings = false
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

    var canRunBase: Bool {
        !isRunning && selectedTask != nil && hasProject
    }

    var canStartRun: Bool {
        canRunBase && (!runMode.requiresQoder || qoderOK)
    }

    var canSavePrompt: Bool {
        selectedTask != nil && (promptURL != nil || promptUsesTaskObjective)
    }

    var runModeDetail: String {
        runMode.detail
    }

    var startReadinessText: String {
        if isRunning {
            return "正在运行中"
        }
        if !hasProject {
            return "请先创建或选择项目"
        }
        if selectedTask == nil {
            return "请先选择任务"
        }
        if runMode.requiresQoder && !qoderOK {
            return "当前模式需要 Qoder 配置就绪"
        }
        return "将以“\(runMode.title)”启动当前任务"
    }

    var selectedTask: TaskItem? {
        tasks.first { $0.id == selectedTaskID }
    }

    var selectedRun: RunItem? {
        runs.first { $0.id == selectedRunID }
    }

    var qoderStatusTitle: String {
        if !hasProject {
            return "请先创建或选择项目"
        }
        return qoderOK ? "Qoder 已就绪" : "Qoder 尚未配置好"
    }

    var qoderStatusDetail: String {
        if !hasProject {
            return "创建或选择项目后，应用会自动检查本机 Qoder Runner。"
        }
        if qoderOK {
            let runner = shortName(qoderRunnerPath.isEmpty ? qoderRunnerCommand : qoderRunnerPath)
            let config = shortName(qoderResolvedConfigPath.isEmpty ? qoderConfigPath : qoderResolvedConfigPath)
            let nextStep = selectedTask == nil ? "请先在左侧选择一个任务。" : "选择运行模式后点击“启动运行”。"
            return "已连接 \(runner)，使用 \(config)，Profile: \(qoderProfile)。\(nextStep)"
        }
        return "点击“一键配置 Qoder”会安装/注册 qoder-run，并让项目回到系统自动发现模式。"
    }

    var qoderTechnicalSummary: String {
        [
            "来源: \(qoderSource.isEmpty ? "未发现" : qoderSource)",
            "Runner: \(qoderRunnerPath.isEmpty ? qoderRunnerCommand : qoderRunnerPath)",
            "Config: \(qoderResolvedConfigPath.isEmpty ? qoderConfigPath : qoderResolvedConfigPath)",
            "Registry: \(qoderRegistryPath.isEmpty ? "默认位置" : qoderRegistryPath)",
            "状态: \(qoderMessage)"
        ].joined(separator: "\n")
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

    func startRun() {
        guard canStartRun else { return }
        guard savePrompt() else { return }
        runSelectedTask(adapter: runMode.adapter)
    }

    private func runSelectedTask(adapter: String) {
        guard let task = selectedTask else { return }
        runCLI(arguments: [
            "task", "run", task.path.path,
            "--project", projectURL.path,
            "--adapter", adapter
        ]) { [weak self] _ in
            guard let self else { return }
            self.refreshRuns()
            self.selectedRunID = self.runs.first?.id
            self.refreshFiles()
            self.refreshProjectStatus(checkLAN: false)
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
        statusText = "已取消"
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

    func setupQoderRunner() {
        runCLI(arguments: ["qoder", "install", "--project", projectURL.path]) { [weak self] exitCode in
            guard let self else { return }
            if exitCode == 0 {
                self.resetQoderToSystem(clearLog: false)
            } else {
                self.refreshProjectStatus(checkLAN: false)
            }
        }
    }

    func resetQoderToSystem(clearLog: Bool = true) {
        runCLI(
            arguments: ["project", "reset-qoder", "--project", projectURL.path],
            clearLog: clearLog
        ) { [weak self] _ in
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
            statusText = "失败"
            statusColor = .red
            appendLog("save task failed: \(error.localizedDescription)")
        }
    }

    @discardableResult
    func savePrompt() -> Bool {
        guard let task = selectedTask else { return false }
        do {
            if let promptURL {
                try promptText.write(to: promptURL, atomically: true, encoding: .utf8)
                appendLog("saved prompt: \(promptURL.path)")
            } else if promptUsesTaskObjective {
                taskText = updateObjective(in: taskText, with: promptText)
                try taskText.write(to: task.path, atomically: true, encoding: .utf8)
                appendLog("saved objective: \(task.path.path)")
                refreshTasks()
            } else {
                statusText = "失败"
                statusColor = .red
                appendLog("save prompt failed: no prompt_file or plan.objective")
                return false
            }
            return true
        } catch {
            statusText = "失败"
            statusColor = .red
            appendLog("save prompt failed: \(error.localizedDescription)")
            return false
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
            promptUsesTaskObjective = false
            return
        }
        taskText = (try? String(contentsOf: task.path, encoding: .utf8)) ?? ""
        runMode = defaultRunMode(for: task)
        promptURL = resolvePromptURL(from: taskText)
        if let promptURL {
            promptUsesTaskObjective = false
            promptPathDisplay = promptURL.path
            promptText = (try? String(contentsOf: promptURL, encoding: .utf8)) ?? ""
        } else {
            promptUsesTaskObjective = true
            promptPathDisplay = "任务 YAML: plan.objective"
            promptText = taskYAMLValue("objective", in: taskText) ?? ""
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
            .map {
                let text = (try? String(contentsOf: $0, encoding: .utf8)) ?? ""
                let type = taskYAMLValue("type", in: text) ?? "task"
                let mode = taskYAMLValue("mode", in: text) ?? "auto"
                return TaskItem(id: $0.path, name: $0.lastPathComponent, path: $0, type: type, mode: mode)
            }
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
            StatusItem(id: "project", label: "项目", ok: project.ok, message: project.ok ? "已打开" : "缺失"),
            StatusItem(id: "qoder", label: "Qoder", ok: qoder.ok, message: qoder.ok ? "已就绪" : "未配置"),
            StatusItem(id: "tasks", label: "任务", ok: tasks.ok, message: tasks.ok ? "有任务" : "无任务"),
            StatusItem(id: "runs", label: "运行", ok: runs.ok, message: runs.ok ? "已初始化" : "缺失"),
            StatusItem(id: "lan", label: "LAN", ok: lan.ok, message: lan.ok ? "正常" : "需检查")
        ]

        if let qoderObject = checks["qoder"] as? [String: Any] {
            qoderRunnerCommand = qoderObject["runner_command"] as? String ?? qoderRunnerCommand
            qoderRunnerPath = qoderObject["runner_path"] as? String ?? qoderRunnerPath
            qoderSource = qoderObject["source"] as? String ?? qoderSource
            qoderRegistryPath = qoderObject["registry_path"] as? String ?? qoderRegistryPath
            if let config = qoderObject["config"] as? String, !config.isEmpty {
                qoderConfigPath = config
            } else if let configPath = qoderObject["config_path"] as? String, !configPath.isEmpty {
                qoderConfigPath = configPath
            }
            qoderResolvedConfigPath = qoderObject["config_path"] as? String ?? qoderResolvedConfigPath
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
        qoderSource = object["source"] as? String ?? ""
        if let runner = object["runner_path"] as? String, !runner.isEmpty {
            qoderRunnerPath = runner
            qoderRunnerCommand = runner
        }
        if let config = object["config_path"] as? String, !config.isEmpty {
            qoderResolvedConfigPath = config
            qoderConfigPath = config
        }
        qoderRegistryPath = object["registry_path"] as? String ?? qoderRegistryPath
        qoderProfile = object["profile"] as? String ?? qoderProfile
    }

    private func shortName(_ path: String) -> String {
        guard !path.isEmpty else { return "未设置" }
        return URL(fileURLWithPath: path).lastPathComponent
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

    private func defaultRunMode(for task: TaskItem) -> RunMode {
        if task.mode == "full_cloud" || task.type == "cloud_experiment" {
            return .fullCloud
        }
        if task.mode == "fake" {
            return .fake
        }
        return .localControl
    }

    private func taskYAMLValue(_ key: String, in taskYAML: String) -> String? {
        for line in taskYAML.split(separator: "\n", omittingEmptySubsequences: false) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard trimmed.hasPrefix("\(key):") else { continue }
            let raw = trimmed
                .dropFirst("\(key):".count)
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
            return raw.isEmpty ? nil : String(raw)
        }
        return nil
    }

    private func updateObjective(in taskYAML: String, with objective: String) -> String {
        var lines = taskYAML.components(separatedBy: "\n")
        for index in lines.indices {
            let trimmed = lines[index].trimmingCharacters(in: .whitespaces)
            guard trimmed.hasPrefix("objective:") else { continue }
            let indent = leadingWhitespace(in: lines[index])
            let replacement = yamlBlockLines(key: "objective", indent: indent, value: objective)
            var end = index + 1
            while end < lines.count {
                let candidate = lines[end]
                if candidate.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    end += 1
                    continue
                }
                if leadingWhitespace(in: candidate).count <= indent.count {
                    break
                }
                end += 1
            }
            lines.replaceSubrange(index..<end, with: replacement)
            return lines.joined(separator: "\n")
        }

        for index in lines.indices {
            let trimmed = lines[index].trimmingCharacters(in: .whitespaces)
            guard trimmed == "plan:" else { continue }
            let indent = leadingWhitespace(in: lines[index]) + "  "
            lines.insert(contentsOf: yamlBlockLines(key: "objective", indent: indent, value: objective), at: index + 1)
            return lines.joined(separator: "\n")
        }

        var output = taskYAML
        if !output.hasSuffix("\n") {
            output += "\n"
        }
        output += "plan:\n"
        output += yamlBlockLines(key: "objective", indent: "  ", value: objective).joined(separator: "\n")
        output += "\n"
        return output
    }

    private func yamlBlockLines(key: String, indent: String, value: String) -> [String] {
        let lines = value.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
        return ["\(indent)\(key): |"] + (lines.isEmpty ? ["\(indent)  "] : lines.map { "\(indent)  \($0)" })
    }

    private func leadingWhitespace(in value: String) -> String {
        String(value.prefix { $0 == " " || $0 == "\t" })
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
                self.statusText = completed.terminationStatus == 0 ? "完成" : "失败"
                self.statusColor = completed.terminationStatus == 0 ? .green : .red
                self.appendLog("exit=\(completed.terminationStatus)")
                completion?(completed.terminationStatus)
            }
        }

        do {
            statusText = "运行中"
            statusColor = .yellow
            if clearLog {
                logText = ""
            }
            try process.run()
            self.process = process
            appendLog(([cliCommand] + arguments).joined(separator: " "))
        } catch {
            self.process = nil
            statusText = "失败"
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
