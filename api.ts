import { config } from "dotenv";
import { resolve } from "path";

config({ path: resolve(__dirname, ".env") });

export const BASE_URL = process.env.API_BASE_URL ?? "https://hub.ag3nts.org";

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

export async function apiGet<T = unknown>(path: string, parser?: Parser<T>): Promise<T> {
    const resp = await fetch(`${BASE_URL}${path}`);
    if (!resp.ok) throw new ApiError(resp.status, await resp.text());
    const contentType = resp.headers.get('content-type');

    if (contentType != null && parser == null) {
        if (contentType.includes('application/json')) return resp.json() as T;
        if (contentType.includes('image/') || contentType.includes('application/octet-stream')) return resp.arrayBuffer() as unknown as T;
    }
    return resp.text() as unknown as T;
}

export async function submit(task: string, answer: unknown): Promise<unknown> {
    const result = await apiPost("/verify", { apikey: getApiKey(), task, answer });
    console.log("Response:", JSON.stringify(result, null, 2));
    return result;
}
