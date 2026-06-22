import { config } from "dotenv";
import { resolve } from "path";
import { readFileSync } from 'fs';
import matter from 'gray-matter';

config({ path: resolve(__dirname, ".env") });

const BASE_URL = process.env.API_BASE_URL ?? "https://hub.ag3nts.org";
const DEFAULT_MODEL = process.env.LLM_MODEL ?? "google/gemini-2.0-flash-001";

export class ApiError extends Error {
    constructor(public code: number, public body: string) {
        super(`HTTP ${code}: ${body}`);
    }
}

export function getApiKey(): string {
    const key = process.env.AGENTS_KEY;
    if (!key) { console.error("AGENTS_KEY not set"); process.exit(1); }
    return key;
}

export async function apiPost<T = unknown>(endpoint: string, payload: unknown): Promise<T> {
    const resp = await fetch(`${BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    const body = await resp.json();
    if (!resp.ok) throw new ApiError(resp.status, JSON.stringify(body));
    return body as T;
}

type Parser<T> = "json" | "text" | "binary" | ((raw: string) => T);

export async function apiGet<T = unknown>(path: string, parser: Parser<T> = "json"): Promise<T> {
    const resp = await fetch(`${BASE_URL}${path}`);
    if (!resp.ok) throw new ApiError(resp.status, await resp.text());

    if (parser === "binary") return resp.arrayBuffer() as unknown as T;
    const text = await resp.text();
    if (parser === "text") return text as unknown as T;
    if (parser === "json") return JSON.parse(text) as T;
    return parser(text);
}

export async function llm(
    messages: Record<string, unknown>[],
    options: {
        model?: string;
        tools?: any,
        schema?: Record<string, unknown>;
        maxTokens?: number;
        temperature?: number;
        raw?: boolean;
    } = {}
): Promise<string | Record<string, unknown>> {
    const { model = DEFAULT_MODEL, tools, schema, maxTokens = 1024, temperature, raw } = options;

    const r = await fetch('https://openrouter.ai/api/v1/chat/completions', {
        method: "POST",
        headers: {
            Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            model,
            messages,
            ...(tools && { tools }),
            ...(maxTokens && { max_tokens: maxTokens }),
            ...(temperature !== undefined && { temperature }),
        })
    })
    const resp = await r.json();
    console.log({resp, meta: resp.error.metadata});
    const msg = resp.choices[0].message;
    if (raw) return msg;
    if (schema) return JSON.parse(msg.content ?? "{}");
    return msg.content ?? "";
}

export async function submit(task: string, answer: unknown): Promise<unknown> {
    const result = await apiPost("/verify", { apikey: getApiKey(), task, answer });
    console.log("Response:", JSON.stringify(result, null, 2));
    return result;
}


const TOOLS : Record<string, object> = {
    delegate: {
        type: 'function' as const,
        name: 'delegate',
        description: 'Delegate the work to another agent and wait for the reponse from it',
        parameters: {
            type: 'object',
            properties: {
                name: {
                    type: 'string',
                    description: 'Name of the agent',
                },
                task: {
                    type: 'string',
                    description: 'Task for the agent to perform'
                },
            },
            required: ['name', 'task'],
            "additionalProperties": false
        }

    },
    fetch_data: {
        type: 'function' as const,
        name: 'fetch_data',
        description: 'Fetch data from a URL or API path',
        parameters: {
            type: 'object',
            properties: {
                url: { type: 'string', description: 'URL or path to fetch' },
            },
            required: ['url'],
            "additionalProperties": false
        }
    },
    verify: {
        type: 'function' as const,
        name: 'verify',
        description: 'Submit the final answer for verification',
        parameters: {
            type: 'object',
            properties: {
                task: { type: 'string', description: 'Task name' },
                answer: { type: 'string', description: 'Answer to submit' },
            },
            required: ['task', 'answer'],
            "additionalProperties": false
        }
    },
}

function prepTools(toolList: string[]): object[] {
    return toolList.map(name => TOOLS[name]).filter(d => d);
}

export async function startAgent(agent: string): Promise<unknown> {
    const raw = readFileSync(`workflows/${agent}.md`, 'utf-8');
    const { data, content } = matter(raw);
    return llm([{ role: 'system', content }], { tools: prepTools(data.tools), model: data.model});
}
