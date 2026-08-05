import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { listApprovedTasks, runApprovedTask } from './task-runner.js';
import { buildRepositoryIndex, searchRepositoryIndex } from './repository-indexer.js';
import { createAuthStore } from './auth-store.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname =