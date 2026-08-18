import { readFileSync } from 'fs';
import matter from 'gray-matter';
import sharp from 'sharp';
import { llm } from './llm';
import { prepTools, tool_call, resizeIfNeeded } from './tools';
import { logger } from './logger';

type Messages = Record<string, unknown>[];

function loadWorkflow(agent: string) {
    const raw = readFileSync(`workflows/${agent}.md`, 'utf-8');
    const { data, content } = matter(raw);
    return { data, content };
}

async function pushToolResult(messages: Messages, tool: any, toolResponse: unknown) {
    if (toolResponse instanceof ArrayBuffer) {
        const resized = await resizeIfNeeded(Buffer.from(toolResponse));
        const { format } = await sharp(resized).metadata();
        const mime = `image/${format}`;
        logger.artifact(`output.${format}`, resized);
        messages.push({ role: 'tool', tool_call_id: tool.id, content: 'Image retrieved.' });
        messages.push({
            role: 'user',
            content: [{ type: 'image_url', image_url: { url: `data:${mime};base64,${resized.toString('base64')}` } }],
        });
    } else {
        const content = typeof toolResponse === 'string' ? toolResponse : JSON.stringify(toolResponse);
        messages.push({ role: 'tool', tool_call_id: tool.id, content });
    }
}

function checkFailGuardrail(messages: Messages, tool: any, toolResponse: unknown, failCounts: Record<string, number>) {
    if (tool.function.name !== 'verify') return;
    const isFailure = typeof toolResponse === 'string' && toolResponse.startsWith('Verification failed');
    console.log(toolResponse);
    failCounts.verify = isFailure ? (failCounts.verify ?? 0) + 1 : 0;
    if (failCounts.verify >= 2) {
        messages.push({ role: 'user', content: `verify has failed ${failCounts.verify} times in a row. You must call ask_user now before retrying.` });
        failCounts.verify = 0;
    }
}

export async function startAgent(agent: string, startingMessage?: string): Promise<any> {
    const { data, content } = loadWorkflow(agent);
    const messages: Messages = [{ role: 'system', content }];
    if (startingMessage != null) messages.push({ role: 'user', content: startingMessage });

    const MAX_ITERATIONS = data.max_iterations ?? 10;
    const failCounts: Record<string, number> = {};

    for (let i = 0; i < MAX_ITERATIONS; i++) {
        const response = await llm(messages, { tools: prepTools(data.tools, data), model: data.model });
        const { message, finish_reason } = response;
        logger.artifact(`${agent}_history.json`, JSON.stringify(messages, null, 2));
        messages.push(message);

        if (finish_reason === 'tool_calls') {
            for (const tool of message.tool_calls) {
                const toolResponse = await tool_call(tool.function.name, tool.function.arguments);
                checkFailGuardrail(messages, tool, toolResponse, failCounts);
                await pushToolResult(messages, tool, toolResponse);
            }
        } else if (finish_reason === 'stop') {
            logger.info(`\n=== ${agent} ===\n${message.content}\n${'='.repeat(agent.length + 8)}\n`);
            return message.content;
        } else {
            logger.debug('unexpected finish_reason', response);
            return response;
        }
    }
    return `Agent ${agent} reached iteration limit of ${MAX_ITERATIONS}.`;
}
