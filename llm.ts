import { config } from "dotenv";
import { resolve } from "path";
import { logger } from './logger';

config({ path: resolve(__dirname, ".env") });

const DEFAULT_MODEL = process.env.LLM_MODEL ?? "google/gemini-2.0-flash-001";

const usageStats = { queries: 0, promptTokens: 0, completionTokens: 0, totalTokens: 0 };

export function getUsageStats() {
    return { ...usageStats };
}

export async function llm(
    messages: Record<string, unknown>[],
    options: {
        model?: string;
        tools?: any;
        maxTokens?: number;
        temperature?: number;
        fullResponse?: boolean;
        responseFormat?: {
            name: string,
            strict?: boolean,
            schema: Record<string, unknown>
        }
    } = { fullResponse: false }
): Promise<any> {
    const { model = DEFAULT_MODEL, tools, maxTokens = 1024, temperature, responseFormat } = options;

    try {
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
                ...(responseFormat && { response_format: { type: 'json_schema', json_schema: responseFormat } })
            })
        });

        if (!r.ok) throw new Error(`HTTP error! Status: ${r.status} ${await r.text()}`);

        const resp = await r.json();
        usageStats.queries++;
        if (resp.usage) {
            usageStats.promptTokens += resp.usage.prompt_tokens ?? 0;
            usageStats.completionTokens += resp.usage.completion_tokens ?? 0;
            usageStats.totalTokens += resp.usage.total_tokens ?? 0;
        }
        if (resp.error) {
            const genId = r.headers.get('x-generation-id');
            if (genId) logger.error(`OpenRouter generation ID: https://openrouter.ai/api/v1/generation?id=${genId}`);
            logger.error('Full LLM error response', resp);
            throw new Error(`LLM error: ${JSON.stringify(resp.error)}`);
        }
        if (options.fullResponse) {
            return resp;
        }
        return resp.choices[0];
    } catch (e: any) {
        logger.error(e?.message);
        return Promise.reject(e);
    }
}
