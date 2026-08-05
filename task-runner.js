import { spawn } from 'node:child_process';

const TASKS = Object.freeze({
  syntax: { command: process.execPath, args: ['--check', 'server.js'], label: 'Check server syntax' },
  health: { command: process.execPath, args: ['-e', "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/api/health').then(r=>r.text()).then(console.log)"], label: 'Check running server health' },
  git_status: { command: 'git', args: ['status', '--short', '--branch'], label: 'Show Git status' },
  files: { command: 'find', args: ['.', '-maxdepth', '2', '-type', 'f'], label: 'List project files' }
});

export function listApprovedTasks() {
  return Object.entries(TASKS).map(([id, task]) => ({ id, label: task.label }));
}

export function runApprovedTask(taskId, cwd, timeoutMs = 20000) {
  const task = TASKS[taskId];
  if (!task) throw new Error('Unknown or unapproved task.');

  return new Promise((resolve, reject) => {
    const child = spawn(task.command, task.args, {
      cwd,
      env: process.env,
      shell: false,
      stdio: ['ignore', 'pipe', 'pipe']
    });

    let stdout = '';
    let stderr = '';
    const limit = 200000;
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      reject(new Error(`Task timed out after ${timeoutMs} ms.`));
    }, timeoutMs);

    child.stdout.on('data', (chunk) => { if (stdout.length < limit) stdout += chunk; });
    child.stderr.on('data', (chunk) => { if (stderr.length < limit) stderr += chunk; });
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code, signal) => {
      clearTimeout(timer);
      resolve({ taskId, label: task.label, code, signal, stdout, stderr, ok: code === 0 });
    });
  });
}
