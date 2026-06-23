import * as endpoints from './endpoints';
import sharp from 'sharp';
import { apiGet, getApiKey, submit } from './api';
import { startAgent } from './agent';

export type ToolNames = 'verify' | 'fetch_data' | 'delegate';

const MAX_IMAGE_BYTES = 1 * 1024 * 1024;

export async function resizeIfNeeded(buf: Buffer): Promise<Buffer> {
    if (buf.byteLength <= MAX_IMAGE_BYTES) return buf;
    return sharp(buf).resize({ width: 1024, height: 1024, fit: 'inside' }).png().toBuffer();
}

const TOOLS_MAPPING: Record<ToolNames, (...args: any[]) => Promise<unknown>> = {
    fetch_data: async ({ url }: { url: string }) => {
        const path = (endpoints as unknown as Record<string, string | ((...args: any[]) => string)>)[url] ?? url;
        if (typeof path === 'function') {
            return apiGet<ArrayBuffer>(path(getApiKey()));
        }
        return apiGet<string>(path, 'text');
    },
    verify: submit,
    delegate: async ({ name, task }: Record<string, string>) => {
        console.log(`starting agent ${name}`);
        return startAgent(name, task);
    }
} as const satisfies Record<string, Function>;

export async function tool_call(name: string, fn_args: string): Promise<unknown> {
    if (!(name in TOOLS_MAPPING)) throw new Error("Couldn't find the tool");
    return TOOLS_MAPPING[name as ToolNames].call(null, JSON.parse(fn_args));
}

export const TOOLS: Record<string, object> = {
    delegate: {
        type: 'function' as const,
        function: {
            name: 'delegate',
            description: 'Delegate the work to another agent and wait for the response from it',
            parameters: {
                type: 'object',
                properties: {
                    name: { type: 'string', description: 'Name of the agent' },
                    task: { type: 'string', description: 'Task for the agent to perform' },
                },
                required: ['name', 'task'],
            },
        },
    },
    fetch_data: {
        type: 'function' as const,
        function: {
            name: 'fetch_data',
            description: 'Fetch data from a named endpoint. Always use one of the predefined endpoint names.',
            parameters: {
                type: 'object',
                properties: {
                    url: {
                        type: 'string',
                        description: 'Endpoint name to fetch. Must be one of the available endpoints.',
                        enum: Object.keys(endpoints).filter(str => str.toLowerCase().includes('drone')),
                    },
                },
                required: ['url'],
            },
        },
    },
    verify: {
        type: 'function' as const,
        function: {
            name: 'verify',
            description: 'Submit the final answer for verification',
            parameters: {
                type: 'object',
                properties: {
                    task: { type: 'string', description: 'Task name' },
                    answer: { type: 'string', description: 'Answer to submit' },
                },
                required: ['task', 'answer'],
            },
        },
    },
};

export function prepTools(toolList: string[]): object[] {
    return toolList.map(name => TOOLS[name]).filter(d => d);
}
