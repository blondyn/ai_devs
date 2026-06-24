import * as endpoints from './endpoints';
import sharp from 'sharp';
import readline from 'node:readline';
import { apiGet, getApiKey, submit } from './api';
import { startAgent } from './agent';

export type ToolNames = 'verify' | 'fetch_data' | 'delegate' | 'ask_user';

const MAX_IMAGE_BYTES = 1 * 1024 * 1024;

export async function resizeIfNeeded(buf: Buffer): Promise<Buffer> {
    if (buf.byteLength <= MAX_IMAGE_BYTES) return buf;
    return sharp(buf).resize({ width: 1024, height: 1024, fit: 'inside' }).jpeg({ quality: 70 }).toBuffer();
}

type ToolDef = {
    description: string;
    parameters: Record<string, unknown>;
    handler: (...args: any[]) => Promise<unknown>;
    silent?: boolean;
};

const TOOL_DEFINITIONS: Record<ToolNames, ToolDef> = {
    fetch_data: {
        description: 'Fetch data from a named endpoint. Always use one of the predefined endpoint names.',
        parameters: {
            type: 'object',
            properties: {
                url: {
                    type: 'string',
                    description: 'Endpoint name to fetch. Must be one of the available endpoints.',
                    enum: Object.keys(endpoints),
                },
            },
            required: ['url'],
        },
        handler: async ({ url }: { url: string }) => {
            const path = (endpoints as unknown as Record<string, string | ((...args: any[]) => string)>)[url] ?? url;
            if (typeof path === 'function') return apiGet<ArrayBuffer>(path(getApiKey()));
            return apiGet<string>(path, 'text');
        },
    },

    verify: {
        description: 'Submit the final answer for verification',
        parameters: {
            type: 'object',
            properties: {
                task: { type: 'string', description: 'Task name' },
                answer: {
                    type: 'object',
                    description: 'Answer payload',
                    properties: {
                        instructions: {
                            type: 'array',
                            items: { type: 'string' },
                            description: 'List of drone navigation instructions',
                        },
                    },
                    required: ['instructions'],
                },
            },
            required: ['task', 'answer'],
        },
        handler: async ({ task, answer }: { task: string; answer: unknown }) => {
            try {
                return await submit(task, answer);
            } catch (e: any) {
                const msg = e?.body ?? e?.message ?? String(e);
                return `Verification failed: ${msg}`;
            }
        },
    },
    delegate: {
        description: 'Delegate the work to another agent and wait for the response from it',
        parameters: {
            type: 'object',
            properties: {
                name: { type: 'string', description: 'Name of the agent' },
                task: { type: 'string', description: 'Task for the agent to perform' },
            },
            required: ['name', 'task'],
        },
        handler: async ({ name, task }: Record<string, string>) => {
            console.log(`starting agent ${name}`);
            return startAgent(name, task);
        },
    },
    ask_user: {
        description: 'Ask the human user a question and wait for their response',
        parameters: {
            type: 'object',
            properties: {
                question: { type: 'string', description: 'The question to ask the user' },
            },
            required: ['question'],
        },
        silent: true,
        handler: ({ question }: { question: string }) => new Promise<string>(resolve => {
            process.stdout.write(`\n${question}\nYou: `);
            const rl = readline.createInterface({ input: process.stdin, terminal: false });
            rl.once('line', answer => { rl.close(); resolve(answer); });
        }),
    },
};

export const TOOLS: Record<string, object> = Object.fromEntries(
    Object.entries(TOOL_DEFINITIONS).map(([name, def]) => [name, {
        type: 'function',
        function: { name, description: def.description, parameters: def.parameters },
    }])
);

export async function tool_call(name: string, fn_args: string): Promise<unknown> {
    const def = TOOL_DEFINITIONS[name as ToolNames];
    if (!def) throw new Error(`Couldn't find the tool: ${name}`);
    if (!def.silent) console.log(`calling ${name} ${fn_args}`);
    return def.handler(JSON.parse(fn_args));
}

export function prepTools(toolList: string[], config: Record<string, unknown> = {}): object[] {
    return toolList.flatMap(name => {
        const tool = structuredClone(TOOLS[name]);
        if (!tool) return [];
        if (name === 'fetch_data' && Array.isArray(config.fetch_data_endpoints)) {
            (tool as any).function.parameters.properties.url.enum = config.fetch_data_endpoints;
        }
        return [tool];
    });
}
