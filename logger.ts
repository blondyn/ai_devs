import { appendFileSync, mkdirSync, writeFileSync } from 'fs';
import { join } from 'path';

type Sink = 'console' | 'file' | 'http';
type Level = 'debug' | 'info' | 'error';

const LEVELS: Record<Level, number> = { debug: 0, info: 1, error: 2 };

interface LoggerConfig {
    level?: Level;
    sinks?: Sink[];
    outputDir?: string;
    endpoint?: string;
}

class Logger {
    private level: number;
    private sinks: Sink[];
    private outputDir: string;
    private endpoint: string | undefined;

    constructor(config: LoggerConfig = {}) {
        this.level = LEVELS[config.level ?? 'info'];
        this.sinks = config.sinks ?? ['console'];
        this.outputDir = config.outputDir ?? '.';
        this.endpoint = config.endpoint;
        if (this.sinks.includes('file')) {
            mkdirSync(this.outputDir, { recursive: true });
        }
    }

    private emit(level: Level, message: string, data?: unknown) {
        if (LEVELS[level] < this.level) return;

        const entry = { level, message, ...(data !== undefined && { data }), timestamp: Date.now() };

        if (this.sinks.includes('console')) {
            const fn = level === 'error' ? console.error : console.log;
            data !== undefined ? fn(`[${level}] ${message}`, data) : fn(`[${level}] ${message}`);
        }

        if (this.sinks.includes('file')) {
            appendFileSync(join(this.outputDir, 'run.log'), JSON.stringify(entry) + '\n');
        }

        if (this.sinks.includes('http') && this.endpoint) {
            fetch(this.endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(entry),
            }).catch(() => {});
        }
    }

    debug(message: string, data?: unknown) { this.emit('debug', message, data); }
    info(message: string, data?: unknown) { this.emit('info', message, data); }
    error(message: string, data?: unknown) { this.emit('error', message, data); }

    artifact(name: string, data: Buffer | string) {
        mkdirSync(this.outputDir, { recursive: true });
        writeFileSync(join(this.outputDir, name), data);
    }
}

const sinks = (process.env.LOG_SINKS ?? 'console').split(',').filter(Boolean) as Sink[];

export const logger = new Logger({
    level: (process.env.LOG_LEVEL as Level) ?? 'info',
    sinks,
    outputDir: process.env.LOG_OUTPUT_DIR ?? '.',
    endpoint: process.env.LOG_ENDPOINT,
});
