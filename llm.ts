import { config } from "dotenv";
import { resolve } from "path";

config({ path: resolve(__dirname, ".env") });

const DEFAULT_MODEL = process.env.LLM_MODEL ?? "google/gemini-2.0-flash-001";

export async function llm(
    messages: Record<string, unknown>[],
    options: {
        model?: string;
        tools?: any;
        maxTokens?: number;
        temperature?: number;
    } = {}
): Promise<any> {
    const { model = DEFAULT_MODEL, tools, maxTokens = 1024, temperature } = options;

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
            })
        });

        if (!r.ok) throw new Error(`HTTP error! Status: ${r.status} ${await r.text()}`);

        const resp = await r.json();
        if (resp.error) {
            const genId = r.headers.get('x-generation-id');
            if (genId) console.error(`OpenRouter generation ID: https://openrouter.ai/api/v1/generation?id=${genId}`);
            console.error('Full error response:', JSON.stringify(resp, null, 2));
            throw new Error(`LLM error: ${JSON.stringify(resp.error)}`);
        }

        return resp.choices[0];
    } catch (e: any) {
        console.error(e?.message);
        return Promise.reject(e);
    }
}
