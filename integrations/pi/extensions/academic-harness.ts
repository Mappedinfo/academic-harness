import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Text } from "@earendil-works/pi-tui";
import { Type } from "typebox";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, isAbsolute, resolve } from "node:path";
import { fileURLToPath } from "node:url";

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

type CommandResult = {
  command: string;
  args: string[];
  exitCode: number | null;
  signal: NodeJS.Signals | null;
  stdout: string;
  stderr: string;
};

type HarnessResult = {
  ok: boolean;
  exitCode: number | null;
  command: string;
  args: string[];
  source: string;
  stdout: string;
  stderr: string;
  data: unknown;
  parseError?: string;
};

const extensionFile = fileURLToPath(import.meta.url);
const packageRoot = resolve(dirname(extensionFile), "..");
const repoRoot = resolve(packageRoot, "..", "..");

export default function academicHarnessExtension(pi: ExtensionAPI) {
  registerTools(pi);
  registerCommands(pi);
  registerRenderers(pi);
}

function registerTools(pi: ExtensionAPI) {
  pi.registerTool({
    name: "academic_project_status",
    label: "Academic Project Status",
    description: "Check Academic Harness project configuration through the kernel CLI.",
    parameters: Type.Object({
      project: Type.String({ description: "Academic Harness project directory" }),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      return executeHarnessTool(pi, ctx, "academic_project_status", ["project", "status", "--project", normalizePath(params.project, ctx), "--json"], signal);
    },
    renderResult: renderHarnessToolResult,
  });

  pi.registerTool({
    name: "academic_list_tasks",
    label: "Academic List Tasks",
    description: "List Academic Harness tasks in a project as JSON.",
    parameters: Type.Object({
      project: Type.String({ description: "Academic Harness project directory" }),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      return executeHarnessTool(pi, ctx, "academic_list_tasks", ["task", "list", "--project", normalizePath(params.project, ctx), "--json"], signal);
    },
    renderResult: renderHarnessToolResult,
  });

  pi.registerTool({
    name: "academic_run_task",
    label: "Academic Run Task",
    description: "Run one Academic Harness task through the kernel. Defaults to adapter auto.",
    parameters: Type.Object({
      project: Type.String({ description: "Academic Harness project directory" }),
      task: Type.String({ description: "Task YAML path, project-relative path, or filename under tasks/" }),
      adapter: Type.Optional(Type.String({ description: "Academic Harness adapter, default auto" })),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const project = normalizePath(params.project, ctx);
      const task = resolveTaskPath(project, params.task);
      const adapter = params.adapter || "auto";
      return executeHarnessTool(pi, ctx, "academic_run_task", ["task", "run", task, "--project", project, "--adapter", adapter, "--json"], signal);
    },
    renderResult: renderHarnessToolResult,
  });

  pi.registerTool({
    name: "academic_show_run",
    label: "Academic Show Run",
    description: "Read one Academic Harness run manifest.",
    parameters: Type.Object({
      project: Type.String({ description: "Academic Harness project directory" }),
      run_id: Type.String({ description: "Run id" }),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      return executeHarnessTool(pi, ctx, "academic_show_run", ["run", "show", params.run_id, "--project", normalizePath(params.project, ctx)], signal);
    },
    renderResult: renderHarnessToolResult,
  });

  pi.registerTool({
    name: "academic_validate_run",
    label: "Academic Validate Run",
    description: "Rerun Academic Harness validators for a run and return the updated manifest.",
    parameters: Type.Object({
      project: Type.String({ description: "Academic Harness project directory" }),
      run_id: Type.String({ description: "Run id" }),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      return executeHarnessTool(pi, ctx, "academic_validate_run", ["validate", params.run_id, "--project", normalizePath(params.project, ctx), "--json"], signal);
    },
    renderResult: renderHarnessToolResult,
  });

  pi.registerTool({
    name: "academic_read_trace",
    label: "Academic Read Trace",
    description: "Read parsed Academic Harness trace.jsonl events for a run.",
    parameters: Type.Object({
      project: Type.String({ description: "Academic Harness project directory" }),
      run_id: Type.String({ description: "Run id" }),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      return executeHarnessTool(pi, ctx, "academic_read_trace", ["run", "trace", params.run_id, "--project", normalizePath(params.project, ctx), "--json"], signal);
    },
    renderResult: renderHarnessToolResult,
  });
}

function registerCommands(pi: ExtensionAPI) {
  pi.registerCommand("ah-status", {
    description: "Show Academic Harness project status",
    handler: async (args, ctx) => {
      const project = commandProject(args, ctx);
      await runCommandAndAppend(pi, ctx, "academic_project_status", ["project", "status", "--project", project, "--json"]);
    },
  });

  pi.registerCommand("ah-run", {
    description: "Run an Academic Harness task: /ah-run <task.yaml> [adapter]",
    handler: async (args, ctx) => {
      const parts = splitCommandArgs(args);
      if (parts.length === 0) {
        ctx.ui.notify("Usage: /ah-run <task.yaml> [adapter]", "warning");
        return;
      }
      const project = normalizePath(".", ctx);
      const task = resolveTaskPath(project, parts[0]);
      const adapter = parts[1] || "auto";
      await runCommandAndAppend(pi, ctx, "academic_run_task", ["task", "run", task, "--project", project, "--adapter", adapter, "--json"]);
    },
  });

  pi.registerCommand("ah-show", {
    description: "Show an Academic Harness run manifest: /ah-show <run_id>",
    handler: async (args, ctx) => {
      const runId = splitCommandArgs(args)[0];
      if (!runId) {
        ctx.ui.notify("Usage: /ah-show <run_id>", "warning");
        return;
      }
      await runCommandAndAppend(pi, ctx, "academic_show_run", ["run", "show", runId, "--project", normalizePath(".", ctx)]);
    },
  });

  pi.registerCommand("ah-validate", {
    description: "Rerun validators for an Academic Harness run: /ah-validate <run_id>",
    handler: async (args, ctx) => {
      const runId = splitCommandArgs(args)[0];
      if (!runId) {
        ctx.ui.notify("Usage: /ah-validate <run_id>", "warning");
        return;
      }
      await runCommandAndAppend(pi, ctx, "academic_validate_run", ["validate", runId, "--project", normalizePath(".", ctx), "--json"]);
    },
  });

  pi.registerCommand("ah-trace", {
    description: "Show parsed trace events for an Academic Harness run: /ah-trace <run_id>",
    handler: async (args, ctx) => {
      const runId = splitCommandArgs(args)[0];
      if (!runId) {
        ctx.ui.notify("Usage: /ah-trace <run_id>", "warning");
        return;
      }
      await runCommandAndAppend(pi, ctx, "academic_read_trace", ["run", "trace", runId, "--project", normalizePath(".", ctx), "--json"]);
    },
  });

  pi.registerCommand("ah-qoder-cloud", {
    description: "Run an Academic Harness task through Qoder Cloud: /ah-qoder-cloud <task.yaml>",
    handler: async (args, ctx) => {
      const taskArg = splitCommandArgs(args)[0];
      if (!taskArg) {
        ctx.ui.notify("Usage: /ah-qoder-cloud <task.yaml>", "warning");
        return;
      }
      const project = normalizePath(".", ctx);
      const task = resolveTaskPath(project, taskArg);
      await runCommandAndAppend(pi, ctx, "academic_run_task", ["task", "run", task, "--project", project, "--adapter", "qoder_cloud", "--json"]);
    },
  });
}

function registerRenderers(pi: ExtensionAPI) {
  pi.registerMessageRenderer("academic_harness_result", (message, _options, theme) => {
    const details = message.details as { result?: HarnessResult } | undefined;
    return renderHarnessResult(details?.result, theme);
  });
}

async function executeHarnessTool(pi: ExtensionAPI, ctx: any, label: string, args: string[], signal?: AbortSignal) {
  const result = await runHarnessJSON(args, ctx, signal);
  const entryId = appendHiddenRunEntry(pi, ctx, label, result);
  await linkRunToPiIfPossible(pi, ctx, result, projectFromArgs(args), entryId);
  return toolResponse(label, result);
}

async function runCommandAndAppend(pi: ExtensionAPI, ctx: any, label: string, args: string[]) {
  const result = await runHarnessJSON(args, ctx, ctx.signal);
  const summary = summarize(label, result);
  pi.sendMessage(
    {
      customType: "academic_harness_result",
      content: summary,
      display: true,
      details: {
        label,
        summary,
        result,
      } as JsonValue,
    },
    { triggerTurn: false },
  );
  const entryId = ctx.sessionManager.getLeafId?.();
  await linkRunToPiIfPossible(pi, ctx, result, projectFromArgs(args), entryId);
  ctx.ui.notify(summary, result.ok ? "info" : "warning");
}

function appendHiddenRunEntry(pi: ExtensionAPI, ctx: any, label: string, result: HarnessResult): string | undefined {
  const runId = runIdFromResult(result);
  if (!runId) {
    return undefined;
  }
  const summary = summarize(label, result);
  pi.appendEntry("academic_harness_result", {
    label,
    summary,
    result,
  } as JsonValue);
  return ctx.sessionManager.getLeafId?.();
}

async function runHarnessJSON(args: string[], ctx: any, signal?: AbortSignal): Promise<HarnessResult> {
  const candidates = cliCandidates();
  const cwd = normalizePath(".", ctx);
  const spawnErrors: string[] = [];
  for (const candidate of candidates) {
    try {
      const result = await runProcess(candidate.command, [...candidate.baseArgs, ...args], cwd, signal);
      const parsed = parseJSON(result.stdout);
      return {
        ok: result.exitCode === 0,
        exitCode: result.exitCode,
        command: result.command,
        args: result.args,
        source: candidate.source,
        stdout: result.stdout,
        stderr: result.stderr,
        data: parsed.ok ? parsed.data : null,
        ...(parsed.ok ? {} : { parseError: parsed.error }),
      };
    } catch (error) {
      spawnErrors.push(`${candidate.source}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  return {
    ok: false,
    exitCode: null,
    command: "",
    args,
    source: "none",
    stdout: "",
    stderr: spawnErrors.join("\n"),
    data: null,
    parseError: "Academic Harness CLI could not be started",
  };
}

function cliCandidates(): Array<{ source: string; command: string; baseArgs: string[] }> {
  const candidates: Array<{ source: string; command: string; baseArgs: string[] }> = [];
  const envCli = process.env.ACADEMIC_HARNESS_CLI?.trim();
  if (envCli) {
    candidates.push({ source: "ACADEMIC_HARNESS_CLI", command: envCli, baseArgs: [] });
  }
  if (existsSync(resolve(repoRoot, "pyproject.toml"))) {
    candidates.push({ source: "repo-local uv", command: "uv", baseArgs: ["run", "--project", repoRoot, "academic-harness"] });
  }
  candidates.push({ source: "PATH", command: "academic-harness", baseArgs: [] });
  return candidates;
}

function runProcess(command: string, args: string[], cwd: string, signal?: AbortSignal): Promise<CommandResult> {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
      shell: false,
    });
    let stdout = "";
    let stderr = "";
    const abort = () => child.kill("SIGTERM");
    signal?.addEventListener("abort", abort, { once: true });
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", (error) => {
      signal?.removeEventListener("abort", abort);
      reject(error);
    });
    child.on("close", (exitCode, exitSignal) => {
      signal?.removeEventListener("abort", abort);
      resolvePromise({
        command,
        args,
        exitCode,
        signal: exitSignal,
        stdout,
        stderr,
      });
    });
  });
}

function parseJSON(text: string): { ok: true; data: unknown } | { ok: false; error: string } {
  try {
    return { ok: true, data: JSON.parse(text) };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

function toolResponse(label: string, result: HarnessResult) {
  return {
    content: [{ type: "text" as const, text: summarize(label, result) }],
    details: result,
  };
}

function renderHarnessToolResult(result: any, _options: any, theme: any) {
  return renderHarnessResult(result.details as HarnessResult | undefined, theme);
}

function renderHarnessResult(result: HarnessResult | undefined, theme: any) {
  if (!result) {
    return new Text(theme.fg("dim", "No Academic Harness result"), 0, 0);
  }
  if (result.parseError) {
    return new Text(theme.fg("warning", `Academic Harness output was not JSON: ${result.parseError}`), 0, 0);
  }
  const data = result.data as any;
  if (Array.isArray(data)) {
    const lines = [theme.fg("toolTitle", theme.bold(`Tasks: ${data.length}`))];
    for (const task of data.slice(0, 10)) {
      lines.push(`${task.task_id || task.relative_path}  ${theme.fg("muted", `${task.type || ""} ${task.mode || ""}`.trim())}`);
    }
    if (data.length > 10) {
      lines.push(theme.fg("dim", `... ${data.length - 10} more`));
    }
    return new Text(lines.join("\n"), 0, 0);
  }
  if (data?.checks) {
    const lines = [theme.fg("toolTitle", theme.bold(`Project: ${data.ok ? "ok" : "needs attention"}`))];
    for (const [name, check] of Object.entries(data.checks) as Array<[string, any]>) {
      const mark = check?.ok ? theme.fg("success", "ok") : theme.fg("warning", "fail");
      lines.push(`${name}: ${mark} ${theme.fg("muted", check?.message || "")}`);
    }
    return new Text(lines.join("\n"), 0, 0);
  }
  return new Text(renderRunLines(data, theme).join("\n"), 0, 0);
}

function renderRunLines(data: any, theme: any): string[] {
  const runId = data?.run_id || "unknown";
  const state = data?.state || data?.status || "unknown";
  const status = data?.status || state;
  const statusColor = status === "passed" || status === "succeeded" ? "success" : status === "failed" || status === "blocked" ? "warning" : "text";
  const lines = [
    `${theme.fg("toolTitle", theme.bold("Run:"))} ${runId}`,
    `${theme.fg("toolTitle", theme.bold("State:"))} ${theme.fg(statusColor, state)}`,
    `${theme.fg("toolTitle", theme.bold("Policy:"))} ${policySummary(data?.policy)}`,
  ];
  if (data?.adapter || data?.mode) {
    lines.push(`${theme.fg("toolTitle", theme.bold("Adapter:"))} ${data.adapter || ""}${data.mode ? ` (${data.mode})` : ""}`);
  }
  const validators = Array.isArray(data?.validators) ? data.validators : [];
  lines.push(theme.fg("toolTitle", theme.bold("Validators:")));
  if (validators.length === 0) {
    lines.push(`  ${theme.fg("dim", "none")}`);
  } else {
    for (const validator of validators.slice(0, 8)) {
      const statusText = validator.status || "unknown";
      const color = statusText === "passed" ? "success" : "warning";
      lines.push(`  ${validator.validator || "validator"} ${theme.fg(color, statusText)}`);
    }
    if (validators.length > 8) {
      lines.push(`  ${theme.fg("dim", `... ${validators.length - 8} more`)}`);
    }
  }
  const artifacts = Array.isArray(data?.artifacts) ? data.artifacts : [];
  lines.push(theme.fg("toolTitle", theme.bold("Artifacts:")));
  const artifactPaths = artifactSummaryPaths(data, artifacts);
  if (artifactPaths.length === 0) {
    lines.push(`  ${theme.fg("dim", "none")}`);
  } else {
    for (const artifactPath of artifactPaths.slice(0, 10)) {
      lines.push(`  ${artifactPath}`);
    }
    if (artifactPaths.length > 10) {
      lines.push(`  ${theme.fg("dim", `... ${artifactPaths.length - 10} more`)}`);
    }
  }
  return lines;
}

function policySummary(policy: any): string {
  if (!policy || typeof policy !== "object") {
    return "not recorded";
  }
  const parts: string[] = [];
  if (policy.preflight?.decision) {
    parts.push(`preflight=${policy.preflight.decision}`);
  }
  if (policy.post_artifact?.decision) {
    parts.push(`post_artifact=${policy.post_artifact.decision}`);
  }
  return parts.length ? parts.join(" ") : "not recorded";
}

function artifactSummaryPaths(data: any, artifacts: any[]): string[] {
  const paths: string[] = [];
  if (data?.report_path) {
    paths.push(shortArtifactPath(data.report_path));
  }
  if (data?.summary_path) {
    paths.push(shortArtifactPath(data.summary_path));
  }
  for (const artifact of artifacts) {
    const path = artifact.run_relative_path || artifact.relative_path || artifact.path;
    if (path) {
      const short = shortArtifactPath(String(path));
      if (!paths.includes(short)) {
        paths.push(short);
      }
    }
  }
  return paths;
}

function shortArtifactPath(path: string): string {
  const marker = "/.workbench/runs/";
  const index = path.indexOf(marker);
  if (index >= 0) {
    const rest = path.slice(index + marker.length);
    const parts = rest.split("/");
    return parts.slice(1).join("/") || parts[0] || path;
  }
  return path;
}

async function linkRunToPiIfPossible(
  pi: ExtensionAPI,
  ctx: any,
  result: HarnessResult,
  project: string | undefined,
  entryId: string | undefined,
) {
  const runId = runIdFromResult(result);
  const projectRoot = project || projectRootFromResult(result);
  const sessionId = ctx.sessionManager.getSessionId?.();
  if (!runId || !projectRoot || !sessionId || !entryId) {
    return;
  }
  const linkArgs = [
    "run",
    "link-pi",
    runId,
    "--project",
    projectRoot,
    "--pi-session-id",
    sessionId,
    "--pi-entry-id",
    entryId,
  ];
  const sessionFile = ctx.sessionManager.getSessionFile?.();
  if (sessionFile) {
    linkArgs.push("--pi-session-file", sessionFile);
  }
  const linked = await runHarnessJSON(linkArgs, ctx, undefined);
  if (!linked.parseError && linked.data) {
    result.data = linked.data;
  } else if (linked.stderr || linked.parseError) {
    pi.appendEntry("academic_harness_link_error", {
      run_id: runId,
      error: linked.stderr || linked.parseError,
    } as JsonValue);
  }
}

function runIdFromResult(result: HarnessResult): string | undefined {
  const data = result.data as any;
  return typeof data?.run_id === "string" && data.run_id ? data.run_id : undefined;
}

function projectRootFromResult(result: HarnessResult): string | undefined {
  const data = result.data as any;
  return typeof data?.project_root === "string" && data.project_root ? data.project_root : undefined;
}

function projectFromArgs(args: string[]): string | undefined {
  const index = args.indexOf("--project");
  if (index >= 0 && args[index + 1]) {
    return args[index + 1];
  }
  return undefined;
}

function summarize(label: string, result: HarnessResult): string {
  if (result.parseError) {
    return `${label}: CLI output was not JSON (${result.parseError})`;
  }
  const data = result.data as any;
  if (label === "academic_project_status") {
    const checks = data?.checks ? Object.entries(data.checks).map(([key, value]: [string, any]) => `${key}=${value?.ok ? "ok" : "fail"}`) : [];
    return `project status: ${data?.ok ? "ok" : "needs attention"}${checks.length ? ` (${checks.join(", ")})` : ""}`;
  }
  if (label === "academic_list_tasks") {
    return `tasks: ${Array.isArray(data) ? data.length : 0}`;
  }
  if (label === "academic_read_trace") {
    const events = Array.isArray(data?.events) ? data.events : [];
    const last = events.length ? events[events.length - 1]?.type : "none";
    return `trace ${data?.run_id || ""}: ${events.length} events, last=${last}`;
  }
  const runId = data?.run_id || "";
  const status = data?.status || (result.ok ? "ok" : "failed");
  const adapter = data?.adapter || data?.resolved_adapter || "";
  const report = data?.report_path ? ` report=${data.report_path}` : "";
  return `${label}: ${runId} status=${status}${adapter ? ` adapter=${adapter}` : ""}${report}`;
}

function normalizePath(input: string, ctx: any): string {
  const base = typeof ctx?.cwd === "string" ? ctx.cwd : process.cwd();
  if (!input || input === ".") {
    return base;
  }
  return isAbsolute(input) ? input : resolve(base, input);
}

function resolveTaskPath(project: string, task: string): string {
  if (isAbsolute(task)) {
    return task;
  }
  const direct = resolve(project, task);
  if (existsSync(direct)) {
    return direct;
  }
  return resolve(project, "tasks", task);
}

function commandProject(args: string | undefined, ctx: any): string {
  const first = splitCommandArgs(args)[0];
  return first ? normalizePath(first, ctx) : normalizePath(".", ctx);
}

function splitCommandArgs(args: string | undefined): string[] {
  return (args || "").trim().split(/\s+/).filter(Boolean);
}
