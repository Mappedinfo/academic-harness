import AppKit
import SwiftUI

@main
struct AcademicHarnessMacApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 1040, minHeight: 680)
        }
    }
}

struct ContentView: View {
    @StateObject private var model = WorkbenchModel()

    var body: some View {
        VStack(spacing: 12) {
            HStack(spacing: 10) {
                Circle()
                    .fill(model.statusColor)
                    .frame(width: 12, height: 12)
                Text(model.statusText)
                    .font(.headline)
                TextField("Project path", text: $model.projectPath)
                    .textFieldStyle(.roundedBorder)
                Button("Choose") { model.chooseProject() }
                Button("Reload") { model.reload() }
            }

            HStack(spacing: 8) {
                Text("CLI")
                    .foregroundStyle(.secondary)
                TextField("academic-harness", text: $model.cliCommand)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 220)
                Picker("Adapter", selection: $model.adapter) {
                    Text("qoder").tag("qoder")
                    Text("fake").tag("fake")
                }
                .pickerStyle(.segmented)
                .frame(width: 180)
                Spacer()
                Button("Run") { model.runSelectedTask() }
                    .disabled(!model.canRun)
                Button("Cancel") { model.cancel() }
                    .disabled(!model.isRunning)
                Button("Validate") { model.validateSelectedRun() }
                    .disabled(model.selectedRun == nil || model.isRunning)
            }

            HSplitView {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Tasks")
                        .font(.headline)
                    List(selection: $model.selectedTaskID) {
                        ForEach(model.tasks) { task in
                            Text(task.name)
                                .tag(task.id)
                        }
                    }
                    .frame(minWidth: 240)
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("Runs")
                        .font(.headline)
                    Table(model.runs, selection: $model.selectedRunID) {
                        TableColumn("Run") { run in
                            Text(run.runID)
                                .font(.system(.caption, design: .monospaced))
                        }
                        TableColumn("Status") { run in
                            Text(run.status)
                        }
                        TableColumn("Task") { run in
                            Text(run.taskID)
                        }
                    }
                }

                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("Files")
                            .font(.headline)
                        Spacer()
                        Button("Open Report") { model.openReport() }
                            .disabled(model.selectedRun?.reportPath == nil)
                        Button("Open Summary") { model.openSummary() }
                            .disabled(model.selectedRun?.summaryPath == nil)
                        Button("Reveal") { model.revealRun() }
                            .disabled(model.selectedRun == nil)
                    }

                    List(model.files, id: \.path) { file in
                        Button(file.lastPathComponent) {
                            NSWorkspace.shared.open(file)
                        }
                        .buttonStyle(.plain)
                    }

                    TextEditor(text: $model.logText)
                        .font(.system(.caption, design: .monospaced))
                        .frame(minHeight: 160)
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(Color.secondary.opacity(0.25))
                        )
                }
                .frame(minWidth: 360)
            }
        }
        .padding(16)
        .onAppear { model.reload() }
        .onChange(of: model.selectedRunID) { _ in model.refreshFiles() }
    }
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
    @Published var cliCommand = "academic-harness"
    @Published var adapter = "qoder"
    @Published var tasks: [TaskItem] = []
    @Published var runs: [RunItem] = []
    @Published var files: [URL] = []
    @Published var selectedTaskID: String?
    @Published var selectedRunID: String?
    @Published var statusText = "Idle"
    @Published var statusColor = Color.gray
    @Published var logText = ""

    private var process: Process?

    var isRunning: Bool {
        process != nil
    }

    var canRun: Bool {
        !isRunning && selectedTask != nil && !projectPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var selectedTask: TaskItem? {
        tasks.first { $0.id == selectedTaskID }
    }

    var selectedRun: RunItem? {
        runs.first { $0.id == selectedRunID }
    }

    init() {
        let current = FileManager.default.currentDirectoryPath
        projectPath = current
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
    }

    func runSelectedTask() {
        guard let task = selectedTask else { return }
        runCLI(arguments: [
            "task", "run", task.path.path,
            "--project", projectURL.path,
            "--adapter", adapter
        ])
    }

    func validateSelectedRun() {
        guard let run = selectedRun else { return }
        runCLI(arguments: ["validate", run.runID, "--project", projectURL.path])
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
        if selectedTaskID == nil {
            selectedTaskID = tasks.first?.id
        }
    }

    private func refreshRuns() {
        let runsURL = projectURL
            .appendingPathComponent(".workbench", isDirectory: true)
            .appendingPathComponent("runs", isDirectory: true)
        let runDirs = (try? FileManager.default.contentsOfDirectory(at: runsURL, includingPropertiesForKeys: nil)) ?? []
        runs = runDirs.compactMap(loadRun).sorted { $0.runID > $1.runID }
        if selectedRunID == nil {
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

    private func runCLI(arguments: [String]) {
        guard process == nil else { return }

        let process = Process()
        let output = Pipe()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = [cliCommand] + arguments
        process.standardOutput = output
        process.standardError = output
        process.currentDirectoryURL = projectURL

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
                self.reload()
            }
        }

        do {
            statusText = "Running"
            statusColor = .yellow
            logText = ""
            try process.run()
            self.process = process
            appendLog(([cliCommand] + arguments).joined(separator: " "))
        } catch {
            self.process = nil
            statusText = "Failed"
            statusColor = .red
            appendLog(error.localizedDescription)
        }
    }

    private func appendLog(_ message: String) {
        guard !message.isEmpty else { return }
        if !logText.isEmpty {
            logText += "\n"
        }
        logText += message
        if logText.count > 12000 {
            logText = String(logText.suffix(12000))
        }
    }
}

