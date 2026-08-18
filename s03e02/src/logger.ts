import { appendFileSync, mkdirSync, writeFileSync } from "fs";
import { join } from "path";

type Level = 'info' | 'error';
type Sink = 'console' | 'file';

export class Logger {
    private level: Level
    private outputDirectory: string;
    private sinks: Sink[];


    constructor({ artifactDirectory, sinks, level }: { artifactDirectory: string, sinks: Sink[], level: Level }) {
        this.outputDirectory = artifactDirectory;
        this.sinks = sinks;
        this.level = level;
    }

    emit(level: string, message: string, data?: unknown) {
        if (this.level === 'error' && level === 'info') {
            return;
        }

        const entry = { timestamp: new Date().toISOString(), level, message, ...(data != undefined && { data }) }
        if (this.sinks.includes('console')) {
            const fn = level === 'error' ? console.error : console.log;
            data != null ? fn(`[${entry.timestamp}][${level}] ${message}`, data) : fn(`[${entry.timestamp}][${level}] ${message}`);
        }

        if (this.sinks.includes('file')) {
            appendFileSync(join(this.outputDirectory, 'run.log'), JSON.stringify(entry) + '\n');
        }
    }

    info(message: string, data?: string | Buffer) {
        this.emit('info', message, data);
    }

    error(message: string, data?: string | Buffer) {
        this.emit('error', message, data);
    }

    artifact(name: string, data: string | Buffer) {
        mkdirSync(this.outputDirectory, { recursive: true });
        writeFileSync(join(this.outputDirectory, name), data)
    }
}