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
        .onChange(of: model.selectedRunID) { _ in model.refreshRunSelection() }
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
            HStack {
                Text("运行历史")
                    .font(.headline)
                Spacer()
                TextField("搜索", text: $model.runSearchText)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 120)
            }
            Picker("筛选", selection: $model.runFilter) {
                ForEach(RunStatusFilter.allCases) { filter in
                    Text(filter.title).tag(filter)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()

            Table(model.filteredRuns, selection: $model.selectedRunID) {
                TableColumn("运行") { run in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(run.runID)
                            .font(.system(.caption, design: .monospaced))
                            .lineLimit(1)
                        Text(run.startedAt.isEmpty ? "无开始时间" : run.startedAt)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                TableColumn("状态") { run in
                    statusBadge(run.status)
                }
                TableColumn("任务") { run in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(run.taskID)
                            .lineLimit(1)
                        Text("\(run.mode) · \(run.adapter)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                TableColumn("耗时") { run in
                    Text(run.durationText)
                        .font(.caption)
                }
                TableColumn("验证") { run in
                    Text(run.validatorStatus)
                        .font(.caption)
                        .foregroundStyle(run.validatorStatus == "失败" ? .red : .secondary)
                }
                TableColumn("产物") { run in
                    Text("\(run.artifactCount)")
                        .font(.caption)
                }
            }
            if let summary = model.selectedRunSummary {
                Text(summary)
                    .font(.caption)
                    .foregroundStyle(model.selectedRun?.status == "failed" ? .red : .secondary)
                    .lineLimit(3)
                    .padding(.top, 2)
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
            Picker("", selection: $model.selectedInspectorTab) {
                Text("文件").tag("Files")
                Text("高级任务").tag("Task")
                Text("设置").tag("Settings")
                Text("检查器").tag("Log")
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
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text("执行方案")
                        .foregroundStyle(.secondary)
                    Picker("执行方案", selection: $model.executionPreset) {
                        ForEach(ExecutionPreset.primaryCases) { preset in
                            Text(preset.title).tag(preset)
                        }
                        ForEach(ExecutionPreset.advancedCases) { preset in
                            Text(preset.title).tag(preset)
                        }
                    }
                    .labelsHidden()
                    .pickerStyle(.menu)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                Text(model.executionPresetDetail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                if model.executionPreset.usesCloudAgents {
                    VStack(alignment: .leading, spacing: 8) {
                        Toggle("深度搜索多 Agent", isOn: $model.managedAgentsEnabled)
                        HStack {
                            Text("Agent 数量")
                                .foregroundStyle(.secondary)
                            Picker("Agent 数量", selection: $model.managedAgentCount) {
                                Text("3").tag(3)
                                Text("4").tag(4)
                                Text("5").tag(5)
                            }
                            .pickerStyle(.segmented)
                            .frame(width: 150)
                            Spacer()
                        }
                        Picker("委派方式", selection: $model.managedDelegationStrategy) {
                            Text("Agent 同步").tag("agent_sync")
                            Text("Child 线程").tag("child_threads")
                        }
                        .pickerStyle(.segmented)
                        Toggle("必须成功创建多 Agent", isOn: $model.requireManagedAgents)
                        Text(model.cloudExecutionSummary)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .disabled(model.isRunning)
                }

                if model.executionPreset == .experimentLAN {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text("LAN 目标")
                            .foregroundStyle(.secondary)
                        Text(model.lanTargetSummary)
                            .font(.caption)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer()
                    }
                }

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

    private var filesView: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("文件")
                    .font(.headline)
                Spacer()
                Button("Manifest") { model.openManifest() }
                    .disabled(model.selectedRun == nil)
                Button("Trace") { model.openTrace() }
                    .disabled(!model.selectedRunHasTrace)
                Button("Qoder Metadata") { model.openQoderMetadata() }
                    .disabled(!model.selectedRunHasQoderMetadata)
                Button("打开报告") { model.openReport() }
                    .disabled(model.selectedRun?.reportPath == nil)
                Button("打开总结") { model.openSummary() }
                    .disabled(model.selectedRun?.summaryPath == nil)
                Button("显示文件夹") { model.revealRun() }
                    .disabled(model.selectedRun == nil)
            }
            List {
                ForEach(model.artifactGroups) { group in
                    Section(group.title) {
                        ForEach(group.items) { item in
                            artifactRow(item)
                        }
                    }
                }
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
            localAISettingsCard
            registrySettingsCard

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

    private var registrySettingsCard: some View {
        GroupBox("变量 / 图片 / 表格 Registry") {
            VStack(alignment: .leading, spacing: 8) {
                Text("项目级 registry 用普通 YAML 保存；LAN 实验会在 run 目录下生成对应 registry。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                HStack {
                    Button("变量") { model.openProjectRelativeFile("variables/registry.yaml") }
                    Button("图片") { model.openProjectRelativeFile("figures/registry.yaml") }
                    Button("表格") { model.openProjectRelativeFile("tables/registry.yaml") }
                    Spacer()
                }
            }
            .padding(.vertical, 4)
        }
    }

    private var localAISettingsCard: some View {
        GroupBox("本地 AI Backend") {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .center, spacing: 8) {
                    Circle()
                        .fill(model.localAIOK ? Color.green : Color.red)
                        .frame(width: 10, height: 10)
                    Text(model.localAIStatusTitle)
                        .font(.headline)
                    Spacer()
                }
                Toggle("启用", isOn: $model.localAIEnabled)
                labeledField("Provider", text: $model.localAIProvider)
                labeledField("Base URL", text: $model.localAIBaseURL)
                labeledField("Model", text: $model.localAIModel)
                labeledField("API Key Env", text: $model.localAIAPIKeyEnv)
                labeledField("Env File", text: $model.localAIEnvFile)
                labeledField("Timeout", text: $model.localAITimeout)
                labeledField("Transport", text: $model.localAITransport)
                HStack {
                    Button("保存本地 AI") { model.saveLocalAIConfig() }
                        .disabled(!model.hasProject || model.isRunning)
                    Button("检查连接") { model.checkLocalAI() }
                        .disabled(!model.hasProject || model.isRunning)
                    Spacer()
                }
                Text(model.localAIMessage)
                    .font(.caption)
                    .foregroundStyle(model.localAIOK ? .green : .orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.vertical, 4)
        }
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
        VStack(alignment: .leading, spacing: 8) {
            Picker("检查视图", selection: $model.selectedLogTab) {
                ForEach(RunLogTab.allCases) { tab in
                    Text(tab.title).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()

            switch model.selectedLogTab {
            case .overview:
                runOverviewView
            case .timeline:
                runTimelineView
            case .errors:
                runErrorsView
            case .validation:
                runValidationView
            case .qoder:
                runQoderView
            case .localAI:
                runLocalAIView
            case .raw:
                runRawLogView
            }
        }
    }

    private var runOverviewView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if let detail = model.selectedRunDetail {
                    keyValueRows(detail.overviewRows)
                    if !detail.parseWarnings.isEmpty {
                        GroupBox("解析提示") {
                            VStack(alignment: .leading, spacing: 6) {
                                ForEach(detail.parseWarnings) { warning in
                                    Text("\(warning.source): \(warning.message)")
                                        .font(.caption)
                                        .foregroundStyle(.orange)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                } else {
                    emptyInspectorText("选择一个 run 后查看概览。")
                }
            }
        }
    }

    private var runTimelineView: some View {
        List(model.selectedRunDetail?.timeline ?? []) { event in
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(event.timestamp)
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundStyle(.secondary)
                    Text(event.type)
                        .font(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color(NSColor.controlBackgroundColor))
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                    Spacer()
                }
                Text(event.title)
                    .font(.headline)
                if !event.detail.isEmpty {
                    Text(event.detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(4)
                }
            }
            .padding(.vertical, 3)
        }
        .overlay {
            if model.selectedRunDetail?.timeline.isEmpty ?? true {
                emptyInspectorText("没有 trace.jsonl；旧 run 会尝试从 manifest.state_history 降级生成。")
            }
        }
    }

    private var runErrorsView: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("错误诊断")
                    .font(.headline)
                Spacer()
                Button("复制错误") { model.copySelectedRunErrors() }
                    .disabled(model.selectedRunDetail?.errors.isEmpty ?? true)
            }
            List(model.selectedRunDetail?.errors ?? []) { item in
                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        Text(item.source)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        if !item.filePath.isEmpty {
                            Text(URL(fileURLWithPath: item.filePath).lastPathComponent)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                    Text(item.message)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.red)
                        .textSelection(.enabled)
                }
                .padding(.vertical, 3)
            }
            .overlay {
                if model.selectedRunDetail?.errors.isEmpty ?? true {
                    emptyInspectorText("当前 run 没有发现 manifest、Qoder metadata 或 validator 错误。")
                }
            }
        }
    }

    private var runValidationView: some View {
        List(model.selectedRunDetail?.validators ?? []) { item in
            VStack(alignment: .leading, spacing: 5) {
                HStack {
                    statusBadge(item.status)
                    Text(item.validator)
                        .font(.headline)
                    Spacer()
                    if !item.reportPath.isEmpty {
                        Button("打开") {
                            NSWorkspace.shared.open(URL(fileURLWithPath: item.reportPath))
                        }
                    }
                }
                if !item.message.isEmpty {
                    Text(item.message)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(5)
                }
            }
            .padding(.vertical, 3)
        }
        .overlay {
            if model.selectedRunDetail?.validators.isEmpty ?? true {
                emptyInspectorText("没有 validator 结果。失败如果发生在 executor 阶段，会显示在“错误”页。")
            }
        }
    }

    private var runQoderView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if let detail = model.selectedRunDetail {
                    keyValueRows(detail.qoderRows)
                    GroupBox("Qoder 文件") {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(detail.rawFiles.filter { $0.relativePath.hasPrefix("qoder/") }) { item in
                                artifactRow(item)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                } else {
                    emptyInspectorText("选择一个 Qoder run 后查看 session、agent roster 和 delegation trace。")
                }
            }
        }
    }

    private var runLocalAIView: some View {
        List(model.selectedRunDetail?.localAIArtifacts ?? []) { item in
            artifactRow(item)
        }
        .overlay {
            if model.selectedRunDetail?.localAIArtifacts.isEmpty ?? true {
                emptyInspectorText("当前 run 没有 local_ai 输出。“本地 + 多云端”执行会在这里显示 preflight/postflight 文件。")
            }
        }
    }

    private var runRawLogView: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("原始日志")
                    .font(.headline)
                Spacer()
                Button("CLI 输出") { model.selectedRawLogPath = nil }
                Button("打开所选文件") { model.openSelectedRawLogFile() }
                    .disabled(model.selectedRawLogPath == nil)
            }
            HSplitView {
                List(selection: $model.selectedRawLogPath) {
                    ForEach(model.rawLogFiles) { item in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.relativePath)
                                .font(.caption)
                            Text("\(item.kind) · \(item.sizeText)")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        .tag(item.path.path)
                    }
                }
                .frame(minWidth: 150, maxWidth: 220)

                TextEditor(text: .constant(model.rawLogPreviewText))
                    .font(.system(.caption, design: .monospaced))
                    .overlay(editorBorder)
            }
        }
    }

    private func keyValueRows(_ rows: [KeyValueRow]) -> some View {
        GroupBox("运行摘要") {
            VStack(alignment: .leading, spacing: 7) {
                ForEach(rows) { row in
                    HStack(alignment: .top) {
                        Text(row.key)
                            .frame(width: 92, alignment: .trailing)
                            .foregroundStyle(.secondary)
                        Text(row.value.isEmpty ? "未记录" : row.value)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .font(.caption)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func artifactRow(_ item: RunArtifactItem) -> some View {
        HStack(spacing: 8) {
            Button(item.relativePath) {
                NSWorkspace.shared.open(item.path)
            }
            .buttonStyle(.plain)
            .font(.system(.caption, design: .monospaced))
            .lineLimit(1)
            Spacer()
            Text(item.kind)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(item.sizeText)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .frame(width: 58, alignment: .trailing)
        }
    }

    private func statusBadge(_ status: String) -> some View {
        HStack(spacing: 5) {
            Circle()
                .fill(statusColor(for: status))
                .frame(width: 8, height: 8)
            Text(statusDisplay(status))
                .font(.caption)
                .lineLimit(1)
        }
    }

    private func emptyInspectorText(_ text: String) -> some View {
        Text(text)
            .font(.caption)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding()
    }

    private func statusColor(for status: String) -> Color {
        switch status {
        case "passed":
            return .green
        case "failed":
            return .red
        case "blocked", "awaiting_approval":
            return .orange
        case "cancelled":
            return .gray
        case "running", "created", "executing", "streaming":
            return .yellow
        default:
            return .secondary
        }
    }

    private func statusDisplay(_ status: String) -> String {
        switch status {
        case "passed":
            return "成功"
        case "failed":
            return "失败"
        case "blocked":
            return "阻塞"
        case "awaiting_approval":
            return "待确认"
        case "cancelled":
            return "取消"
        case "running":
            return "运行中"
        default:
            return status
        }
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
                .truncationMode(.tail)
                .frame(maxWidth: 170, alignment: .leading)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color(NSColor.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .help("\(item.label): \(item.message)")
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
    let mode: String
    let adapter: String
    let startedAt: String
    let durationText: String
    let validatorStatus: String
    let artifactCount: Int
    let errorSummary: String
    let runDir: URL
    let reportPath: URL?
    let summaryPath: URL?
    let manifestPath: URL
    let diagnostics: String
}

enum RunStatusFilter: String, CaseIterable, Identifiable {
    case all
    case passed
    case failed
    case blocked
    case cancelled
    case running

    var id: String { rawValue }

    var title: String {
        switch self {
        case .all:
            return "全部"
        case .passed:
            return "成功"
        case .failed:
            return "失败"
        case .blocked:
            return "阻塞"
        case .cancelled:
            return "取消"
        case .running:
            return "运行中"
        }
    }

    func matches(_ run: RunItem) -> Bool {
        switch self {
        case .all:
            return true
        case .passed:
            return run.status == "passed"
        case .failed:
            return run.status == "failed"
        case .blocked:
            return run.status == "blocked" || run.status == "awaiting_approval"
        case .cancelled:
            return run.status == "cancelled"
        case .running:
            return ["running", "created", "executing", "streaming"].contains(run.status)
        }
    }
}

enum RunLogTab: String, CaseIterable, Identifiable {
    case overview
    case timeline
    case errors
    case validation
    case qoder
    case localAI
    case raw

    var id: String { rawValue }

    var title: String {
        switch self {
        case .overview:
            return "概览"
        case .timeline:
            return "时间线"
        case .errors:
            return "错误"
        case .validation:
            return "验证"
        case .qoder:
            return "Qoder"
        case .localAI:
            return "本地 AI"
        case .raw:
            return "原始日志"
        }
    }
}

struct KeyValueRow: Identifiable, Hashable {
    let id: String
    let key: String
    let value: String
}

struct RunTimelineEvent: Identifiable, Hashable {
    let id: String
    let timestamp: String
    let type: String
    let title: String
    let detail: String
}

struct RunErrorItem: Identifiable, Hashable {
    let id: String
    let source: String
    let message: String
    let filePath: String
}

struct RunValidationItem: Identifiable, Hashable {
    let id: String
    let validator: String
    let status: String
    let message: String
    let reportPath: String
}

struct RunArtifactItem: Identifiable, Hashable {
    let id: String
    let path: URL
    let relativePath: String
    let kind: String
    let sizeText: String
    let modifiedText: String

    var groupTitle: String {
        switch kind {
        case "report":
            return "报告"
        case "summary":
            return "总结"
        case "qoder_artifact":
            return "Qoder Artifact"
        case "qoder_raw":
            return "Qoder Raw"
        case "local_ai":
            return "本地 AI"
        case "lan_artifact":
            return "LAN Artifact"
        case "lan_raw":
            return "LAN Raw"
        case "figure_registry":
            return "图片 Registry"
        case "table_registry":
            return "表格 Registry"
        case "validation":
            return "验证"
        case "trace":
            return "Trace"
        case "manifest":
            return "Manifest"
        default:
            return "其他"
        }
    }
}

struct ArtifactGroup: Identifiable, Hashable {
    let id: String
    let title: String
    let items: [RunArtifactItem]
}

struct RunDetail {
    let overviewRows: [KeyValueRow]
    let timeline: [RunTimelineEvent]
    let errors: [RunErrorItem]
    let validators: [RunValidationItem]
    let artifacts: [RunArtifactItem]
    let rawFiles: [RunArtifactItem]
    let qoderRows: [KeyValueRow]
    let localAIArtifacts: [RunArtifactItem]
    let parseWarnings: [RunErrorItem]
}

enum ExecutionPreset: String, CaseIterable, Identifiable {
    case decisionCloud
    case decisionHybrid
    case decisionTask
    case researchCloud
    case researchLocal
    case experimentLAN
    case debugFake
    case compatibilityQoderCLI

    var id: String { rawValue }

    static let primaryCases: [ExecutionPreset] = [
        .decisionCloud,
        .decisionHybrid,
        .decisionTask,
        .researchCloud,
        .researchLocal,
        .experimentLAN
    ]

    static let advancedCases: [ExecutionPreset] = [
        .debugFake,
        .compatibilityQoderCLI
    ]

    var title: String {
        switch self {
        case .decisionCloud:
            return "做决策 · 纯云端"
        case .decisionHybrid:
            return "做决策 · 本地 + 多云端"
        case .decisionTask:
            return "做决策 · 单纯任务"
        case .researchCloud:
            return "做调研 · 云端"
        case .researchLocal:
            return "做调研 · 本地"
        case .experimentLAN:
            return "做实验 · 局域网"
        case .debugFake:
            return "高级调试 · Fake 测试"
        case .compatibilityQoderCLI:
            return "高级兼容 · Qoder CLI"
        }
    }

    var adapter: String {
        switch self {
        case .decisionCloud, .researchCloud:
            return "qoder_cloud"
        case .decisionHybrid:
            return "hybrid"
        case .experimentLAN:
            return "lan"
        case .decisionTask, .researchLocal:
            return "local_control"
        case .debugFake:
            return "fake"
        case .compatibilityQoderCLI:
            return "qoder"
        }
    }

    var requiresQoder: Bool {
        self == .decisionCloud
            || self == .decisionHybrid
            || self == .researchCloud
            || self == .compatibilityQoderCLI
    }

    var requiresLocalAI: Bool {
        self == .decisionHybrid
    }

    var requiresLAN: Bool {
        self == .experimentLAN
    }

    var usesCloudAgents: Bool {
        self == .decisionCloud || self == .decisionHybrid || self == .researchCloud
    }

    var detail: String {
        switch self {
        case .decisionCloud:
            return "本地只提交目标和回收 artifacts，决策拆解、调研和成稿由 Qoder Cloud Agent 完成。"
        case .decisionHybrid:
            return "本地 AI 先拆解和审查，Qoder Cloud 执行搜索写作，本地 AI 再审校整合。"
        case .decisionTask:
            return "本地生成控制计划、检查材料或任务拆解，不启动云端检索与远程实验。"
        case .researchCloud:
            return "把调研任务交给 Qoder Cloud Agent，适合需要联网搜索、证据整理和报告写作的任务。"
        case .researchLocal:
            return "本地生成调研计划或整理已有材料，不启动 Qoder Cloud Agent。"
        case .experimentLAN:
            return "只把任务规格和变量提交到局域网 worker，数据留在远程，本地回收报告和轻量 registry。"
        case .debugFake:
            return "离线生成 fixture 输出，用于检查项目、UI 和 validator 是否能跑通。"
        case .compatibilityQoderCLI:
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
    @Published var selectedRunDetail: RunDetail?
    @Published var runFilter: RunStatusFilter = .all
    @Published var runSearchText = ""
    @Published var selectedLogTab: RunLogTab = .overview
    @Published var rawLogFiles: [RunArtifactItem] = []
    @Published var selectedRawLogPath: String?
    @Published var selectedTaskID: String?
    @Published var selectedRunID: String?
    @Published var selectedInspectorTab = "Files"
    @Published var executionPreset: ExecutionPreset = .decisionTask
    @Published var statusText = "空闲"
    @Published var statusColor = Color.gray
    @Published var statusItems: [StatusItem] = []
    @Published var taskText = ""
    @Published var promptText = ""
    @Published var promptPathDisplay = ""
    @Published var promptUsesTaskObjective = false
    @Published var logText = ""
    @Published var runDiagnosticsText = ""
    @Published var qoderOK = false
    @Published var qoderMessage = "未加载项目"
    @Published var qoderRunnerCommand = "qoder-run"
    @Published var qoderConfigPath = ""
    @Published var qoderProfile = "default"
    @Published var qoderRunnerPath = ""
    @Published var qoderResolvedConfigPath = ""
    @Published var qoderSource = ""
    @Published var qoderRegistryPath = ""
    @Published var qoderManagedMessage = "深度搜索多 Agent 待检查"
    @Published var qoderManagedReady = false
    @Published var qoderManagedSchemaOK = true
    @Published var qoderManagedAgentCount = 4
    @Published var qoderManagedConfiguredCount = 4
    @Published var qoderManagedModelOK = false
    @Published var qoderManagedRequestedModel = ""
    @Published var qoderManagedResolvedModel = ""
    @Published var qoderManagedModelSource = ""
    @Published var qoderManagedDelegationStrategy = "agent_sync"
    @Published var qoderManagedIncludeSelf = false
    @Published var qoderModelsMessage = "模型未检查"
    @Published var qoderNetworkMode = "auto"
    @Published var qoderNetworkModeEffective = "direct"
    @Published var managedAgentsEnabled = true
    @Published var managedAgentCount = 4
    @Published var managedDelegationStrategy = "agent_sync"
    @Published var requireManagedAgents = false
    @Published var localAIOK = false
    @Published var localAIEnabled = true
    @Published var localAIProvider = "openai_compatible"
    @Published var localAIBaseURL = "https://api.longcat.chat/openai"
    @Published var localAIModel = "LongCat-2.0"
    @Published var localAIAPIKeyEnv = "LONG_CAT_API_KEY"
    @Published var localAIEnvFile = ""
    @Published var localAITimeout = "120"
    @Published var localAITransport = "auto"
    @Published var localAIMessage = "本地 AI 未配置"
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
        canRunBase
            && (!executionPreset.requiresQoder || qoderOK)
            && (!executionPreset.requiresLocalAI || localAIOK)
            && (!executionPreset.requiresLAN || (lanEnabled && lanOK))
            && !strictManagedAgentModelBlock
    }

    var canSavePrompt: Bool {
        selectedTask != nil && (promptURL != nil || promptUsesTaskObjective)
    }

    var executionPresetDetail: String {
        executionPreset.detail
    }

    var managedAgentsDetail: String {
        if !managedAgentsEnabled {
            return "本次云端执行将使用单个 Qoder Agent。"
        }
        let workerCount = max(2, managedAgentCount - 1)
        let state = qoderManagedReady ? "本地 roster 已准备" : "首次运行会自动创建或更新"
        let model = qoderManagedResolvedModel.isEmpty ? "未解析" : qoderManagedResolvedModel
        let strategy = managedDelegationStrategy == "child_threads" ? "Child 线程" : "Agent 同步"
        return "1 个统领 Agent + \(workerCount) 个分工 Agent；委派方式: \(strategy)；\(state)。模型: \(model)。\(qoderManagedMessage)"
    }

    var cloudExecutionSummary: String {
        if !managedAgentsEnabled {
            return "云端执行：单个 Qoder Agent。详细模型与 schema 状态见“设置 > Qoder”。"
        }
        let workerCount = max(2, managedAgentCount - 1)
        let strategy = managedDelegationStrategy == "child_threads" ? "Child 线程" : "Agent 同步"
        let strict = requireManagedAgents ? "必须创建成功" : "失败时允许按后端策略降级"
        return "云端执行：1 个统领 Agent + \(workerCount) 个分工 Agent；\(strategy)；\(strict)。详细状态见“设置 > Qoder”。"
    }

    var qoderManagedModelText: String {
        if qoderManagedModelOK {
            let resolved = qoderManagedResolvedModel.isEmpty ? "自动选择" : qoderManagedResolvedModel
            let source = qoderManagedModelSource.isEmpty ? "" : " (\(qoderManagedModelSource))"
            return "Qoder 模型可用: \(resolved)\(source)"
        }
        return "Qoder 模型不可用: \(qoderModelsMessage)"
    }

    var qoderManagedSchemaText: String {
        if qoderManagedSchemaOK {
            let strategy = qoderManagedDelegationStrategy == "child_threads" ? "Child 线程" : "Agent 同步"
            return "Multiagent schema OK: \(qoderManagedAgentCount) agents, \(strategy)"
        }
        return "Multiagent schema 错误：下次运行会自动更新 roster"
    }

    var lanTargetSummary: String {
        guard lanEnabled else { return "LAN 未启用" }
        let target = lanSSHAlias.isEmpty ? (lanServer.isEmpty ? "未设置服务器" : lanServer) : lanSSHAlias
        let root = lanProjectRoot.isEmpty ? "未设置项目根目录" : lanProjectRoot
        return "\(target) · \(root)"
    }

    var localAIStatusTitle: String {
        localAIOK ? "本地 AI 已就绪" : "本地 AI 未就绪"
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
        if executionPreset.requiresQoder && !qoderOK {
            return "当前执行方案需要 Qoder 配置就绪"
        }
        if strictManagedAgentModelBlock {
            return "必须创建多 Agent，但当前 Qoder 模型不可用：\(qoderModelsMessage)"
        }
        if executionPreset.requiresLocalAI && !localAIOK {
            return "本地 + 多云端需要本地 AI Backend 就绪"
        }
        if executionPreset.requiresLAN && !(lanEnabled && lanOK) {
            return "做实验 · 局域网需要 LAN 配置就绪"
        }
        return "将以“\(executionPreset.title)”启动当前任务"
    }

    var selectedTask: TaskItem? {
        tasks.first { $0.id == selectedTaskID }
    }

    var selectedRun: RunItem? {
        runs.first { $0.id == selectedRunID }
    }

    var filteredRuns: [RunItem] {
        let query = runSearchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return runs.filter { run in
            guard runFilter.matches(run) else { return false }
            guard !query.isEmpty else { return true }
            return [
                run.runID,
                run.status,
                run.taskID,
                run.mode,
                run.adapter,
                run.errorSummary
            ]
            .joined(separator: " ")
            .lowercased()
            .contains(query)
        }
    }

    var selectedRunSummary: String? {
        guard let run = selectedRun else { return nil }
        if !run.errorSummary.isEmpty {
            return "错误：\(run.errorSummary)"
        }
        return "\(run.status) · \(run.mode) · 验证 \(run.validatorStatus) · artifacts \(run.artifactCount)"
    }

    var artifactGroups: [ArtifactGroup] {
        let items = selectedRunDetail?.artifacts ?? []
        let order = ["报告", "总结", "LAN Artifact", "图片 Registry", "表格 Registry", "LAN Raw", "Qoder Artifact", "Qoder Raw", "本地 AI", "验证", "Trace", "Manifest", "其他"]
        let grouped = Dictionary(grouping: items) { $0.groupTitle }
        return order.compactMap { title in
            guard let values = grouped[title], !values.isEmpty else { return nil }
            return ArtifactGroup(id: title, title: title, items: values.sorted { $0.relativePath < $1.relativePath })
        }
    }

    var selectedRunHasTrace: Bool {
        guard let run = selectedRun else { return false }
        return FileManager.default.fileExists(atPath: run.runDir.appendingPathComponent("trace.jsonl").path)
    }

    var selectedRunHasQoderMetadata: Bool {
        guard let run = selectedRun else { return false }
        return FileManager.default.fileExists(atPath: run.runDir.appendingPathComponent("qoder/metadata.json").path)
    }

    var rawLogPreviewText: String {
        guard let selectedRawLogPath else {
            return combinedLogText.isEmpty ? "没有 CLI 输出。" : combinedLogText
        }
        let url = URL(fileURLWithPath: selectedRawLogPath)
        return previewText(from: url, maxLines: 220)
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
            let nextStep = selectedTask == nil ? "请先在左侧选择一个任务。" : "选择执行方案后点击“启动运行”。"
            let modelText = qoderManagedModelOK
                ? "多 Agent 模型可用: \(qoderManagedResolvedModel.isEmpty ? "自动选择" : qoderManagedResolvedModel)"
                : "多 Agent 模型未就绪: \(qoderModelsMessage)"
            let schemaText = qoderManagedSchemaOK ? "Multiagent schema OK" : "Multiagent schema 需更新"
            let networkText = qoderNetworkModeEffective == qoderNetworkMode
                ? "网络: \(qoderNetworkMode)"
                : "网络: \(qoderNetworkMode) -> \(qoderNetworkModeEffective)"
            return "已连接 \(runner)，使用 \(config)，Profile: \(qoderProfile)。\(networkText)。\(modelText)。\(schemaText)。\(qoderManagedMessage)。\(nextStep)"
        }
        return "点击“一键配置 Qoder”会安装/注册 qoder-run，并让项目回到系统自动发现模式。"
    }

    var qoderTechnicalSummary: String {
        [
            "来源: \(qoderSource.isEmpty ? "未发现" : qoderSource)",
            "Runner: \(qoderRunnerPath.isEmpty ? qoderRunnerCommand : qoderRunnerPath)",
            "Config: \(qoderResolvedConfigPath.isEmpty ? qoderConfigPath : qoderResolvedConfigPath)",
            "Registry: \(qoderRegistryPath.isEmpty ? "默认位置" : qoderRegistryPath)",
            "Network: requested=\(qoderNetworkMode), effective=\(qoderNetworkModeEffective)",
            "Models: \(qoderModelsMessage)",
            "Managed model: requested=\(qoderManagedRequestedModel.isEmpty ? "auto" : qoderManagedRequestedModel), resolved=\(qoderManagedResolvedModel.isEmpty ? "none" : qoderManagedResolvedModel), source=\(qoderManagedModelSource.isEmpty ? "unknown" : qoderManagedModelSource)",
            "Managed schema: ok=\(qoderManagedSchemaOK), agents=\(qoderManagedAgentCount), strategy=\(qoderManagedDelegationStrategy), include_self=\(qoderManagedIncludeSelf)",
            "Managed Agents: \(qoderManagedMessage)",
            "状态: \(qoderMessage)"
        ].joined(separator: "\n")
    }

    var combinedLogText: String {
        [logText, runDiagnosticsText]
            .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            .joined(separator: "\n\n")
    }

    private var strictManagedAgentModelBlock: Bool {
        executionPreset.usesCloudAgents
            && managedAgentsEnabled
            && requireManagedAgents
            && !qoderManagedModelOK
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
        runSelectedTask(adapter: executionPreset.adapter)
    }

    private func runSelectedTask(adapter: String) {
        guard let task = selectedTask else { return }
        var arguments = [
            "task", "run", task.path.path,
            "--project", projectURL.path,
            "--adapter", adapter
        ]
        if executionPreset.usesCloudAgents {
            arguments.append(contentsOf: ["--managed-agents", managedAgentsEnabled ? "on" : "off"])
            arguments.append(contentsOf: ["--managed-agent-count", String(managedAgentCount)])
            arguments.append(contentsOf: ["--delegation-strategy", managedDelegationStrategy])
            if requireManagedAgents {
                arguments.append("--require-managed-agents")
            }
        }
        runCLI(arguments: arguments) { [weak self] _ in
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

    func openManifest() {
        guard let run = selectedRun else { return }
        NSWorkspace.shared.open(run.manifestPath)
    }

    func openTrace() {
        guard let run = selectedRun else { return }
        let url = run.runDir.appendingPathComponent("trace.jsonl")
        if FileManager.default.fileExists(atPath: url.path) {
            NSWorkspace.shared.open(url)
        }
    }

    func openQoderMetadata() {
        guard let run = selectedRun else { return }
        let url = run.runDir.appendingPathComponent("qoder/metadata.json")
        if FileManager.default.fileExists(atPath: url.path) {
            NSWorkspace.shared.open(url)
        }
    }

    func openSelectedRawLogFile() {
        guard let selectedRawLogPath else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: selectedRawLogPath))
    }

    func copySelectedRunErrors() {
        let text = (selectedRunDetail?.errors ?? [])
            .map { "[\($0.source)] \($0.message)" }
            .joined(separator: "\n")
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
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

    func openProjectRelativeFile(_ relativePath: String) {
        let url = projectURL.appendingPathComponent(relativePath)
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

    func saveLocalAIConfig() {
        var args = [
            "project", "set-local-ai",
            "--project", projectURL.path,
            "--enabled", localAIEnabled ? "true" : "false"
        ]
        let provider = localAIProvider.trimmingCharacters(in: .whitespacesAndNewlines)
        let baseURL = localAIBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        let model = localAIModel.trimmingCharacters(in: .whitespacesAndNewlines)
        let apiKeyEnv = localAIAPIKeyEnv.trimmingCharacters(in: .whitespacesAndNewlines)
        let envFile = localAIEnvFile.trimmingCharacters(in: .whitespacesAndNewlines)
        let timeout = localAITimeout.trimmingCharacters(in: .whitespacesAndNewlines)
        let transport = localAITransport.trimmingCharacters(in: .whitespacesAndNewlines)
        if !provider.isEmpty {
            args.append(contentsOf: ["--provider", provider])
        }
        if !baseURL.isEmpty {
            args.append(contentsOf: ["--base-url", baseURL])
        }
        if !model.isEmpty {
            args.append(contentsOf: ["--model", model])
        }
        if !apiKeyEnv.isEmpty {
            args.append(contentsOf: ["--api-key-env", apiKeyEnv])
        }
        if !envFile.isEmpty {
            args.append(contentsOf: ["--env-file", envFile])
        }
        if !timeout.isEmpty {
            args.append(contentsOf: ["--timeout-seconds", timeout])
        }
        if !transport.isEmpty {
            args.append(contentsOf: ["--transport", transport])
        }
        runCLI(arguments: args) { [weak self] _ in
            self?.refreshProjectStatus(checkLAN: false)
        }
    }

    func checkLocalAI() {
        refreshProjectStatus(checkLAN: false, checkLocalAI: true)
    }

    func refreshRunSelection() {
        guard let run = selectedRun else {
            files = []
            runDiagnosticsText = ""
            selectedRunDetail = nil
            rawLogFiles = []
            selectedRawLogPath = nil
            return
        }
        runDiagnosticsText = run.diagnostics
        var found: [URL] = []
        if let enumerator = FileManager.default.enumerator(at: run.runDir, includingPropertiesForKeys: nil) {
            for case let url as URL in enumerator where !url.hasDirectoryPath {
                found.append(url)
            }
        }
        files = found.sorted { $0.path < $1.path }
        selectedRunDetail = loadRunDetail(for: run, discoveredFiles: files)
        rawLogFiles = selectedRunDetail?.rawFiles ?? []
        selectedRawLogPath = rawLogFiles.first?.path.path
        selectedLogTab = run.status == "failed" || run.status == "blocked" ? .errors : .overview
    }

    func refreshFiles() {
        refreshRunSelection()
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
        executionPreset = defaultExecutionPreset(for: task)
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
        let diagnostics = runDiagnostics(from: object, runDir: url)
        let adapter = stringValue(object["adapter"]) ?? stringValue(object["resolved_adapter"]) ?? stringValue(object["requested_adapter"]) ?? ""
        let mode = stringValue(object["mode"]) ?? ""
        let startedAt = stringValue(object["started_at"]) ?? ""
        let finishedAt = stringValue(object["finished_at"]) ?? ""
        let artifacts = object["artifacts"] as? [[String: Any]] ?? []
        let validators = object["validators"] as? [[String: Any]] ?? []
        let validatorStatus = validatorSummary(validators)
        let errorSummary = bestRunError(from: object, runDir: url)
        return RunItem(
            id: runID,
            runID: runID,
            status: status,
            taskID: taskID,
            mode: mode,
            adapter: adapter,
            startedAt: compactDateTime(startedAt),
            durationText: durationText(startedAt: startedAt, finishedAt: finishedAt),
            validatorStatus: validatorStatus,
            artifactCount: artifacts.count,
            errorSummary: errorSummary,
            runDir: url,
            reportPath: report,
            summaryPath: summary,
            manifestPath: manifest,
            diagnostics: diagnostics
        )
    }

    private func runDiagnostics(from manifest: [String: Any], runDir: URL) -> String {
        var lines: [String] = []
        if let runID = manifest["run_id"] as? String {
            lines.append("Selected run: \(runID)")
        }
        if let status = manifest["status"] as? String {
            lines.append("manifest.status: \(status)")
        }
        if let error = manifest["error"] as? String, !error.isEmpty {
            lines.append("manifest.error: \(error)")
        }
        if let stopReason = manifest["stop_reason"] as? String, !stopReason.isEmpty {
            lines.append("manifest.stop_reason: \(stopReason)")
        }
        let qoderMetadata = runDir.appendingPathComponent("qoder").appendingPathComponent("metadata.json")
        if
            let data = try? Data(contentsOf: qoderMetadata),
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        {
            if let qoderStatus = object["status"] as? String {
                lines.append("qoder.metadata.status: \(qoderStatus)")
            }
            if let qoderError = object["error"] as? String, !qoderError.isEmpty {
                lines.append("qoder.metadata.error: \(qoderError)")
            }
            if let qoderStop = object["stop_reason"] as? String, !qoderStop.isEmpty {
                lines.append("qoder.metadata.stop_reason: \(qoderStop)")
            }
            if
                let managed = object["managed_agents"] as? [String: Any],
                let managedError = managed["error"] as? String,
                !managedError.isEmpty
            {
                lines.append("qoder.managed_agents.error: \(managedError)")
            }
        }
        return lines.joined(separator: "\n")
    }

    private func loadRunDetail(for run: RunItem, discoveredFiles: [URL]) -> RunDetail {
        var parseWarnings: [RunErrorItem] = []
        let manifest = readJSONDictionary(run.manifestPath, warnings: &parseWarnings) ?? [:]
        let qoderMetadataURL = run.runDir.appendingPathComponent("qoder/metadata.json")
        let qoderMetadata = readJSONDictionary(qoderMetadataURL, warnings: &parseWarnings)
        let artifacts = collectArtifactItems(run: run, manifest: manifest, discoveredFiles: discoveredFiles, warnings: &parseWarnings)
        let validators = collectValidationItems(run: run, manifest: manifest, warnings: &parseWarnings)
        let timeline = collectTimelineEvents(run: run, manifest: manifest, warnings: &parseWarnings)
        let errors = collectRunErrors(run: run, manifest: manifest, qoderMetadata: qoderMetadata, validators: validators) + parseWarnings
        let rawFiles = artifacts.filter { isRawLogArtifact($0) }
        let localAIArtifacts = artifacts.filter { $0.relativePath.hasPrefix("local_ai/") }
        return RunDetail(
            overviewRows: overviewRows(run: run, manifest: manifest, qoderMetadata: qoderMetadata, validators: validators, artifacts: artifacts),
            timeline: timeline,
            errors: errors,
            validators: validators,
            artifacts: artifacts,
            rawFiles: rawFiles,
            qoderRows: qoderRows(run: run, manifest: manifest, qoderMetadata: qoderMetadata),
            localAIArtifacts: localAIArtifacts,
            parseWarnings: parseWarnings
        )
    }

    private func overviewRows(
        run: RunItem,
        manifest: [String: Any],
        qoderMetadata: [String: Any]?,
        validators: [RunValidationItem],
        artifacts: [RunArtifactItem]
    ) -> [KeyValueRow] {
        let policy = nestedDictionary(manifest, "policy")
        let preflight = policy.flatMap { nestedDictionary($0, "preflight") }
        let postArtifact = policy.flatMap { nestedDictionary($0, "post_artifact") }
        let qoder = nestedDictionary(manifest, "qoder") ?? nestedDictionary(manifest, "executor")
        let managed = qoder.flatMap { nestedDictionary($0, "managed_agents") } ?? qoderMetadata.flatMap { nestedDictionary($0, "managed_agents") }
        let sessionID = stringValue(qoder?["session_id"]) ?? stringValue(qoderMetadata?["session_id"])
        let managedSummary = managedAgentsSummary(managed)
        return [
            KeyValueRow(id: "run", key: "Run", value: run.runID),
            KeyValueRow(id: "status", key: "状态", value: stringValue(manifest["status"]) ?? run.status),
            KeyValueRow(id: "state", key: "State", value: stringValue(manifest["state"]) ?? ""),
            KeyValueRow(id: "task", key: "任务", value: run.taskID),
            KeyValueRow(id: "mode", key: "模式", value: run.mode),
            KeyValueRow(id: "adapter", key: "Adapter", value: run.adapter),
            KeyValueRow(id: "started", key: "开始", value: compactDateTime(stringValue(manifest["started_at"]) ?? "")),
            KeyValueRow(id: "finished", key: "结束", value: compactDateTime(stringValue(manifest["finished_at"]) ?? "")),
            KeyValueRow(id: "duration", key: "耗时", value: run.durationText),
            KeyValueRow(id: "preflight", key: "Preflight", value: policyDecisionSummary(preflight)),
            KeyValueRow(id: "post_artifact", key: "Artifact", value: policyDecisionSummary(postArtifact)),
            KeyValueRow(id: "validators", key: "验证", value: validators.isEmpty ? "未运行" : validatorSummary(validators.map { ["status": $0.status] })),
            KeyValueRow(id: "artifacts", key: "产物", value: "\(artifacts.count) files"),
            KeyValueRow(id: "session", key: "Session", value: sessionID ?? ""),
            KeyValueRow(id: "managed", key: "多 Agent", value: managedSummary),
            KeyValueRow(id: "report", key: "报告", value: run.reportPath?.path ?? ""),
            KeyValueRow(id: "summary", key: "总结", value: run.summaryPath?.path ?? "")
        ]
    }

    private func collectTimelineEvents(run: RunItem, manifest: [String: Any], warnings: inout [RunErrorItem]) -> [RunTimelineEvent] {
        let traceURL = run.runDir.appendingPathComponent("trace.jsonl")
        if FileManager.default.fileExists(atPath: traceURL.path) {
            return readJSONLines(traceURL, warnings: &warnings).enumerated().map { index, object in
                let type = stringValue(object["type"]) ?? "event"
                let ts = compactDateTime(stringValue(object["ts"]) ?? "")
                let data = object["data"] as? [String: Any] ?? [:]
                let title: String
                if type == "state.enter" {
                    let state = stringValue(data["state"]) ?? "state"
                    let reason = stringValue(data["reason"]) ?? ""
                    title = reason.isEmpty ? state : "\(state): \(reason)"
                } else if type.hasPrefix("policy.") {
                    title = "\(type): \(stringValue(data["decision"]) ?? "unknown")"
                } else {
                    title = type
                }
                return RunTimelineEvent(
                    id: "\(traceURL.path):\(index)",
                    timestamp: ts,
                    type: type,
                    title: title,
                    detail: compactJSON(data)
                )
            }
        }

        let history = manifest["state_history"] as? [[String: Any]] ?? []
        return history.enumerated().map { index, item in
            let state = stringValue(item["state"]) ?? "state"
            let reason = stringValue(item["reason"]) ?? ""
            return RunTimelineEvent(
                id: "state_history:\(index)",
                timestamp: compactDateTime(stringValue(item["entered_at"]) ?? ""),
                type: "state.history",
                title: reason.isEmpty ? state : "\(state): \(reason)",
                detail: compactJSON(item)
            )
        }
    }

    private func collectValidationItems(run: RunItem, manifest: [String: Any], warnings: inout [RunErrorItem]) -> [RunValidationItem] {
        var items: [RunValidationItem] = []
        let validators = manifest["validators"] as? [[String: Any]] ?? []
        for (index, validator) in validators.enumerated() {
            let reportPath = stringValue(validator["report_path"]) ?? ""
            items.append(RunValidationItem(
                id: reportPath.isEmpty ? "manifest-validator-\(index)" : reportPath,
                validator: stringValue(validator["validator"]) ?? stringValue(validator["name"]) ?? "validator",
                status: stringValue(validator["status"]) ?? "unknown",
                message: validationMessage(from: validator),
                reportPath: reportPath
            ))
        }

        let validationDir = run.runDir.appendingPathComponent("validation", isDirectory: true)
        let files = (try? FileManager.default.contentsOfDirectory(at: validationDir, includingPropertiesForKeys: nil)) ?? []
        let known = Set(items.map { $0.reportPath })
        for file in files where file.pathExtension.lowercased() == "json" && !known.contains(file.path) {
            if let object = readJSONDictionary(file, warnings: &warnings) {
                items.append(RunValidationItem(
                    id: file.path,
                    validator: stringValue(object["validator"]) ?? file.deletingPathExtension().lastPathComponent,
                    status: stringValue(object["status"]) ?? "unknown",
                    message: validationMessage(from: object),
                    reportPath: file.path
                ))
            }
        }
        return items.sorted { $0.validator < $1.validator }
    }

    private func collectArtifactItems(
        run: RunItem,
        manifest: [String: Any],
        discoveredFiles: [URL],
        warnings: inout [RunErrorItem]
    ) -> [RunArtifactItem] {
        var byPath: [String: RunArtifactItem] = [:]
        let artifactsJSON = run.runDir.appendingPathComponent("artifacts.json")
        if
            let artifactIndex = readJSONDictionary(artifactsJSON, warnings: &warnings),
            let records = artifactIndex["artifacts"] as? [[String: Any]]
        {
            for record in records {
                if let item = artifactItem(from: record, runDir: run.runDir) {
                    byPath[item.path.path] = item
                }
            }
        } else if let records = manifest["artifacts"] as? [[String: Any]] {
            for record in records {
                if let item = artifactItem(from: record, runDir: run.runDir) {
                    byPath[item.path.path] = item
                }
            }
        }

        for file in discoveredFiles {
            if byPath[file.path] == nil {
                let relativePath = relativePath(file, from: run.runDir)
                byPath[file.path] = RunArtifactItem(
                    id: file.path,
                    path: file,
                    relativePath: relativePath,
                    kind: inferredArtifactKind(relativePath),
                    sizeText: fileSizeText(file),
                    modifiedText: modifiedText(file)
                )
            }
        }

        return byPath.values.sorted { lhs, rhs in
            if lhs.groupTitle == rhs.groupTitle {
                return lhs.relativePath < rhs.relativePath
            }
            return lhs.groupTitle < rhs.groupTitle
        }
    }

    private func collectRunErrors(
        run: RunItem,
        manifest: [String: Any],
        qoderMetadata: [String: Any]?,
        validators: [RunValidationItem]
    ) -> [RunErrorItem] {
        var errors: [RunErrorItem] = []
        func append(_ source: String, _ message: String?, _ filePath: String = "") {
            guard let message, !message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
            errors.append(RunErrorItem(id: "\(source)-\(errors.count)", source: source, message: message, filePath: filePath))
        }

        append("manifest.error", stringValue(manifest["error"]), run.manifestPath.path)
        append("manifest.stop_reason", stringValue(manifest["stop_reason"]), run.manifestPath.path)
        if let executor = nestedDictionary(manifest, "executor") {
            append("executor.error", stringValue(executor["error"]), run.manifestPath.path)
            append("executor.stop_reason", stringValue(executor["stop_reason"]), run.manifestPath.path)
        }
        if let qoder = nestedDictionary(manifest, "qoder") {
            append("qoder.error", stringValue(qoder["error"]), run.manifestPath.path)
            append("qoder.stop_reason", stringValue(qoder["stop_reason"]), run.manifestPath.path)
        }

        let qoderMetadataPath = run.runDir.appendingPathComponent("qoder/metadata.json").path
        if let qoderMetadata {
            append("qoder.metadata.error", stringValue(qoderMetadata["error"]), qoderMetadataPath)
            append("qoder.metadata.stop_reason", stringValue(qoderMetadata["stop_reason"]), qoderMetadataPath)
            if let metadataErrors = qoderMetadata["errors"] as? [[String: Any]] {
                for (index, error) in metadataErrors.enumerated() {
                    append("qoder.metadata.errors[\(index)]", stringValue(error["message"]) ?? compactJSON(error), qoderMetadataPath)
                }
            }
            if
                let managed = nestedDictionary(qoderMetadata, "managed_agents"),
                let managedError = stringValue(managed["error"])
            {
                append("qoder.managed_agents", managedError, qoderMetadataPath)
            }
        }

        for validator in validators where validator.status != "passed" {
            append("validator.\(validator.validator)", validator.message.isEmpty ? validator.status : validator.message, validator.reportPath)
        }
        return errors
    }

    private func qoderRows(run: RunItem, manifest: [String: Any], qoderMetadata: [String: Any]?) -> [KeyValueRow] {
        let qoder = nestedDictionary(manifest, "qoder") ?? nestedDictionary(manifest, "executor")
        let managed = qoder.flatMap { nestedDictionary($0, "managed_agents") } ?? qoderMetadata.flatMap { nestedDictionary($0, "managed_agents") }
        let delegationsPath = run.runDir.appendingPathComponent("qoder/delegations.jsonl")
        let threadsPath = run.runDir.appendingPathComponent("qoder/threads.json")
        return [
            KeyValueRow(id: "session", key: "Session", value: stringValue(qoder?["session_id"]) ?? stringValue(qoderMetadata?["session_id"]) ?? ""),
            KeyValueRow(id: "status", key: "状态", value: stringValue(qoder?["status"]) ?? stringValue(qoderMetadata?["status"]) ?? ""),
            KeyValueRow(id: "mode", key: "模式", value: stringValue(qoder?["mode"]) ?? stringValue(qoderMetadata?["mode"]) ?? ""),
            KeyValueRow(id: "stop", key: "Stop", value: stringValue(qoder?["stop_reason"]) ?? stringValue(qoderMetadata?["stop_reason"]) ?? ""),
            KeyValueRow(id: "model", key: "模型", value: stringValue(managed?["resolved_model"]) ?? stringValue(managed?["model"]) ?? ""),
            KeyValueRow(id: "schema", key: "Schema", value: "schema_ok=\(stringValue(managed?["schema_ok"]) ?? "") · strategy=\(stringValue(managed?["delegation_strategy"]) ?? "")"),
            KeyValueRow(id: "agents", key: "Agents", value: managedAgentsSummary(managed)),
            KeyValueRow(id: "delegations", key: "Delegations", value: FileManager.default.fileExists(atPath: delegationsPath.path) ? "\(countLines(delegationsPath)) dispatched" : "无"),
            KeyValueRow(id: "threads", key: "Threads", value: FileManager.default.fileExists(atPath: threadsPath.path) ? threadsPath.lastPathComponent : "无")
        ]
    }

    private func artifactItem(from record: [String: Any], runDir: URL) -> RunArtifactItem? {
        guard
            let pathValue = stringValue(record["path"])
                ?? stringValue(record["local_path"])
                ?? stringValue(record["run_relative_path"])
        else {
            return nil
        }
        let url = pathValue.hasPrefix("/") ? URL(fileURLWithPath: pathValue) : runDir.appendingPathComponent(pathValue)
        let relativePath = stringValue(record["run_relative_path"]) ?? relativePath(url, from: runDir)
        let kind = stringValue(record["kind"]) ?? inferredArtifactKind(relativePath)
        return RunArtifactItem(
            id: url.path,
            path: url,
            relativePath: relativePath,
            kind: kind,
            sizeText: fileSizeText(url, fallback: record["size"]),
            modifiedText: modifiedText(url)
        )
    }

    private func readJSONDictionary(_ url: URL, warnings: inout [RunErrorItem]) -> [String: Any]? {
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        do {
            let data = try Data(contentsOf: url)
            return try JSONSerialization.jsonObject(with: data) as? [String: Any]
        } catch {
            warnings.append(RunErrorItem(
                id: "parse-\(url.path)",
                source: "parse",
                message: "\(url.lastPathComponent): \(error.localizedDescription)",
                filePath: url.path
            ))
            return nil
        }
    }

    private func readJSONLines(_ url: URL, warnings: inout [RunErrorItem]) -> [[String: Any]] {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
        var output: [[String: Any]] = []
        for (index, line) in text.split(separator: "\n", omittingEmptySubsequences: true).enumerated() {
            guard let data = String(line).data(using: .utf8) else { continue }
            do {
                if let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    output.append(object)
                }
            } catch {
                warnings.append(RunErrorItem(
                    id: "jsonl-\(url.path)-\(index)",
                    source: "parse.jsonl",
                    message: "\(url.lastPathComponent): line \(index + 1) \(error.localizedDescription)",
                    filePath: url.path
                ))
            }
        }
        return output
    }

    private func bestRunError(from manifest: [String: Any], runDir: URL) -> String {
        if let error = stringValue(manifest["error"]), !error.isEmpty {
            return error
        }
        if let stopReason = stringValue(manifest["stop_reason"]), !stopReason.isEmpty {
            return stopReason
        }
        if let executor = nestedDictionary(manifest, "executor") {
            if let error = stringValue(executor["error"]), !error.isEmpty {
                return error
            }
            if let stopReason = stringValue(executor["stop_reason"]), !stopReason.isEmpty {
                return stopReason
            }
        }
        let qoderMetadata = runDir.appendingPathComponent("qoder/metadata.json")
        var warnings: [RunErrorItem] = []
        if let metadata = readJSONDictionary(qoderMetadata, warnings: &warnings) {
            if let error = stringValue(metadata["error"]), !error.isEmpty {
                return error
            }
            if let stopReason = stringValue(metadata["stop_reason"]), !stopReason.isEmpty {
                return stopReason
            }
            if
                let errors = metadata["errors"] as? [[String: Any]],
                let first = errors.first,
                let message = stringValue(first["message"])
            {
                return message
            }
        }
        return ""
    }

    private func validatorSummary(_ validators: [[String: Any]]) -> String {
        guard !validators.isEmpty else { return "未运行" }
        if validators.allSatisfy({ stringValue($0["status"]) == "passed" }) {
            return "通过"
        }
        if validators.contains(where: { stringValue($0["status"]) == "failed" }) {
            return "失败"
        }
        return "有结果"
    }

    private func validationMessage(from object: [String: Any]) -> String {
        if let error = stringValue(object["error"]), !error.isEmpty {
            return error
        }
        if let message = stringValue(object["message"]), !message.isEmpty {
            return message
        }
        if let checks = object["checks"] as? [[String: Any]] {
            let failed = checks.filter { stringValue($0["status"]) == "failed" }
            let warnings = checks.filter { stringValue($0["status"]) == "warning" }
            if !failed.isEmpty {
                return failed.compactMap { stringValue($0["name"]) ?? stringValue($0["message"]) }.joined(separator: ", ")
            }
            if !warnings.isEmpty {
                return "warnings: " + warnings.compactMap { stringValue($0["name"]) ?? stringValue($0["message"]) }.joined(separator: ", ")
            }
            return "\(checks.count) checks"
        }
        return ""
    }

    private func policyDecisionSummary(_ object: [String: Any]?) -> String {
        guard let object else { return "未记录" }
        let decision = stringValue(object["decision"]) ?? "unknown"
        let reasons = (object["reasons"] as? [Any] ?? []).compactMap(stringValue)
        let warnings = (object["warnings"] as? [Any] ?? []).compactMap(stringValue)
        let suffix = (reasons + warnings).joined(separator: "; ")
        return suffix.isEmpty ? decision : "\(decision): \(suffix)"
    }

    private func managedAgentsSummary(_ managed: [String: Any]?) -> String {
        guard let managed else { return "未启用或未记录" }
        let active = stringValue(managed["active"]) ?? stringValue(managed["enabled"]) ?? ""
        let count = stringValue(managed["agent_count"]) ?? stringValue(managed["total_agents"]) ?? ""
        let model = stringValue(managed["resolved_model"]) ?? stringValue(managed["model"]) ?? ""
        let strategy = stringValue(managed["delegation_strategy"]) ?? ""
        let coordinator = nestedDictionary(managed, "coordinator").flatMap { stringValue($0["name"]) } ?? ""
        return ["active=\(active)", "count=\(count)", "model=\(model)", "strategy=\(strategy)", coordinator]
            .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            .joined(separator: " · ")
    }

    private func nestedDictionary(_ object: [String: Any], _ key: String) -> [String: Any]? {
        object[key] as? [String: Any]
    }

    private func stringValue(_ value: Any?) -> String? {
        guard let value, !(value is NSNull) else { return nil }
        if let string = value as? String {
            return string
        }
        if let bool = value as? Bool {
            return bool ? "true" : "false"
        }
        if let number = value as? NSNumber {
            return number.stringValue
        }
        return nil
    }

    private func compactJSON(_ value: Any) -> String {
        guard JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
              let text = String(data: data, encoding: .utf8)
        else {
            return String(describing: value)
        }
        return text
    }

    private func relativePath(_ url: URL, from baseURL: URL) -> String {
        let path = url.standardizedFileURL.path
        let basePath = baseURL.standardizedFileURL.path
        if path == basePath {
            return url.lastPathComponent
        }
        if path.hasPrefix(basePath + "/") {
            return String(path.dropFirst(basePath.count + 1))
        }
        return path
    }

    private func inferredArtifactKind(_ relativePath: String) -> String {
        if relativePath == "report.md" {
            return "report"
        }
        if relativePath == "summary.md" {
            return "summary"
        }
        if relativePath == "manifest.json" {
            return "manifest"
        }
        if relativePath == "trace.jsonl" {
            return "trace"
        }
        if relativePath.hasPrefix("validation/") {
            return "validation"
        }
        if relativePath.hasPrefix("local_ai/") {
            return "local_ai"
        }
        if relativePath.hasPrefix("qoder/artifacts/") {
            return "qoder_artifact"
        }
        if relativePath.hasPrefix("qoder/") {
            return "qoder_raw"
        }
        return "artifact"
    }

    private func isRawLogArtifact(_ item: RunArtifactItem) -> Bool {
        let path = item.relativePath
        return item.kind == "qoder_raw"
            || item.kind == "lan_raw"
            || item.kind == "trace"
            || item.kind == "manifest"
            || path.hasSuffix(".jsonl")
            || path.hasSuffix(".sse")
            || path.hasSuffix(".json")
            || path.hasSuffix(".txt")
            || path.hasSuffix(".py")
    }

    private func fileSizeText(_ url: URL, fallback: Any? = nil) -> String {
        let size = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber)?.int64Value
            ?? (fallback as? NSNumber)?.int64Value
            ?? Int64(stringValue(fallback) ?? "")
            ?? 0
        if size >= 1_048_576 {
            return String(format: "%.1f MB", Double(size) / 1_048_576.0)
        }
        if size >= 1024 {
            return String(format: "%.1f KB", Double(size) / 1024.0)
        }
        return "\(size) B"
    }

    private func modifiedText(_ url: URL) -> String {
        guard
            let date = try? FileManager.default.attributesOfItem(atPath: url.path)[.modificationDate] as? Date
        else {
            return ""
        }
        let formatter = DateFormatter()
        formatter.dateFormat = "MM-dd HH:mm"
        return formatter.string(from: date)
    }

    private func compactDateTime(_ value: String) -> String {
        guard !value.isEmpty else { return "" }
        let prefix = String(value.prefix(19))
        return prefix.replacingOccurrences(of: "T", with: " ")
    }

    private func durationText(startedAt: String, finishedAt: String) -> String {
        guard !startedAt.isEmpty else { return "未知" }
        guard !finishedAt.isEmpty else { return "运行中" }
        let formatter = ISO8601DateFormatter()
        guard let start = formatter.date(from: startedAt), let finish = formatter.date(from: finishedAt) else {
            return "未知"
        }
        let seconds = max(0, Int(finish.timeIntervalSince(start)))
        if seconds < 60 {
            return "\(seconds)s"
        }
        if seconds < 3600 {
            return "\(seconds / 60)m \(seconds % 60)s"
        }
        return "\(seconds / 3600)h \((seconds % 3600) / 60)m"
    }

    private func countLines(_ url: URL) -> Int {
        guard let text = try? String(contentsOf: url, encoding: .utf8), !text.isEmpty else { return 0 }
        return text.split(separator: "\n", omittingEmptySubsequences: true).count
    }

    private func previewText(from url: URL, maxLines: Int) -> String {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else {
            return "无法读取：\(url.path)"
        }
        let lines = text.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
        if lines.count <= maxLines {
            return text
        }
        return "仅显示最后 \(maxLines) 行：\n" + lines.suffix(maxLines).joined(separator: "\n")
    }

    private func refreshProjectStatus(checkLAN: Bool, checkLocalAI: Bool = false) {
        let args = [
            "project", "status",
            "--project", projectURL.path,
            "--json"
        ] + (checkLAN ? ["--check-lan"] : []) + (checkLocalAI ? ["--check-local-ai"] : [])
        runShortCLI(arguments: args) { [weak self] output, exitCode in
            guard let self else { return }
            if exitCode != 0 {
                self.qoderOK = false
                self.localAIOK = false
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
        let localAI = checkValue("local_ai", in: checks)
        let lan = checkValue("lan", in: checks)
        qoderOK = qoder.ok
        qoderMessage = qoder.message
        localAIOK = localAI.ok
        localAIMessage = localAI.message
        lanOK = lan.ok
        lanMessage = lan.message
        statusItems = [
            StatusItem(id: "project", label: "项目", ok: project.ok, message: statusMessage(project, ok: "已打开", fail: "缺失")),
            StatusItem(id: "qoder", label: "Qoder", ok: qoder.ok, message: statusMessage(qoder, ok: "已就绪", fail: "未配置")),
            StatusItem(id: "local_ai", label: "Local AI", ok: localAI.ok, message: statusMessage(localAI, ok: "已就绪", fail: "未配置")),
            StatusItem(id: "tasks", label: "任务", ok: tasks.ok, message: statusMessage(tasks, ok: "有任务", fail: "无任务")),
            StatusItem(id: "runs", label: "运行", ok: runs.ok, message: statusMessage(runs, ok: "已初始化", fail: "缺失")),
            StatusItem(id: "lan", label: "LAN", ok: lan.ok, message: statusMessage(lan, ok: "正常", fail: "需检查"))
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
            if let models = qoderObject["models"] as? [String: Any] {
                qoderModelsMessage = models["message"] as? String ?? qoderModelsMessage
                qoderNetworkMode = models["network_mode"] as? String ?? qoderNetworkMode
                qoderNetworkModeEffective = models["network_mode_effective"] as? String ?? qoderNetworkModeEffective
            }
            if let managed = qoderObject["managed_agents"] as? [String: Any] {
                qoderManagedMessage = managed["message"] as? String ?? qoderManagedMessage
                qoderManagedReady = managed["ready"] as? Bool ?? false
                qoderManagedModelOK = managed["model_ok"] as? Bool ?? false
                qoderManagedSchemaOK = managed["schema_ok"] as? Bool ?? qoderManagedSchemaOK
                qoderManagedRequestedModel = managed["requested_model"] as? String ?? ""
                qoderManagedResolvedModel = managed["resolved_model"] as? String ?? ""
                qoderManagedModelSource = managed["model_source"] as? String ?? ""
                qoderManagedDelegationStrategy = managed["delegation_strategy"] as? String ?? qoderManagedDelegationStrategy
                qoderManagedIncludeSelf = managed["include_self"] as? Bool ?? false
                qoderManagedConfiguredCount = managed["total_agents"] as? Int ?? qoderManagedConfiguredCount
                qoderManagedAgentCount = managed["agent_count"] as? Int ?? qoderManagedConfiguredCount
                managedAgentsEnabled = managed["enabled"] as? Bool ?? managedAgentsEnabled
                if !isRunning, ["agent_sync", "child_threads"].contains(qoderManagedDelegationStrategy) {
                    managedDelegationStrategy = qoderManagedDelegationStrategy
                }
                if !isRunning && [3, 4, 5].contains(qoderManagedConfiguredCount) {
                    managedAgentCount = qoderManagedConfiguredCount
                }
            }
        }

        if let lanObject = checks["lan"] as? [String: Any] {
            lanEnabled = lanObject["enabled"] as? Bool ?? false
            lanServer = lanObject["server"] as? String ?? ""
            lanProjectRoot = lanObject["project_root"] as? String ?? ""
            lanSSHAlias = lanObject["ssh_alias"] as? String ?? ""
        }

        if let localAIObject = checks["local_ai"] as? [String: Any] {
            localAIEnabled = localAIObject["enabled"] as? Bool ?? false
            localAIProvider = localAIObject["provider"] as? String ?? localAIProvider
            localAIBaseURL = localAIObject["base_url"] as? String ?? localAIBaseURL
            localAIModel = localAIObject["model"] as? String ?? localAIModel
            localAIAPIKeyEnv = localAIObject["api_key_env"] as? String ?? localAIAPIKeyEnv
            localAIEnvFile = localAIObject["env_file"] as? String ?? localAIEnvFile
            localAITransport = localAIObject["transport"] as? String ?? localAITransport
            if let timeout = localAIObject["timeout_seconds"] as? Int {
                localAITimeout = String(timeout)
            }
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

    private func statusMessage(_ check: (ok: Bool, message: String), ok: String, fail: String) -> String {
        let message = check.message.trimmingCharacters(in: .whitespacesAndNewlines)
        return message.isEmpty ? (check.ok ? ok : fail) : message
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

    private func defaultExecutionPreset(for task: TaskItem) -> ExecutionPreset {
        if task.mode == "hybrid" {
            return .decisionHybrid
        }
        if task.mode == "lan_control" || task.type == "lan_experiment" {
            return .experimentLAN
        }
        if task.mode == "full_cloud" || task.type == "cloud_experiment" {
            return .researchCloud
        }
        if task.type == "deep_search" || task.type == "qoder_research" {
            return .researchCloud
        }
        if task.mode == "local_control" || task.type == "local_control" {
            return .decisionTask
        }
        if task.mode == "fake" {
            return .debugFake
        }
        return .decisionTask
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
